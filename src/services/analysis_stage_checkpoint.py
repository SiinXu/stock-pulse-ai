# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Stage-level analysis checkpoints and reproducibility controls.

Extends task-queue restart recovery (requeue of ``stock_analysis``) and
trading-day fetch resume with analysis **stage** durability:

* After each successful multi-agent stage, intermediate state is persisted.
* On resume for the same ``query_id`` / stock, completed stages are restored
  and skipped when the compatibility fingerprint still matches.
* Recovery is exact-replay only: fingerprint mismatch invalidates the
  checkpoint so the run never silently produces a different conclusion.
* Reproducibility controls record a run-config snapshot and optionally pin
  local randomness / temperature for more comparable re-runs.

Process-local only (ADR-004 / ADR-008). Not a distributed queue.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
CHECKPOINT_SCHEMA = "analysis_stage_checkpoint.v1"
META_SESSION_KEY = "_analysis_stage_checkpoint_session"
META_ANNOTATION_KEY = "analysis_checkpoint"
META_REPRO_KEY = "run_configuration"
AGENT_STAGE_NAMESPACE = "agent"
PIPELINE_STAGE_NAMESPACE = "pipeline"
_SAFE_RUN_KEY = re.compile(r"[^A-Za-z0-9._-]+")
_CHECKPOINT_IO_LOCK = threading.RLock()
_CURRENT_CHECKPOINT_SESSION: ContextVar[Optional["AnalysisStageCheckpointSession"]] = (
    ContextVar("analysis_stage_checkpoint_session", default=None)
)
_CHECKPOINT_RUNTIME_META_KEYS = frozenset({"mode_budget", "mode_budget_account"})
_CONFIG_CONTRACT_PREFIXES = (
    "agent_",
    "decision_",
    "generation_",
    "llm_",
    "report_",
    "repro_",
    "risk_",
)
_SENSITIVE_CONFIG_FRAGMENTS = ("api_key", "password", "secret", "token")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json_default(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return sorted(value)
    if hasattr(value, "value") and not isinstance(value, (str, bytes, int, float, bool)):
        try:
            return value.value
        except Exception:  # broad-exception: optional_metadata - Enum-like adapters may expose a failing value property; the next supported projection is attempted.
            pass
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return value.to_dict()
        except Exception:  # broad-exception: optional_metadata - Optional object projections may fail; unsupported values are rejected below.
            pass
    raise TypeError(f"Unsupported checkpoint value: {type(value).__name__}")


def stable_json_dumps(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
        allow_nan=False,
    )


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(stable_json_dumps(payload).encode("utf-8")).hexdigest()[:32]


def sanitize_run_key(query_id: str, stock_code: str) -> str:
    raw = f"{str(query_id or '').strip()}__{str(stock_code or '').strip()}"
    cleaned = _SAFE_RUN_KEY.sub("_", raw).strip("._-") or "unknown_run"
    return f"{cleaned[:80]}_{stable_hash(raw)[:16]}"


def _resolve_app_revision() -> Optional[str]:
    for key in ("STOCKPULSE_REVISION", "GIT_COMMIT", "GITHUB_SHA"):
        value = (os.getenv(key) or "").strip()
        if value:
            return value[:64]
    try:
        root = Path(__file__).resolve().parents[2]
        git_dir = root / ".git"
        if git_dir.is_file():
            marker = git_dir.read_text(encoding="utf-8").strip()
            if marker.startswith("gitdir:"):
                git_dir = (root / marker.split(":", 1)[1].strip()).resolve()
        head = git_dir / "HEAD"
        if not head.is_file():
            return None
        text = head.read_text(encoding="utf-8").strip()
        if text.startswith("ref:"):
            ref = text.split(":", 1)[1].strip()
            ref_path = git_dir / ref
            if ref_path.is_file():
                return ref_path.read_text(encoding="utf-8").strip()[:40]
            return ref
        return text[:40] or None
    except OSError:
        return None


@lru_cache(maxsize=1)
def _runtime_contract_hash() -> str:
    """Hash executable Agent/strategy sources that can change resumed conclusions."""
    root = Path(__file__).resolve().parents[2]
    candidates: List[Path] = []
    for relative in ("src/agent", "strategies"):
        directory = root / relative
        if directory.is_dir():
            candidates.extend(
                path
                for path in directory.rglob("*")
                if path.is_file() and path.suffix in {".py", ".yaml", ".yml"}
            )
    for relative in (
        "src/core/stages/analysis_agent.py",
        "src/core/stages/orchestration.py",
        "src/services/analysis_stage_checkpoint.py",
    ):
        path = root / relative
        if path.is_file():
            candidates.append(path)
    digest = hashlib.sha256()
    for path in sorted(set(candidates), key=lambda item: item.as_posix()):
        try:
            content = path.read_bytes()
        except OSError:
            return "unavailable"
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()[:32] if candidates else "unavailable"


def _configuration_contract_hash(config: Any) -> str:
    try:
        raw = vars(config)
    except TypeError:
        raw = {}
    projection: Dict[str, Any] = {}
    for key, value in raw.items():
        normalized_key = str(key).lower()
        if not normalized_key.startswith(_CONFIG_CONTRACT_PREFIXES):
            continue
        if any(fragment in normalized_key for fragment in _SENSITIVE_CONFIG_FRAGMENTS):
            continue
        try:
            stable_json_dumps(value)
        except (TypeError, ValueError, OverflowError):
            continue
        projection[str(key)] = value
    return stable_hash(projection)


def build_repro_snapshot(
    config: Any,
    *,
    skills: Optional[Sequence[str]] = None,
    seed: Optional[int] = None,
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    skill_list = [str(item) for item in (skills or []) if str(item).strip()]
    if not skill_list:
        configured = getattr(config, "agent_skills", None) or []
        skill_list = [str(item) for item in configured if str(item).strip()]
    snapshot: Dict[str, Any] = {
        "schema": "run_configuration.v1",
        "recorded_at": _utc_now_iso(),
        "repro_mode_enabled": getattr(config, "repro_mode_enabled", False) is True,
        "seed": seed if seed is not None else getattr(config, "repro_seed", None),
        "models": {
            "litellm_model": getattr(config, "litellm_model", None),
            "agent_litellm_model": getattr(config, "agent_litellm_model", None),
            "agent_generation_backend": getattr(config, "agent_generation_backend", None),
            "generation_backend": getattr(config, "generation_backend", None),
        },
        "sampling": {
            "llm_temperature": getattr(config, "llm_temperature", None),
            "gemini_temperature": getattr(config, "gemini_temperature", None),
            "openai_temperature": getattr(config, "openai_temperature", None),
            "anthropic_temperature": getattr(config, "anthropic_temperature", None),
        },
        "pipeline": {
            "agent_mode": bool(getattr(config, "agent_mode", False)),
            "agent_arch": getattr(config, "agent_arch", None),
            "agent_orchestrator_mode": getattr(config, "agent_orchestrator_mode", None),
            "agent_critic_enabled": bool(getattr(config, "agent_critic_enabled", False)),
            "agent_red_team_enabled": bool(getattr(config, "agent_red_team_enabled", False)),
            "agent_multi_strategy_deliberation": bool(
                getattr(config, "agent_multi_strategy_deliberation", False)
            ),
            "agent_investment_committee_mode": bool(
                getattr(config, "agent_investment_committee_mode", False)
            ),
            "agent_risk_override": bool(getattr(config, "agent_risk_override", True)),
            "risk_gate_profile": getattr(config, "risk_gate_profile", None),
            "report_type": getattr(config, "report_type", None),
            "report_language": getattr(config, "report_language", None),
            "report_mode": getattr(config, "report_mode", None),
        },
        "skills": skill_list,
        "feature_flags": {
            "agent_planning_enabled": bool(getattr(config, "agent_planning_enabled", False)),
            "agent_memory_enabled": bool(getattr(config, "agent_memory_enabled", False)),
            "decision_memory_enabled": bool(getattr(config, "decision_memory_enabled", False)),
            "report_integrity_enabled": bool(getattr(config, "report_integrity_enabled", True)),
            "agent_observability_enabled": bool(
                getattr(config, "agent_observability_enabled", True)
            ),
        },
        "versions": {
            "checkpoint_schema": CHECKPOINT_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "backtest_engine_version": getattr(config, "backtest_engine_version", None),
            "app_revision": _resolve_app_revision(),
            "runtime_contract_hash": _runtime_contract_hash(),
            "configuration_contract_hash": _configuration_contract_hash(config),
        },
        "limitations": [
            "Provider-side sampling may remain non-deterministic even when temperature is pinned.",
            "Live market data and search results can change between a full run and a later replay.",
            "Exact-replay resume reuses stored stage outputs; it does not re-call the LLM for those stages.",
        ],
    }
    if extra:
        snapshot["extra"] = dict(extra)
    snapshot["fingerprint"] = stable_hash(
        {
            "models": snapshot["models"],
            "sampling": snapshot["sampling"],
            "pipeline": snapshot["pipeline"],
            "skills": snapshot["skills"],
            "feature_flags": snapshot["feature_flags"],
            "versions": snapshot["versions"],
            "seed": snapshot["seed"],
        }
    )
    return snapshot


def build_compatibility_fingerprint(
    *,
    stock_code: str,
    repro_snapshot: Mapping[str, Any],
    report_type: Optional[str] = None,
    analysis_phase: Optional[str] = None,
) -> str:
    return stable_hash(
        {
            "stock_code": str(stock_code or "").strip(),
            "report_type": report_type,
            "analysis_phase": analysis_phase,
            "repro_fingerprint": repro_snapshot.get("fingerprint"),
            "checkpoint_schema": CHECKPOINT_SCHEMA,
            "schema_version": SCHEMA_VERSION,
        }
    )


def _normalize_repro_seed(value: Any) -> int:
    try:
        return max(0, int(value if value is not None else 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def build_repro_status(config: Any) -> Dict[str, Any]:
    """Describe request-scoped reproducibility controls without global mutation."""
    enabled = getattr(config, "repro_mode_enabled", False) is True
    seed = _normalize_repro_seed(getattr(config, "repro_seed", None)) if enabled else None
    return {
        "enabled": enabled,
        "seed": seed,
        "seed_forwarded_to_provider": enabled,
        "effective_llm_temperature": 0.0 if enabled else getattr(config, "llm_temperature", None),
        "temperature_pinned": enabled,
        "scope": "request",
    }


def resolve_repro_generation_params(
    config: Any,
    requested_temperature: Any,
) -> Tuple[Any, Optional[int]]:
    """Return per-call temperature/seed overrides for compatible providers."""
    if getattr(config, "repro_mode_enabled", False) is not True:
        return requested_temperature, None
    return 0.0, _normalize_repro_seed(getattr(config, "repro_seed", None))


def apply_repro_mode(config: Any) -> Dict[str, Any]:
    """Backward-compatible pure status helper; never mutates shared runtime state."""
    return build_repro_status(config)


def serialize_agent_opinion(opinion: Any) -> Dict[str, Any]:
    if opinion is None:
        return {}
    if isinstance(opinion, Mapping):
        payload = dict(opinion)
    elif is_dataclass(opinion) and not isinstance(opinion, type):
        payload = asdict(opinion)
    else:
        payload = {
            "agent_name": getattr(opinion, "agent_name", ""),
            "signal": getattr(opinion, "signal", ""),
            "confidence": getattr(opinion, "confidence", 0.0),
            "reasoning": getattr(opinion, "reasoning", ""),
            "key_levels": dict(getattr(opinion, "key_levels", {}) or {}),
            "raw_data": dict(getattr(opinion, "raw_data", {}) or {}),
            "timestamp": getattr(opinion, "timestamp", 0.0),
        }
    return json.loads(stable_json_dumps(payload))


def deserialize_agent_opinion(payload: Mapping[str, Any]) -> Any:
    from src.agent.protocols import AgentOpinion

    return AgentOpinion(
        agent_name=str(payload.get("agent_name") or ""),
        signal=str(payload.get("signal") or ""),
        confidence=float(payload.get("confidence") or 0.0),
        reasoning=str(payload.get("reasoning") or ""),
        key_levels=dict(payload.get("key_levels") or {}),
        raw_data=dict(payload.get("raw_data") or {}),
        timestamp=float(payload.get("timestamp") or 0.0),
    )


@dataclass
class StageCheckpointRecord:
    stage: str
    status: str = "success"
    payload: Dict[str, Any] = field(default_factory=dict)
    completed_at: str = field(default_factory=_utc_now_iso)


@dataclass
class AnalysisCheckpointManifest:
    schema: str = CHECKPOINT_SCHEMA
    schema_version: int = SCHEMA_VERSION
    query_id: str = ""
    stock_code: str = ""
    compatibility_fingerprint: str = ""
    repro_snapshot: Dict[str, Any] = field(default_factory=dict)
    completed_stages: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
    consistency: str = "exact_replay"
    invalidated: bool = False
    invalidate_reason: Optional[str] = None
    resumed: bool = False
    resume_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "query_id": self.query_id,
            "stock_code": self.stock_code,
            "compatibility_fingerprint": self.compatibility_fingerprint,
            "repro_snapshot": self.repro_snapshot,
            "completed_stages": list(self.completed_stages),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "consistency": self.consistency,
            "invalidated": self.invalidated,
            "invalidate_reason": self.invalidate_reason,
            "resumed": self.resumed,
            "resume_count": self.resume_count,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "AnalysisCheckpointManifest":
        return cls(
            schema=str(raw.get("schema") or CHECKPOINT_SCHEMA),
            schema_version=int(raw.get("schema_version") or SCHEMA_VERSION),
            query_id=str(raw.get("query_id") or ""),
            stock_code=str(raw.get("stock_code") or ""),
            compatibility_fingerprint=str(raw.get("compatibility_fingerprint") or ""),
            repro_snapshot=dict(raw.get("repro_snapshot") or {}),
            completed_stages=[str(item) for item in (raw.get("completed_stages") or [])],
            created_at=str(raw.get("created_at") or _utc_now_iso()),
            updated_at=str(raw.get("updated_at") or _utc_now_iso()),
            consistency=str(raw.get("consistency") or "exact_replay"),
            invalidated=bool(raw.get("invalidated")),
            invalidate_reason=(
                str(raw["invalidate_reason"])
                if raw.get("invalidate_reason") is not None
                else None
            ),
            resumed=bool(raw.get("resumed")),
            resume_count=int(raw.get("resume_count") or 0),
        )


class AnalysisStageCheckpointStore:
    def __init__(self, root_dir: str | Path, *, ttl_hours: int = 24) -> None:
        self.root_dir = Path(root_dir).expanduser()
        self.ttl_hours = max(0, int(ttl_hours))
        self._lock = _CHECKPOINT_IO_LOCK

    def _run_dir(self, query_id: str, stock_code: str) -> Path:
        return self.root_dir / sanitize_run_key(query_id, stock_code)

    def _manifest_path(self, run_dir: Path) -> Path:
        return run_dir / "manifest.json"

    def run_exists(self, query_id: str, stock_code: str) -> bool:
        return self._run_dir(query_id, stock_code).exists()

    def _stage_path(self, run_dir: Path, stage: str) -> Path:
        safe = _SAFE_RUN_KEY.sub("_", stage).strip("._-") or "stage"
        return run_dir / "stages" / f"{safe}.json"

    def ensure_root(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(
            f".{path.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
        )
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def cleanup_expired(self) -> int:
        if self.ttl_hours <= 0 or not self.root_dir.exists():
            return 0
        cutoff = time.time() - (self.ttl_hours * 3600)
        removed = 0
        with self._lock:
            for child in list(self.root_dir.iterdir()):
                if not child.is_dir():
                    continue
                try:
                    mtime = child.stat().st_mtime
                except OSError:
                    continue
                if mtime < cutoff:
                    try:
                        shutil.rmtree(child)
                        removed += 1
                    except OSError as exc:
                        log_safe_exception(
                            logger,
                            "Failed to remove expired analysis checkpoint",
                            exc,
                            error_code="analysis_checkpoint_ttl_cleanup_failed",
                            level=logging.WARNING,
                            context={"path": str(child)},
                        )
        return removed

    def load_manifest(
        self, query_id: str, stock_code: str
    ) -> Optional[AnalysisCheckpointManifest]:
        path = self._manifest_path(self._run_dir(query_id, stock_code))
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError) as exc:
            log_safe_exception(
                logger,
                "Failed to read analysis checkpoint manifest",
                exc,
                error_code="analysis_checkpoint_manifest_read_failed",
                level=logging.WARNING,
                context={"path": str(path)},
            )
            return None
        if not isinstance(raw, dict):
            return None
        try:
            manifest = AnalysisCheckpointManifest.from_dict(raw)
        except (TypeError, ValueError, OverflowError):
            return None
        if (
            manifest.schema != CHECKPOINT_SCHEMA
            or manifest.schema_version != SCHEMA_VERSION
            or manifest.query_id != str(query_id)
            or manifest.stock_code != str(stock_code)
        ):
            return None
        return manifest

    def save_manifest(self, manifest: AnalysisCheckpointManifest) -> bool:
        run_dir = self._run_dir(manifest.query_id, manifest.stock_code)
        try:
            with self._lock:
                run_dir.mkdir(parents=True, exist_ok=True)
                (run_dir / "stages").mkdir(parents=True, exist_ok=True)
                manifest.updated_at = _utc_now_iso()
                self._atomic_write_json(
                    self._manifest_path(run_dir),
                    manifest.to_dict(),
                )
            return True
        except (OSError, TypeError, ValueError) as exc:
            log_safe_exception(
                logger,
                "Failed to write analysis checkpoint manifest",
                exc,
                error_code="analysis_checkpoint_manifest_write_failed",
                level=logging.WARNING,
                context={"query_id": manifest.query_id, "stock_code": manifest.stock_code},
            )
            return False

    def save_stage(
        self,
        *,
        query_id: str,
        stock_code: str,
        stage: str,
        payload: Mapping[str, Any],
        status: str = "success",
        manifest: Optional[AnalysisCheckpointManifest] = None,
    ) -> Optional[AnalysisCheckpointManifest]:
        stage_name = str(stage or "").strip()
        if not stage_name:
            return manifest
        run_dir = self._run_dir(query_id, stock_code)
        try:
            record = StageCheckpointRecord(
                stage=stage_name,
                status=status,
                payload=json.loads(stable_json_dumps(dict(payload))),
            )
            with self._lock:
                persisted = self.load_manifest(query_id, stock_code)
                if (
                    persisted is not None
                    and manifest is not None
                    and persisted.compatibility_fingerprint
                    != manifest.compatibility_fingerprint
                ):
                    return None
                manifest = persisted or manifest or AnalysisCheckpointManifest(
                    query_id=query_id,
                    stock_code=stock_code,
                )
                updated = AnalysisCheckpointManifest.from_dict(manifest.to_dict())
                if stage_name not in updated.completed_stages:
                    updated.completed_stages.append(stage_name)
                updated.query_id = query_id
                updated.stock_code = stock_code
                run_dir.mkdir(parents=True, exist_ok=True)
                (run_dir / "stages").mkdir(parents=True, exist_ok=True)
                self._atomic_write_json(
                    self._stage_path(run_dir, stage_name),
                    asdict(record),
                )
                if not self.save_manifest(updated):
                    return None
            return updated
        except (OSError, TypeError, ValueError) as exc:
            log_safe_exception(
                logger,
                "Failed to write analysis stage checkpoint",
                exc,
                error_code="analysis_checkpoint_stage_write_failed",
                level=logging.WARNING,
                context={"query_id": query_id, "stock_code": stock_code, "stage": stage_name},
            )
            return None

    def load_stage(
        self, query_id: str, stock_code: str, stage: str
    ) -> Optional[StageCheckpointRecord]:
        path = self._stage_path(self._run_dir(query_id, stock_code), stage)
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return None
            payload = raw.get("payload") or {}
            if not isinstance(payload, dict):
                return None
            record = StageCheckpointRecord(
                stage=str(raw.get("stage") or stage),
                status=str(raw.get("status") or "success"),
                payload=dict(payload),
                completed_at=str(raw.get("completed_at") or _utc_now_iso()),
            )
        except (OSError, TypeError, ValueError, OverflowError):
            return None
        if record.stage != stage:
            return None
        return record

    def delete_run(self, query_id: str, stock_code: str) -> bool:
        run_dir = self._run_dir(query_id, stock_code)
        if not run_dir.exists():
            return True
        try:
            with self._lock:
                shutil.rmtree(run_dir)
            return True
        except OSError as exc:
            log_safe_exception(
                logger,
                "Failed to delete analysis checkpoint run",
                exc,
                error_code="analysis_checkpoint_delete_failed",
                level=logging.WARNING,
                context={"query_id": query_id, "stock_code": stock_code},
            )
            return False

    def invalidate(
        self,
        query_id: str,
        stock_code: str,
        reason: str,
        *,
        delete: bool = True,
    ) -> None:
        if delete:
            self.delete_run(query_id, stock_code)
            return
        manifest = self.load_manifest(query_id, stock_code)
        if manifest is None:
            return
        manifest.invalidated = True
        manifest.invalidate_reason = reason
        manifest.consistency = "invalidated"
        self.save_manifest(manifest)


@dataclass
class AnalysisStageCheckpointSession:
    store: AnalysisStageCheckpointStore
    query_id: str
    stock_code: str
    enabled: bool
    force_full: bool
    compatibility_fingerprint: str
    repro_snapshot: Dict[str, Any]
    record_config: bool = True
    repro_status: Dict[str, Any] = field(default_factory=dict)
    manifest: Optional[AnalysisCheckpointManifest] = None
    restored_stages: List[str] = field(default_factory=list)
    consistency: str = "full_run"
    annotation: Dict[str, Any] = field(default_factory=dict)

    def __deepcopy__(self, memo: Dict[int, Any]) -> "AnalysisStageCheckpointSession":
        """Keep the request-scoped session shared across isolated Agent contexts."""
        memo[id(self)] = self
        return self

    @property
    def completed_stages(self) -> Tuple[str, ...]:
        if self.manifest is None:
            return ()
        return tuple(self.manifest.completed_stages)

    def is_stage_complete(self, stage: str) -> bool:
        return stage in self.completed_stages

    def _disable_after_persistence_failure(self, note: str) -> None:
        self.enabled = False
        self.manifest = None
        self.restored_stages = []
        self.consistency = "checkpoint_unavailable"
        self._refresh_annotation(resumed=False, note=note)

    def _begin_fresh(self, consistency: str, *, note: Optional[str] = None) -> None:
        self.manifest = AnalysisCheckpointManifest(
            query_id=self.query_id,
            stock_code=self.stock_code,
            compatibility_fingerprint=self.compatibility_fingerprint,
            repro_snapshot=self.repro_snapshot,
            consistency=consistency,
            invalidate_reason=note,
        )
        self.consistency = consistency
        if not self.store.save_manifest(self.manifest):
            self._disable_after_persistence_failure("manifest_write_failed")
            return
        self._refresh_annotation(resumed=False, note=note)

    def begin(self) -> "AnalysisStageCheckpointSession":
        if not self.enabled:
            self.consistency = "checkpoint_disabled"
            self._refresh_annotation(resumed=False)
            return self
        if self.force_full:
            self.store.invalidate(self.query_id, self.stock_code, "force_full_rerun", delete=True)
            self._begin_fresh("full_rerun_forced", note="force_full_rerun")
            return self
        existing = self.store.load_manifest(self.query_id, self.stock_code)
        if existing is None:
            if self.store.run_exists(self.query_id, self.stock_code):
                self.store.invalidate(
                    self.query_id,
                    self.stock_code,
                    "corrupt_manifest",
                    delete=True,
                )
                self._begin_fresh(
                    "full_rerun_corrupt_checkpoint",
                    note="corrupt_manifest",
                )
            else:
                self._begin_fresh("full_run")
            return self
        if existing.invalidated:
            self.store.delete_run(self.query_id, self.stock_code)
            self._begin_fresh("full_run", note="prior_invalidated")
            return self
        if existing.compatibility_fingerprint != self.compatibility_fingerprint:
            reason = "compatibility_fingerprint_mismatch"
            self.store.invalidate(self.query_id, self.stock_code, reason, delete=True)
            self._begin_fresh("full_rerun_incompatible", note=reason)
            logger.info(
                "Analysis checkpoint invalidated for %s (%s): %s",
                self.stock_code,
                self.query_id,
                reason,
            )
            return self
        corrupt_stage = next(
            (
                stage
                for stage in existing.completed_stages
                if (
                    (record := self.store.load_stage(self.query_id, self.stock_code, stage))
                    is None
                    or record.status != "success"
                )
            ),
            None,
        )
        if corrupt_stage is not None:
            reason = f"missing_stage_payload:{corrupt_stage}"
            self.store.invalidate(self.query_id, self.stock_code, reason, delete=True)
            self._begin_fresh("full_rerun_corrupt_checkpoint", note=reason)
            return self
        existing.resumed = True
        existing.resume_count = int(existing.resume_count or 0) + 1
        existing.repro_snapshot = self.repro_snapshot
        existing.compatibility_fingerprint = self.compatibility_fingerprint
        existing.consistency = "exact_replay"
        self.manifest = existing
        if not self.store.save_manifest(self.manifest):
            self._disable_after_persistence_failure("manifest_write_failed")
            return self
        self.consistency = "exact_replay"
        self.restored_stages = list(existing.completed_stages)
        self._refresh_annotation(resumed=bool(self.restored_stages))
        if self.restored_stages:
            logger.info(
                "Analysis checkpoint resume for %s (%s): stages=%s",
                self.stock_code,
                self.query_id,
                ",".join(self.restored_stages),
            )
        return self

    def save_stage(self, stage: str, payload: Mapping[str, Any], *, status: str = "success") -> None:
        if not self.enabled:
            return
        if self.manifest is None:
            self.manifest = AnalysisCheckpointManifest(
                query_id=self.query_id,
                stock_code=self.stock_code,
                compatibility_fingerprint=self.compatibility_fingerprint,
                repro_snapshot=self.repro_snapshot,
            )
        saved_manifest = self.store.save_stage(
            query_id=self.query_id,
            stock_code=self.stock_code,
            stage=stage,
            payload=payload,
            status=status,
            manifest=self.manifest,
        )
        if saved_manifest is None:
            self._disable_after_persistence_failure(f"stage_write_failed:{stage}")
            return
        self.manifest = saved_manifest
        self._refresh_annotation(resumed=bool(self.restored_stages))

    def load_stage_payload(self, stage: str) -> Optional[Dict[str, Any]]:
        if not self.enabled or not self.is_stage_complete(stage):
            return None
        record = self.store.load_stage(self.query_id, self.stock_code, stage)
        if record is None or record.status != "success":
            return None
        return dict(record.payload)

    def complete(self) -> None:
        if not self.enabled:
            return
        deleted = self.store.delete_run(self.query_id, self.stock_code)
        self.manifest = None
        self._refresh_annotation(
            resumed=bool(self.restored_stages),
            completed=True,
            note=None if deleted else "checkpoint_cleanup_failed",
        )

    def fail_keep(self) -> None:
        self._refresh_annotation(resumed=bool(self.restored_stages), completed=False)

    def metadata_for_snapshot(self) -> Dict[str, Any]:
        return {
            "checkpoint": dict(self.annotation),
            "run_configuration": (
                dict(self.repro_snapshot) if self.record_config else {}
            ),
            "repro_status": dict(self.repro_status),
        }

    def _refresh_annotation(
        self,
        *,
        resumed: bool,
        note: Optional[str] = None,
        completed: bool = False,
    ) -> None:
        self.annotation = {
            "enabled": self.enabled,
            "query_id": self.query_id,
            "stock_code": self.stock_code,
            "consistency": self.consistency,
            "resumed": resumed,
            "restored_stages": list(self.restored_stages),
            "completed_stages": list(self.completed_stages),
            "compatibility_fingerprint": self.compatibility_fingerprint,
            "force_full": self.force_full,
            "note": note,
            "completed": completed,
            "resume_count": int(self.manifest.resume_count) if self.manifest is not None else 0,
        }


def create_checkpoint_session(
    config: Any,
    *,
    query_id: str,
    stock_code: str,
    skills: Optional[Sequence[str]] = None,
    report_type: Optional[str] = None,
    analysis_phase: Optional[str] = None,
    force_full: bool = False,
    active: bool = True,
    store: Optional[AnalysisStageCheckpointStore] = None,
) -> AnalysisStageCheckpointSession:
    enabled = bool(active) and bool(getattr(config, "analysis_checkpoint_enabled", True))
    force = bool(force_full) or bool(getattr(config, "analysis_checkpoint_force_full", False))
    root = getattr(config, "analysis_checkpoint_dir", None) or "./data/checkpoints"
    ttl_value = getattr(config, "analysis_checkpoint_ttl_hours", 24)
    ttl = int(24 if ttl_value is None else ttl_value)
    if store is None:
        store = AnalysisStageCheckpointStore(root, ttl_hours=ttl)
        if enabled:
            try:
                store.ensure_root()
                store.cleanup_expired()
            except OSError as exc:
                log_safe_exception(
                    logger,
                    "Analysis checkpoint store init failed; continuing without checkpoints",
                    exc,
                    error_code="analysis_checkpoint_store_init_failed",
                    level=logging.WARNING,
                )
                enabled = False
    repro_status = build_repro_status(config)
    seed = repro_status.get("seed")
    if seed is None:
        seed = getattr(config, "repro_seed", None)
    record_config = bool(getattr(config, "repro_record_config", True))
    if record_config or enabled or getattr(config, "repro_mode_enabled", False) is True:
        repro_snapshot = build_repro_snapshot(config, skills=skills, seed=seed)
    else:
        repro_snapshot = {
            "schema": "run_configuration.v1",
            "recorded_at": _utc_now_iso(),
            "fingerprint": "unrecorded",
        }
    fingerprint = build_compatibility_fingerprint(
        stock_code=stock_code,
        repro_snapshot=repro_snapshot,
        report_type=report_type,
        analysis_phase=analysis_phase,
    )
    session = AnalysisStageCheckpointSession(
        store=store,
        query_id=str(query_id or "").strip() or "anonymous",
        stock_code=str(stock_code or "").strip(),
        enabled=enabled,
        force_full=force,
        compatibility_fingerprint=fingerprint,
        repro_snapshot=repro_snapshot,
        record_config=record_config,
        repro_status=repro_status,
    )
    return session.begin()


def agent_stage_name(stage: str) -> str:
    return f"{AGENT_STAGE_NAMESPACE}.{stage}"


def pipeline_stage_name(stage: str) -> str:
    return f"{PIPELINE_STAGE_NAMESPACE}.{stage}"


def _public_checkpoint_meta(meta: Any) -> Dict[str, Any]:
    if not isinstance(meta, Mapping):
        return {}
    return {
        str(key): value
        for key, value in meta.items()
        if not str(key).startswith("_")
        and str(key) not in {META_ANNOTATION_KEY, META_REPRO_KEY}
        and str(key) not in _CHECKPOINT_RUNTIME_META_KEYS
    }


def build_agent_input_fingerprint(ctx: Any) -> Optional[str]:
    """Fingerprint the fully assembled Agent input before any stage runs."""
    projection = {
        "query": getattr(ctx, "query", ""),
        "stock_code": getattr(ctx, "stock_code", ""),
        "stock_name": getattr(ctx, "stock_name", ""),
        "session_id": getattr(ctx, "session_id", ""),
        "data": dict(getattr(ctx, "data", {}) or {}),
        "risk_flags": list(getattr(ctx, "risk_flags", []) or []),
        "meta": _public_checkpoint_meta(getattr(ctx, "meta", {})),
    }
    try:
        return stable_hash(projection)
    except (TypeError, ValueError, OverflowError):
        return None


def _restart_after_invalid_restore(
    session: AnalysisStageCheckpointSession,
    reason: str,
) -> None:
    session.store.invalidate(session.query_id, session.stock_code, reason, delete=True)
    session.restored_stages = []
    session._begin_fresh("full_rerun_corrupt_checkpoint", note=reason)


def restore_agent_context_from_session(
    session: AnalysisStageCheckpointSession, ctx: Any
) -> List[str]:
    if not session.enabled:
        return []
    agent_stages = [
        stage
        for stage in session.completed_stages
        if stage.startswith(f"{AGENT_STAGE_NAMESPACE}.")
    ]
    if not agent_stages:
        return []
    latest_stage = agent_stages[-1]
    payload = session.load_stage_payload(latest_stage)
    context_snapshot = payload.get("context") if isinstance(payload, Mapping) else None
    if not isinstance(context_snapshot, Mapping):
        _restart_after_invalid_restore(session, f"invalid_context_snapshot:{latest_stage}")
        return []
    current_input_fingerprint = build_agent_input_fingerprint(ctx)
    saved_input_fingerprint = str(payload.get("input_fingerprint") or "")
    if (
        not current_input_fingerprint
        or not saved_input_fingerprint
        or current_input_fingerprint != saved_input_fingerprint
    ):
        _restart_after_invalid_restore(session, "agent_input_fingerprint_mismatch")
        return []
    opinions_raw = context_snapshot.get("opinions")
    risk_flags_raw = context_snapshot.get("risk_flags")
    data_raw = context_snapshot.get("data")
    meta_raw = context_snapshot.get("meta")
    if (
        not isinstance(opinions_raw, list)
        or not isinstance(risk_flags_raw, list)
        or not isinstance(data_raw, Mapping)
        or not isinstance(meta_raw, Mapping)
    ):
        _restart_after_invalid_restore(session, f"invalid_context_snapshot:{latest_stage}")
        return []
    try:
        restored_opinions = [
            deserialize_agent_opinion(item)
            for item in opinions_raw
            if isinstance(item, Mapping)
        ]
        if len(restored_opinions) != len(opinions_raw):
            raise ValueError("invalid opinion payload")
        restored_risk_flags = [dict(item) for item in risk_flags_raw if isinstance(item, Mapping)]
        if len(restored_risk_flags) != len(risk_flags_raw):
            raise ValueError("invalid risk flag payload")
    except (TypeError, ValueError, OverflowError):
        _restart_after_invalid_restore(session, f"invalid_context_snapshot:{latest_stage}")
        return []

    private_meta = {
        key: value
        for key, value in (getattr(ctx, "meta", {}) or {}).items()
        if str(key).startswith("_")
        or str(key) in {META_ANNOTATION_KEY, META_REPRO_KEY}
        or str(key) in _CHECKPOINT_RUNTIME_META_KEYS
    }
    ctx.opinions[:] = restored_opinions
    ctx.risk_flags[:] = restored_risk_flags
    ctx.data.clear()
    ctx.data.update(dict(data_raw))
    ctx.meta.clear()
    ctx.meta.update(dict(meta_raw))
    ctx.meta.update(private_meta)

    restored = [stage.split(".", 1)[1] for stage in agent_stages]
    ctx.meta["_checkpoint_restored_agent_stages"] = list(restored)
    session.restored_stages = list(session.completed_stages)
    session.consistency = "exact_replay"
    session._refresh_annotation(resumed=True)
    return restored


def capture_agent_stage_payload(
    ctx: Any,
    *,
    stage_name: str,
    stage_result: Any = None,
) -> Dict[str, Any]:
    all_opinions = [serialize_agent_opinion(item) for item in (getattr(ctx, "opinions", []) or [])]
    input_fingerprint = (getattr(ctx, "meta", {}) or {}).get(
        "_checkpoint_agent_input_fingerprint"
    )
    context_snapshot = {
        "opinions": all_opinions,
        "risk_flags": list(getattr(ctx, "risk_flags", []) or []),
        "data": dict(getattr(ctx, "data", {}) or {}),
        "meta": _public_checkpoint_meta(getattr(ctx, "meta", {})),
    }
    result_meta = {}
    if stage_result is not None:
        result_meta = {
            "status": str(
                getattr(getattr(stage_result, "status", None), "value", getattr(stage_result, "status", ""))
            ),
            "duration_s": getattr(stage_result, "duration_s", None),
            "tokens_used": getattr(stage_result, "tokens_used", None),
            "models_used": list((getattr(stage_result, "meta", {}) or {}).get("models_used") or []),
        }
    return {
        "stage": stage_name,
        "input_fingerprint": input_fingerprint,
        "context": json.loads(stable_json_dumps(context_snapshot)),
        "stage_result": result_meta,
    }


def activate_checkpoint_session(
    session: AnalysisStageCheckpointSession,
) -> Token[Optional[AnalysisStageCheckpointSession]]:
    return _CURRENT_CHECKPOINT_SESSION.set(session)


def current_checkpoint_session() -> Optional[AnalysisStageCheckpointSession]:
    return _CURRENT_CHECKPOINT_SESSION.get()


def reset_checkpoint_session(
    token: Optional[Token[Optional[AnalysisStageCheckpointSession]]],
) -> None:
    if token is not None:
        _CURRENT_CHECKPOINT_SESSION.reset(token)


def session_from_agent_context(ctx: Any) -> Optional[AnalysisStageCheckpointSession]:
    meta = getattr(ctx, "meta", None)
    if isinstance(meta, dict):
        session = meta.get(META_SESSION_KEY)
        if isinstance(session, AnalysisStageCheckpointSession):
            return session
    data = getattr(ctx, "data", None)
    if isinstance(data, dict):
        session = data.get(META_SESSION_KEY)
        if isinstance(session, AnalysisStageCheckpointSession):
            return session
    return None
