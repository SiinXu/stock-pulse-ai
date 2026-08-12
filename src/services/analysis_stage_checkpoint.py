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
import random
import re
import shutil
import threading
import time
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
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
        except Exception:
            pass
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return value.to_dict()
        except Exception:
            pass
    return str(value)


def stable_json_dumps(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(stable_json_dumps(payload).encode("utf-8")).hexdigest()[:32]


def sanitize_run_key(query_id: str, stock_code: str) -> str:
    raw = f"{str(query_id or '').strip()}__{str(stock_code or '').strip()}"
    cleaned = _SAFE_RUN_KEY.sub("_", raw).strip("._-") or "unknown_run"
    if len(cleaned) > 120:
        cleaned = f"{cleaned[:80]}_{stable_hash(raw)[:16]}"
    return cleaned


def _resolve_app_revision() -> Optional[str]:
    for key in ("STOCKPULSE_REVISION", "GIT_COMMIT", "GITHUB_SHA"):
        value = (os.getenv(key) or "").strip()
        if value:
            return value[:64]
    try:
        root = Path(__file__).resolve().parents[2]
        head = root / ".git" / "HEAD"
        if not head.is_file():
            return None
        text = head.read_text(encoding="utf-8").strip()
        if text.startswith("ref:"):
            ref = text.split(":", 1)[1].strip()
            ref_path = root / ".git" / ref
            if ref_path.is_file():
                return ref_path.read_text(encoding="utf-8").strip()[:40]
            return ref
        return text[:40] or None
    except Exception:
        return None


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
        "repro_mode_enabled": bool(getattr(config, "repro_mode_enabled", False)),
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
            "versions": {
                k: v for k, v in snapshot["versions"].items() if k != "app_revision"
            },
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


def apply_repro_mode(config: Any) -> Dict[str, Any]:
    enabled = bool(getattr(config, "repro_mode_enabled", False))
    status: Dict[str, Any] = {
        "enabled": enabled,
        "seed_applied": False,
        "temperature_pinned": False,
        "seed": None,
        "numpy_seed_applied": False,
    }
    if not enabled:
        return status
    seed = getattr(config, "repro_seed", None)
    if seed is None:
        seed = 0
    try:
        seed_int = int(seed)
    except (TypeError, ValueError):
        seed_int = 0
    status["seed"] = seed_int
    try:
        random.seed(seed_int)
        status["seed_applied"] = True
    except Exception as exc:
        log_safe_exception(
            logger,
            "Failed to pin random.seed for repro mode",
            exc,
            error_code="analysis_repro_seed_failed",
            level=logging.WARNING,
        )
    try:
        import numpy as np  # type: ignore

        np.random.seed(seed_int)
        status["numpy_seed_applied"] = True
    except Exception:
        status["numpy_seed_applied"] = False
    try:
        current = float(getattr(config, "llm_temperature", 0.0) or 0.0)
        if current != 0.0:
            config.llm_temperature = 0.0
            status["temperature_pinned"] = True
            status["previous_llm_temperature"] = current
    except Exception as exc:
        log_safe_exception(
            logger,
            "Failed to pin llm_temperature for repro mode",
            exc,
            error_code="analysis_repro_temperature_failed",
            level=logging.WARNING,
        )
    return status


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
        self._lock = threading.RLock()

    def _run_dir(self, query_id: str, stock_code: str) -> Path:
        return self.root_dir / sanitize_run_key(query_id, stock_code)

    def _manifest_path(self, run_dir: Path) -> Path:
        return run_dir / "manifest.json"

    def _stage_path(self, run_dir: Path, stage: str) -> Path:
        safe = _SAFE_RUN_KEY.sub("_", stage).strip("._-") or "stage"
        return run_dir / "stages" / f"{safe}.json"

    def ensure_root(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)

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
        return AnalysisCheckpointManifest.from_dict(raw)

    def save_manifest(self, manifest: AnalysisCheckpointManifest) -> bool:
        run_dir = self._run_dir(manifest.query_id, manifest.stock_code)
        try:
            with self._lock:
                run_dir.mkdir(parents=True, exist_ok=True)
                (run_dir / "stages").mkdir(parents=True, exist_ok=True)
                manifest.updated_at = _utc_now_iso()
                self._manifest_path(run_dir).write_text(
                    json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            return True
        except OSError as exc:
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
        record = StageCheckpointRecord(
            stage=stage_name,
            status=status,
            payload=json.loads(stable_json_dumps(dict(payload))),
        )
        try:
            with self._lock:
                run_dir.mkdir(parents=True, exist_ok=True)
                (run_dir / "stages").mkdir(parents=True, exist_ok=True)
                self._stage_path(run_dir, stage_name).write_text(
                    json.dumps(asdict(record), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                if manifest is None:
                    manifest = self.load_manifest(query_id, stock_code) or AnalysisCheckpointManifest(
                        query_id=query_id,
                        stock_code=stock_code,
                    )
                if stage_name not in manifest.completed_stages:
                    manifest.completed_stages.append(stage_name)
                manifest.query_id = query_id
                manifest.stock_code = stock_code
                self.save_manifest(manifest)
            return manifest
        except OSError as exc:
            log_safe_exception(
                logger,
                "Failed to write analysis stage checkpoint",
                exc,
                error_code="analysis_checkpoint_stage_write_failed",
                level=logging.WARNING,
                context={"query_id": query_id, "stock_code": stock_code, "stage": stage_name},
            )
            return manifest

    def load_stage(
        self, query_id: str, stock_code: str, stage: str
    ) -> Optional[StageCheckpointRecord]:
        path = self._stage_path(self._run_dir(query_id, stock_code), stage)
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            return None
        if not isinstance(raw, dict):
            return None
        return StageCheckpointRecord(
            stage=str(raw.get("stage") or stage),
            status=str(raw.get("status") or "success"),
            payload=dict(raw.get("payload") or {}),
            completed_at=str(raw.get("completed_at") or _utc_now_iso()),
        )

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
    repro_status: Dict[str, Any] = field(default_factory=dict)
    manifest: Optional[AnalysisCheckpointManifest] = None
    restored_stages: List[str] = field(default_factory=list)
    consistency: str = "full_run"
    annotation: Dict[str, Any] = field(default_factory=dict)

    @property
    def completed_stages(self) -> Tuple[str, ...]:
        if self.manifest is None:
            return ()
        return tuple(self.manifest.completed_stages)

    def is_stage_complete(self, stage: str) -> bool:
        return stage in self.completed_stages

    def begin(self) -> "AnalysisStageCheckpointSession":
        if not self.enabled:
            self.consistency = "checkpoint_disabled"
            self._refresh_annotation(resumed=False)
            return self
        if self.force_full:
            self.store.invalidate(self.query_id, self.stock_code, "force_full_rerun", delete=True)
            self.manifest = AnalysisCheckpointManifest(
                query_id=self.query_id,
                stock_code=self.stock_code,
                compatibility_fingerprint=self.compatibility_fingerprint,
                repro_snapshot=self.repro_snapshot,
                consistency="full_rerun_forced",
            )
            self.store.save_manifest(self.manifest)
            self.consistency = "full_rerun_forced"
            self._refresh_annotation(resumed=False)
            return self
        existing = self.store.load_manifest(self.query_id, self.stock_code)
        if existing is None:
            self.manifest = AnalysisCheckpointManifest(
                query_id=self.query_id,
                stock_code=self.stock_code,
                compatibility_fingerprint=self.compatibility_fingerprint,
                repro_snapshot=self.repro_snapshot,
            )
            self.store.save_manifest(self.manifest)
            self.consistency = "full_run"
            self._refresh_annotation(resumed=False)
            return self
        if existing.invalidated:
            self.store.delete_run(self.query_id, self.stock_code)
            self.manifest = AnalysisCheckpointManifest(
                query_id=self.query_id,
                stock_code=self.stock_code,
                compatibility_fingerprint=self.compatibility_fingerprint,
                repro_snapshot=self.repro_snapshot,
            )
            self.store.save_manifest(self.manifest)
            self.consistency = "full_run"
            self._refresh_annotation(resumed=False, note="prior_invalidated")
            return self
        if existing.compatibility_fingerprint != self.compatibility_fingerprint:
            reason = "compatibility_fingerprint_mismatch"
            self.store.invalidate(self.query_id, self.stock_code, reason, delete=True)
            self.manifest = AnalysisCheckpointManifest(
                query_id=self.query_id,
                stock_code=self.stock_code,
                compatibility_fingerprint=self.compatibility_fingerprint,
                repro_snapshot=self.repro_snapshot,
                consistency="full_rerun_incompatible",
                invalidate_reason=reason,
            )
            self.store.save_manifest(self.manifest)
            self.consistency = "full_rerun_incompatible"
            self._refresh_annotation(resumed=False, note=reason)
            logger.info(
                "Analysis checkpoint invalidated for %s (%s): %s",
                self.stock_code,
                self.query_id,
                reason,
            )
            return self
        existing.resumed = True
        existing.resume_count = int(existing.resume_count or 0) + 1
        existing.repro_snapshot = self.repro_snapshot
        existing.compatibility_fingerprint = self.compatibility_fingerprint
        existing.consistency = "exact_replay"
        self.manifest = existing
        self.store.save_manifest(self.manifest)
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
        self.manifest = self.store.save_stage(
            query_id=self.query_id,
            stock_code=self.stock_code,
            stage=stage,
            payload=payload,
            status=status,
            manifest=self.manifest,
        )
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
        self.store.delete_run(self.query_id, self.stock_code)
        self.manifest = None
        self._refresh_annotation(resumed=bool(self.restored_stages), completed=True)

    def fail_keep(self) -> None:
        self._refresh_annotation(resumed=bool(self.restored_stages), completed=False)

    def metadata_for_snapshot(self) -> Dict[str, Any]:
        return {
            "checkpoint": dict(self.annotation),
            "run_configuration": dict(self.repro_snapshot),
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
    store: Optional[AnalysisStageCheckpointStore] = None,
) -> AnalysisStageCheckpointSession:
    enabled = bool(getattr(config, "analysis_checkpoint_enabled", True))
    force = bool(force_full) or bool(getattr(config, "analysis_checkpoint_force_full", False))
    root = getattr(config, "analysis_checkpoint_dir", None) or "./data/checkpoints"
    ttl = int(getattr(config, "analysis_checkpoint_ttl_hours", 24) or 24)
    if store is None:
        store = AnalysisStageCheckpointStore(root, ttl_hours=ttl)
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
    repro_status = (
        apply_repro_mode(config)
        if bool(getattr(config, "repro_mode_enabled", False))
        else {"enabled": False}
    )
    seed = repro_status.get("seed")
    if seed is None:
        seed = getattr(config, "repro_seed", None)
    record_config = bool(getattr(config, "repro_record_config", True))
    if record_config or enabled or bool(getattr(config, "repro_mode_enabled", False)):
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
        repro_status=repro_status,
    )
    return session.begin()


def agent_stage_name(stage: str) -> str:
    return f"{AGENT_STAGE_NAMESPACE}.{stage}"


def pipeline_stage_name(stage: str) -> str:
    return f"{PIPELINE_STAGE_NAMESPACE}.{stage}"


def restore_agent_context_from_session(
    session: AnalysisStageCheckpointSession, ctx: Any
) -> List[str]:
    restored: List[str] = []
    if not session.enabled:
        return restored
    for stage in session.completed_stages:
        if not stage.startswith(f"{AGENT_STAGE_NAMESPACE}."):
            continue
        bare = stage.split(".", 1)[1]
        payload = session.load_stage_payload(stage)
        if not payload:
            session.store.invalidate(
                session.query_id,
                session.stock_code,
                f"missing_stage_payload:{stage}",
                delete=True,
            )
            session.manifest = None
            session.restored_stages = []
            session.consistency = "full_rerun_corrupt_checkpoint"
            session._refresh_annotation(resumed=False, note=f"missing_stage_payload:{stage}")
            return []
        for opinion_raw in payload.get("opinions") or []:
            if isinstance(opinion_raw, Mapping):
                opinion = deserialize_agent_opinion(opinion_raw)
                existing_names = {
                    getattr(item, "agent_name", None) for item in getattr(ctx, "opinions", [])
                }
                if opinion.agent_name and opinion.agent_name in existing_names:
                    continue
                ctx.add_opinion(opinion)
        for flag in payload.get("risk_flags") or []:
            if isinstance(flag, Mapping):
                ctx.risk_flags.append(dict(flag))
        data_patch = payload.get("data") or {}
        if isinstance(data_patch, Mapping):
            for key, value in data_patch.items():
                ctx.set_data(key, value)
        meta_patch = payload.get("meta") or {}
        if isinstance(meta_patch, Mapping):
            for key, value in meta_patch.items():
                if str(key).startswith("_"):
                    continue
                ctx.meta[key] = value
        restored.append(bare)
    if restored:
        ctx.meta["_checkpoint_restored_agent_stages"] = list(restored)
        session.restored_stages = [
            agent_stage_name(name) for name in restored
        ] + [
            stage
            for stage in session.completed_stages
            if stage.startswith(f"{PIPELINE_STAGE_NAMESPACE}.")
        ]
        session.consistency = "exact_replay"
        session._refresh_annotation(resumed=True)
    return restored


def capture_agent_stage_payload(
    ctx: Any,
    *,
    stage_name: str,
    stage_result: Any = None,
) -> Dict[str, Any]:
    all_opinions = [
        serialize_agent_opinion(item) for item in (getattr(ctx, "opinions", []) or [])
    ]
    stage_opinions = [
        item
        for item in all_opinions
        if not item.get("agent_name")
        or item.get("agent_name") == stage_name
        or str(item.get("agent_name")).startswith(f"{stage_name}_")
        or stage_name in str(item.get("agent_name") or "")
    ]
    data_keys = (
        "final_response_text",
        "dashboard",
        "strategy_results",
        "deliberation_summary",
        "agent_disagreement_summary",
    )
    data_out: Dict[str, Any] = {}
    for key in data_keys:
        value = ctx.get_data(key) if hasattr(ctx, "get_data") else (getattr(ctx, "data", {}) or {}).get(key)
        if value is not None:
            data_out[key] = value
    meta_keys = (
        "skills_requested",
        "strategies_requested",
        "report_language",
        "invalid_opinions",
        "skill_scheduler",
        "critic",
        "risk_gate_result",
        "agent_disagreement_explanation",
    )
    meta_out: Dict[str, Any] = {}
    meta = getattr(ctx, "meta", {}) or {}
    for key in meta_keys:
        if key in meta:
            meta_out[key] = meta[key]
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
        "opinions": all_opinions,
        "stage_opinions": stage_opinions,
        "risk_flags": list(getattr(ctx, "risk_flags", []) or []),
        "data": json.loads(stable_json_dumps(data_out)),
        "meta": json.loads(stable_json_dumps(meta_out)),
        "stage_result": result_meta,
    }


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
