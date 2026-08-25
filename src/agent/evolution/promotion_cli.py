# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Dry-run agent promotion sidecar (Issue #1093 first slice).

Opt-in library behind ``scripts/agent_evolve.py``. Invocation is the only gate:
there is no config-registry key, scheduler, HTTP surface, or auto-promote flag.

Proposals are JSON sidecars. They embed an existing sandbox
``PromotionReceipt`` (``auto_promote`` hard false) plus offline eval scores.
Approve/reject flip sidecar ``review_state`` only. This module never:

* writes ``strategies/``, plugin catalogs, or Skill source files
* imports or calls SkillRouter / AgentOrchestrator
* emits EvolutionEvent rows
* introduces an auto-promote environment key
* grants production routing or Skill activation
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.agent.sandbox.clock import FakeClock
from src.agent.sandbox.context import SandboxContext
from src.agent.sandbox.policy import SANDBOX_ISOLATION_POLICY
from src.agent.sandbox.promotion import PromotionReceipt, build_promotion_receipt

try:  # POSIX process lock.
    import fcntl
except ImportError:  # pragma: no cover - Windows uses msvcrt below.
    fcntl = None

try:  # Windows process lock.
    import msvcrt
except ImportError:  # pragma: no cover - POSIX uses fcntl above.
    msvcrt = None


PROPOSAL_SCHEMA_VERSION = "agent-promotion-proposal-v1"
DEFAULT_STORE_DIRNAME = "artifacts/agent_evolve"
PROPOSAL_ID_PATTERN = re.compile(r"^promo-[0-9a-f]{16}$")
MAX_PROPOSAL_BYTES = 512 * 1024
MAX_SOURCE_BYTES = 262_144
MAX_EPISODE_BYTES = 16 * 1024 * 1024
MAX_PROPOSALS = 4096
MAX_LESSONS = 32
REVIEW_STATES = frozenset({"proposed", "scored", "approved", "rejected"})
CANDIDATE_KINDS = frozenset({"experimental_skill_id", "router_rule"})
DEFAULT_RECEIPT_NOW = "2026-08-01T00:00:00Z"
LOCK_FILENAME = ".store.lock"
REVIEW_NOTE = (
    "Approve flips sidecar review_state only. It does not activate SkillRouter, "
    "catalog skills, router rules, or auto-promote."
)
ROLLBACK_CONDITION = (
    "Leave the experimental candidate unactivated and revert any Skill-id pin. "
    "This sidecar never rewrites Agent Soul or strategies/*.yaml."
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FORBIDDEN_STORE_RELATIVE = (
    "strategies",
    "src/plugins",
    "src/agent/skills",
    "plugins",
    "tests/fixtures",
)
_KNOWN_LESSON_KINDS = frozenset(
    {
        "evidence_gap",
        "overclaim",
        "overconfidence",
        "tool_failure",
        "risk_omission",
        "format_violation",
        "regime_shift",
        "horizon_mismatch",
        "other",
    }
)


class PromotionProposalError(ValueError):
    """Fail-closed promotion sidecar contract error."""


def default_store_dir() -> Path:
    return Path(DEFAULT_STORE_DIRNAME)


def _utc_iso(clock: Optional[Any] = None) -> str:
    if clock is not None:
        iso = getattr(clock, "isoformat", None)
        if callable(iso):
            return str(iso())
        now = getattr(clock, "now", None)
        if isinstance(now, datetime):
            return now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        if isinstance(clock, datetime):
            return clock.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        text = str(clock).strip()
        if text:
            return text
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def assert_store_dir_safe(store_dir: Path | str) -> Path:
    """Reject store paths that could be picked up as skills or fixtures."""
    resolved = Path(store_dir).expanduser().resolve()
    for relative in _FORBIDDEN_STORE_RELATIVE:
        forbidden = (_REPO_ROOT / relative).resolve()
        if resolved == forbidden or _is_relative_to(resolved, forbidden):
            raise PromotionProposalError(
                f"store_dir must not be inside {relative}: {resolved}"
            )
    return resolved


def _proposal_path(store_dir: Path, proposal_id: str) -> Path:
    if not PROPOSAL_ID_PATTERN.fullmatch(proposal_id):
        raise PromotionProposalError(f"invalid proposal_id: {proposal_id!r}")
    return store_dir / f"{proposal_id}.json"


def _canonical_lessons(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise PromotionProposalError("source lessons must be a non-empty array")
    if len(raw) > MAX_LESSONS:
        raise PromotionProposalError(f"source lessons exceed {MAX_LESSONS} items")
    out: List[Dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise PromotionProposalError(f"lessons[{index}] must be an object")
        kind = str(item.get("kind") or "").strip()
        if kind not in _KNOWN_LESSON_KINDS:
            raise PromotionProposalError(
                f"lessons[{index}].kind is not a known lesson kind: {kind!r}"
            )
        payload: Dict[str, Any] = {"kind": kind}
        severity = str(item.get("severity") or "").strip()
        if severity:
            if severity not in {"low", "medium", "high"}:
                raise PromotionProposalError(
                    f"lessons[{index}].severity is invalid: {severity!r}"
                )
            payload["severity"] = severity
        claim_ref = str(item.get("claim_ref") or "").strip()
        if claim_ref:
            payload["claim_ref"] = claim_ref[:128]
        remedy = str(item.get("remedy") or "").strip()
        if remedy:
            payload["remedy"] = remedy[:1000]
        out.append(payload)
    return out


def _load_json_file(path: Path, *, limit: int, label: str) -> Any:
    if not path.is_file():
        raise PromotionProposalError(f"{label} is not a file: {path}")
    size = path.stat().st_size
    if size > limit:
        raise PromotionProposalError(f"{label} exceeds {limit} bytes: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PromotionProposalError(f"{label} is not valid JSON: {path}") from exc
    return payload


def _load_fixture_case(path: Path) -> Dict[str, Any]:
    payload = _load_json_file(path, limit=MAX_SOURCE_BYTES, label="fixture")
    if not isinstance(payload, Mapping):
        raise PromotionProposalError("fixture must be a JSON object")
    case = dict(payload)
    case_id = str(case.get("id") or path.stem).strip()
    if not case_id:
        raise PromotionProposalError("fixture case id is required")
    case["id"] = case_id
    return case


def _load_episode_lessons(path: Path) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    payload = _load_json_file(path, limit=MAX_EPISODE_BYTES, label="episodes")
    if isinstance(payload, list):
        episodes = payload
    elif isinstance(payload, Mapping) and isinstance(payload.get("episodes"), list):
        episodes = payload["episodes"]
    else:
        raise PromotionProposalError(
            'episodes JSON must be a list or {"episodes": [...]}'
        )
    lessons: List[Dict[str, Any]] = []
    first_run = "episode-lessons"
    for index, item in enumerate(episodes):
        if not isinstance(item, Mapping):
            raise PromotionProposalError(f"episodes[{index}] must be an object")
        if index == 0:
            first_run = str(item.get("run_id") or item.get("episode_id") or first_run)
        raw_lessons = item.get("lessons")
        if isinstance(raw_lessons, list):
            lessons.extend(raw_lessons)
    if not lessons:
        raise PromotionProposalError("episodes JSON contains no lessons")
    case_id = f"episode:{first_run}"
    case = {
        "id": case_id,
        "profile": "episode_lessons",
        "lessons": lessons,
        "claims": [],
        "actuals": {},
        "resolution": {"outcome": "miss"},
        "expected": {
            "outcome": "miss",
            "require_lessons": True,
            "forbid_soul_mutation_claim": True,
        },
        "episode": {
            "run_id": first_run,
            "trajectory_summary": [],
        },
    }
    return case_id, _canonical_lessons(lessons), case


def _proposal_id_for(kind: str, case_id: str, lessons: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {"kind": kind, "case_id": case_id, "lessons": list(lessons)},
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"promo-{digest}"


def _experimental_id(kind: str, case_id: str, lessons: Sequence[Mapping[str, Any]]) -> str:
    lesson_kind = str(lessons[0].get("kind") or "other")
    prefix = "experimental-skill" if kind == "experimental_skill_id" else "experimental-route"
    return f"{prefix}:{lesson_kind}:{case_id}"


def assert_receipt_non_activating(receipt: Mapping[str, Any] | PromotionReceipt) -> None:
    """Fail closed if a sidecar or live policy would grant production promotion."""
    if SANDBOX_ISOLATION_POLICY.get("auto_promote_to_production") is not False:
        raise PromotionProposalError(
            "sandbox auto_promote_to_production must remain false"
        )
    if isinstance(receipt, PromotionReceipt):
        body = receipt.to_dict()
    else:
        body = dict(receipt)
    if body.get("auto_promote") is not False:
        raise PromotionProposalError(
            "promotion receipt auto_promote must remain false"
        )
    if body.get("review_required") is not True:
        raise PromotionProposalError("promotion receipt review_required must remain true")


def _build_receipt(
    *,
    proposal_id: str,
    experimental_id: str,
    case: Mapping[str, Any],
    clock: Optional[Any] = None,
) -> Dict[str, Any]:
    snapshot = {
        "proposal_id": proposal_id,
        "experimental_id": experimental_id,
        "case_id": str(case.get("id") or ""),
    }
    actuals = case.get("actuals") if isinstance(case.get("actuals"), Mapping) else {}
    if actuals:
        snapshot["actuals"] = dict(actuals)
    fixed_now = DEFAULT_RECEIPT_NOW
    if clock is not None:
        iso = getattr(clock, "isoformat", None)
        if callable(iso):
            fixed_now = str(iso())
    context = SandboxContext.create(
        clock=FakeClock.fixed(fixed_now),
        data_mode="snapshot",
        snapshot=snapshot,
        agent_variant_id=experimental_id[:160],
        sandbox_run_id=proposal_id,
        source_data_window={"proposal_id": proposal_id, "dry_run": True},
    )
    receipt = build_promotion_receipt(
        context=context,
        rollback_condition=ROLLBACK_CONDITION,
        metadata={
            "promotion_cli": True,
            "proposal_id": proposal_id,
            "experimental_id": experimental_id,
        },
    )
    assert_receipt_non_activating(receipt)
    return receipt.to_dict()


def _validate_proposal_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    if payload.get("schema_version") != PROPOSAL_SCHEMA_VERSION:
        raise PromotionProposalError(
            f"unsupported proposal schema: {payload.get('schema_version')!r}"
        )
    proposal_id = str(payload.get("proposal_id") or "").strip()
    if not PROPOSAL_ID_PATTERN.fullmatch(proposal_id):
        raise PromotionProposalError(f"invalid proposal_id: {proposal_id!r}")
    review_state = str(payload.get("review_state") or "").strip()
    if review_state not in REVIEW_STATES:
        raise PromotionProposalError(f"invalid review_state: {review_state!r}")
    receipt = payload.get("promotion_receipt")
    if not isinstance(receipt, Mapping):
        raise PromotionProposalError("proposal is missing promotion_receipt")
    assert_receipt_non_activating(receipt)
    candidate = payload.get("candidate")
    if not isinstance(candidate, Mapping):
        raise PromotionProposalError("proposal is missing candidate")
    kind = str(candidate.get("kind") or "").strip()
    if kind not in CANDIDATE_KINDS:
        raise PromotionProposalError(f"unsupported candidate kind: {kind!r}")
    return dict(payload)


@dataclass(frozen=True)
class PromotionCommandResult:
    """JSON-serializable CLI/service result."""

    operation: str
    proposal: Dict[str, Any]
    idempotent: bool = False

    def to_dict(self) -> Dict[str, Any]:
        body = dict(self.proposal)
        body["operation"] = self.operation
        body["idempotent"] = self.idempotent
        return body


class AgentPromotionService:
    """File-backed propose/score/status/approve/reject sidecar."""

    def __init__(
        self,
        store_dir: Path | str | None = None,
        *,
        clock: Optional[Any] = None,
    ) -> None:
        self.store_dir = assert_store_dir_safe(store_dir or default_store_dir())
        self._clock = clock
        self._lock = threading.RLock()

    def propose(
        self,
        *,
        fixture: Path | str | None = None,
        case_id: str | None = None,
        episodes: Path | str | None = None,
        candidate_kind: str = "experimental_skill_id",
    ) -> PromotionCommandResult:
        kind = str(candidate_kind or "").strip()
        if kind not in CANDIDATE_KINDS:
            raise PromotionProposalError(f"unsupported candidate kind: {kind!r}")
        source_case, lessons, resolved_case_id, source_type = self._load_source(
            fixture=fixture,
            case_id=case_id,
            episodes=episodes,
        )
        proposal_id = _proposal_id_for(kind, resolved_case_id, lessons)
        experimental_id = _experimental_id(kind, resolved_case_id, lessons)
        now = _utc_iso(self._clock)
        payload = {
            "schema_version": PROPOSAL_SCHEMA_VERSION,
            "proposal_id": proposal_id,
            "review_state": "proposed",
            "candidate": {
                "kind": kind,
                "experimental_id": experimental_id,
                "lessons": lessons,
                "source": {
                    "type": source_type,
                    "case_id": resolved_case_id,
                },
            },
            "eval_inputs": {"case_ids": [resolved_case_id]},
            "source_case": source_case,
            "eval_scores": None,
            "promotion_receipt": _build_receipt(
                proposal_id=proposal_id,
                experimental_id=experimental_id,
                case=source_case,
                clock=self._clock,
            ),
            "review": {
                "state": "proposed",
                "note": REVIEW_NOTE,
            },
            "created_at": now,
            "updated_at": now,
        }
        _validate_proposal_payload(payload)
        with self._exclusive_lock():
            existing = self._read_unlocked(proposal_id, missing_ok=True)
            if existing is not None:
                return PromotionCommandResult(
                    operation="propose",
                    proposal=existing,
                    idempotent=True,
                )
            self._write_unlocked(payload)
        return PromotionCommandResult(operation="propose", proposal=payload)

    def score(self, proposal_id: str) -> PromotionCommandResult:
        from src.services.prediction_eval_service import (
            PREDICTION_EVAL_ENGINE_VERSION,
            PREDICTION_EVAL_SCHEMA_VERSION,
            evaluate_prediction_case,
            score_only_prediction_view,
        )

        with self._exclusive_lock():
            current = self._read_unlocked(proposal_id)
            source_case = current.get("source_case")
            if not isinstance(source_case, Mapping):
                raise PromotionProposalError(
                    f"proposal {proposal_id} is missing source_case"
                )
            case_result = evaluate_prediction_case(source_case)
            compact = score_only_prediction_view(
                {
                    "schema_version": PREDICTION_EVAL_SCHEMA_VERSION,
                    "engine_version": PREDICTION_EVAL_ENGINE_VERSION,
                    "aggregate": {
                        "cases": 1,
                        "checks_passed": case_result.get("passed"),
                        "checks_total": case_result.get("total"),
                        "score": case_result.get("score"),
                    },
                    "cases": [case_result],
                }
            )
            scores = {
                "schema_version": PREDICTION_EVAL_SCHEMA_VERSION,
                "engine_version": PREDICTION_EVAL_ENGINE_VERSION,
                "live_agent_run": False,
                "case": case_result,
                "compact": compact,
            }
            next_state = current["review_state"]
            if next_state in {"proposed", "scored"}:
                next_state = "scored"
            updated = dict(current)
            updated["eval_scores"] = scores
            updated["review_state"] = next_state
            updated["review"] = {
                **dict(current.get("review") or {}),
                "state": next_state,
                "note": REVIEW_NOTE,
            }
            updated["updated_at"] = _utc_iso(self._clock)
            _validate_proposal_payload(updated)
            self._write_unlocked(updated)
            idempotent = (
                current.get("review_state") == "scored"
                and current.get("eval_scores") == scores
            )
        return PromotionCommandResult(
            operation="score",
            proposal=updated,
            idempotent=idempotent,
        )

    def status(self, proposal_id: Optional[str] = None) -> Dict[str, Any]:
        with self._exclusive_lock():
            if proposal_id:
                payload = self._read_unlocked(proposal_id)
                return {"count": 1, "proposals": [self._public_status(payload)]}
            items = []
            if self.store_dir.is_dir():
                paths = sorted(self.store_dir.glob("promo-*.json"))
                if len(paths) > MAX_PROPOSALS:
                    raise PromotionProposalError("store exceeds the proposal limit")
                for path in paths:
                    try:
                        payload = self._read_path_unlocked(path)
                        items.append(self._public_status(payload))
                    except PromotionProposalError as exc:
                        items.append(
                            {
                                "proposal_id": path.stem,
                                "error": str(exc),
                            }
                        )
            return {"count": len(items), "proposals": items}

    def approve(self, proposal_id: str) -> PromotionCommandResult:
        return self._set_review_state(proposal_id, "approved", operation="approve")

    def reject(self, proposal_id: str) -> PromotionCommandResult:
        return self._set_review_state(proposal_id, "rejected", operation="reject")

    def _set_review_state(
        self,
        proposal_id: str,
        target: str,
        *,
        operation: str,
    ) -> PromotionCommandResult:
        with self._exclusive_lock():
            current = self._read_unlocked(proposal_id)
            assert_receipt_non_activating(current["promotion_receipt"])
            current_state = str(current.get("review_state") or "")
            if current_state == target:
                return PromotionCommandResult(
                    operation=operation,
                    proposal=current,
                    idempotent=True,
                )
            if current_state == "approved" and target == "rejected":
                raise PromotionProposalError(
                    f"proposal {proposal_id} is already approved"
                )
            if current_state == "rejected" and target == "approved":
                raise PromotionProposalError(
                    f"proposal {proposal_id} is already rejected"
                )
            if target == "approved" and current_state not in {"scored", "approved"}:
                raise PromotionProposalError(
                    f"approve requires a scored proposal: {proposal_id}"
                )
            updated = dict(current)
            updated["review_state"] = target
            updated["review"] = {
                **dict(current.get("review") or {}),
                "state": target,
                "note": REVIEW_NOTE,
            }
            receipt = dict(updated["promotion_receipt"])
            receipt["auto_promote"] = False
            receipt["review_required"] = True
            updated["promotion_receipt"] = receipt
            updated["updated_at"] = _utc_iso(self._clock)
            _validate_proposal_payload(updated)
            self._write_unlocked(updated)
        return PromotionCommandResult(operation=operation, proposal=updated)

    def _load_source(
        self,
        *,
        fixture: Path | str | None,
        case_id: str | None,
        episodes: Path | str | None,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], str, str]:
        selected = [item for item in (fixture, case_id, episodes) if item]
        if len(selected) != 1:
            raise PromotionProposalError(
                "exactly one of fixture, case_id, or episodes is required"
            )
        if episodes is not None:
            resolved_id, lessons, case = _load_episode_lessons(Path(episodes))
            return case, lessons, resolved_id, "episode_lessons"
        if fixture is not None:
            case = _load_fixture_case(Path(fixture))
            lessons = _canonical_lessons(case.get("lessons"))
            return case, lessons, str(case["id"]), "prediction_eval_fixture"
        from src.services.prediction_eval_service import load_prediction_eval_cases

        wanted = str(case_id or "").strip()
        if not wanted:
            raise PromotionProposalError("case_id is required")
        for case in load_prediction_eval_cases():
            if str(case.get("id") or "") == wanted:
                lessons = _canonical_lessons(case.get("lessons"))
                return dict(case), lessons, wanted, "prediction_eval_fixture"
        raise PromotionProposalError(f"unknown prediction eval case_id: {wanted!r}")

    def _public_status(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        candidate = payload.get("candidate") if isinstance(payload.get("candidate"), Mapping) else {}
        receipt = (
            payload.get("promotion_receipt")
            if isinstance(payload.get("promotion_receipt"), Mapping)
            else {}
        )
        scores = payload.get("eval_scores")
        compact = None
        if isinstance(scores, Mapping):
            compact = scores.get("compact") or {
                "score": (scores.get("case") or {}).get("score")
                if isinstance(scores.get("case"), Mapping)
                else None
            }
        return {
            "proposal_id": payload.get("proposal_id"),
            "review_state": payload.get("review_state"),
            "candidate_kind": candidate.get("kind"),
            "experimental_id": candidate.get("experimental_id"),
            "auto_promote": receipt.get("auto_promote"),
            "review_required": receipt.get("review_required"),
            "eval_scores": compact,
            "updated_at": payload.get("updated_at"),
            "review_note": REVIEW_NOTE,
        }

    def _exclusive_lock(self):
        store_dir = self.store_dir

        class _Guard:
            def __enter__(inner_self):
                store_dir.mkdir(parents=True, exist_ok=True)
                self._lock.acquire()
                try:
                    inner_self._handle = (store_dir / LOCK_FILENAME).open("a+b")
                    if fcntl is not None:
                        fcntl.flock(inner_self._handle.fileno(), fcntl.LOCK_EX)
                    elif msvcrt is not None:  # pragma: no cover - Windows only.
                        inner_self._handle.seek(0, os.SEEK_END)
                        if inner_self._handle.tell() == 0:
                            inner_self._handle.write(b"\0")
                            inner_self._handle.flush()
                        inner_self._handle.seek(0)
                        msvcrt.locking(inner_self._handle.fileno(), msvcrt.LK_LOCK, 1)
                except OSError:
                    self._lock.release()
                    raise
                return self

            def __exit__(inner_self, exc_type, exc, tb):
                try:
                    if fcntl is not None:
                        fcntl.flock(inner_self._handle.fileno(), fcntl.LOCK_UN)
                    elif msvcrt is not None:  # pragma: no cover - Windows only.
                        inner_self._handle.seek(0)
                        msvcrt.locking(inner_self._handle.fileno(), msvcrt.LK_UNLCK, 1)
                finally:
                    inner_self._handle.close()
                    self._lock.release()
                return False

        return _Guard()

    def _read_unlocked(
        self,
        proposal_id: str,
        *,
        missing_ok: bool = False,
    ) -> Optional[Dict[str, Any]]:
        path = _proposal_path(self.store_dir, proposal_id)
        if not path.is_file():
            if missing_ok:
                return None
            raise PromotionProposalError(f"proposal not found: {proposal_id}")
        return self._read_path_unlocked(path)

    def _read_path_unlocked(self, path: Path) -> Dict[str, Any]:
        if path.stat().st_size > MAX_PROPOSAL_BYTES:
            raise PromotionProposalError(f"proposal exceeds size limit: {path.name}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PromotionProposalError(f"proposal is unreadable: {path.name}") from exc
        if not isinstance(payload, Mapping):
            raise PromotionProposalError(f"proposal must be a JSON object: {path.name}")
        return _validate_proposal_payload(payload)

    def _write_unlocked(self, payload: Mapping[str, Any]) -> None:
        proposal_id = str(payload.get("proposal_id") or "")
        path = _proposal_path(self.store_dir, proposal_id)
        encoded = json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        if len(encoded.encode("utf-8")) > MAX_PROPOSAL_BYTES:
            raise PromotionProposalError("proposal exceeds size limit")
        self.store_dir.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{proposal_id}.",
            suffix=".tmp",
            dir=str(self.store_dir),
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
            if os.name != "nt":
                directory_fd = os.open(self.store_dir, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        except OSError:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
            raise
        finally:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
