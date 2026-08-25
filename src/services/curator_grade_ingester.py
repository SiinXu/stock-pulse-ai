# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""CLI-invoked eval-fixture curator-grade ingester (Issue #1096).

Invocation is the only gate: there is no config-registry key and no scheduler.
Labels are written to the ``agent_episode_curator_grades`` sidecar. Append-only
``agent_episodes`` are never updated. Missing grades stay absent; unknown tokens
fail closed before any write.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from src.repositories.agent_curator_grade_repo import AgentCuratorGradeRepository
from src.repositories.agent_episode_repo import AgentEpisodeRepository
from src.schemas.agent_episode import AGENT_EPISODE_MAX_PAGE_SIZE
from src.schemas.curator_grade import (
    CURATOR_GRADE_FIXTURE_VERSION,
    normalize_curator_grade,
)
from src.storage import DatabaseManager


MAX_FIXTURE_BYTES = 262_144


@dataclass(frozen=True)
class CuratorGradeIngestSummary:
    """Deterministic counts for one CLI invocation."""

    fixture: str
    scanned: int = 0
    labeled: int = 0
    updated: int = 0
    skipped_missing_grade: int = 0
    skipped_missing_episode: int = 0
    dry_run: bool = False
    noop: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class _MutableCounts:
    scanned: int = 0
    labeled: int = 0
    updated: int = 0
    skipped_missing_grade: int = 0
    skipped_missing_episode: int = 0


@dataclass(frozen=True)
class _PreparedGrade:
    episode_id: str
    fixture_run_id: Optional[str]
    manual_grade: Optional[str]


def _load_fixture_records(path: Path) -> List[Mapping[str, Any]]:
    if not path.is_file():
        raise ValueError(f"fixture is not a file: {path}")
    size = path.stat().st_size
    if size > MAX_FIXTURE_BYTES:
        raise ValueError(
            f"fixture exceeds {MAX_FIXTURE_BYTES} bytes: {path}"
        )
    raw = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"fixture is not valid JSON: {path}") from exc
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        version = payload.get("version")
        if version is not None and str(version).strip() != CURATOR_GRADE_FIXTURE_VERSION:
            raise ValueError(
                f"unsupported curator-grade fixture version: {version!r}"
            )
        records = payload.get("grades")
        if records is None:
            raise ValueError("fixture object must include a grades array")
    else:
        raise ValueError("fixture must be a JSON object or array")
    if not isinstance(records, list):
        raise ValueError("fixture grades must be an array")
    if len(records) > AGENT_EPISODE_MAX_PAGE_SIZE:
        raise ValueError(
            f"fixture exceeds {AGENT_EPISODE_MAX_PAGE_SIZE} grade records"
        )
    prepared: List[Mapping[str, Any]] = []
    for index, item in enumerate(records):
        if not isinstance(item, Mapping):
            raise ValueError(f"fixture grades[{index}] must be an object")
        prepared.append(item)
    return prepared


def _prepare_record(item: Mapping[str, Any], *, index: int) -> _PreparedGrade:
    episode_id = str(item.get("episode_id") or "").strip()
    if not episode_id:
        raise ValueError(f"fixture grades[{index}].episode_id is required")
    raw_run = item.get("run_id")
    fixture_run_id: Optional[str]
    if raw_run is None:
        fixture_run_id = None
    elif isinstance(raw_run, bool) or not isinstance(raw_run, str):
        raise ValueError(f"fixture grades[{index}].run_id must be a string")
    else:
        fixture_run_id = raw_run.strip() or None
    if "manual_grade" not in item:
        return _PreparedGrade(
            episode_id=episode_id,
            fixture_run_id=fixture_run_id,
            manual_grade=None,
        )
    try:
        grade = normalize_curator_grade(item.get("manual_grade"))  # type: ignore[arg-type]
    except ValueError as exc:
        raise ValueError(f"fixture grades[{index}]: {exc}") from exc
    return _PreparedGrade(
        episode_id=episode_id,
        fixture_run_id=fixture_run_id,
        manual_grade=grade,
    )


class CuratorGradeIngester:
    """Batch-ingest allowlisted curator grades. Invocation is the gate."""

    def __init__(
        self,
        *,
        db_manager: Optional[DatabaseManager] = None,
        episode_repo: Optional[AgentEpisodeRepository] = None,
        label_repo: Optional[AgentCuratorGradeRepository] = None,
    ) -> None:
        self._db = db_manager
        self._episode_repo = episode_repo
        self._label_repo = label_repo

    def _episodes(self) -> AgentEpisodeRepository:
        if self._episode_repo is None:
            self._episode_repo = AgentEpisodeRepository(self._db)
        return self._episode_repo

    def _labels(self) -> AgentCuratorGradeRepository:
        if self._label_repo is None:
            self._label_repo = AgentCuratorGradeRepository(self._db)
        return self._label_repo

    def ingest(
        self,
        *,
        fixture: Any,
        episode_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> CuratorGradeIngestSummary:
        path = Path(fixture)
        records = _load_fixture_records(path)
        prepared: List[_PreparedGrade] = [
            _prepare_record(item, index=index) for index, item in enumerate(records)
        ]
        filter_key = str(episode_id or "").strip() or None
        if filter_key:
            prepared = [item for item in prepared if item.episode_id == filter_key]
        counts = _MutableCounts()
        if not prepared:
            return CuratorGradeIngestSummary(
                fixture=str(path),
                dry_run=dry_run,
                noop=True,
            )
        self._reject_run_id_mismatches(prepared)
        for item in prepared:
            counts.scanned += 1
            self._ingest_one(item, dry_run=dry_run, counts=counts)
        return CuratorGradeIngestSummary(
            fixture=str(path),
            scanned=counts.scanned,
            labeled=counts.labeled,
            updated=counts.updated,
            skipped_missing_grade=counts.skipped_missing_grade,
            skipped_missing_episode=counts.skipped_missing_episode,
            dry_run=dry_run,
            noop=counts.labeled == 0 and counts.updated == 0,
        )

    def _reject_run_id_mismatches(self, prepared: Sequence[_PreparedGrade]) -> None:
        """Fail closed on identity mismatch before any sidecar write."""
        for item in prepared:
            if item.manual_grade is None or item.fixture_run_id is None:
                continue
            episode = self._episodes().get_by_episode_id(item.episode_id)
            if episode is None:
                continue
            run_id = str(episode.run_id or "").strip()
            if run_id and item.fixture_run_id != run_id:
                raise ValueError(
                    "fixture run_id does not match episode "
                    f"{item.episode_id}: {item.fixture_run_id!r} vs {run_id!r}"
                )

    def _ingest_one(
        self,
        item: _PreparedGrade,
        *,
        dry_run: bool,
        counts: _MutableCounts,
    ) -> None:
        if item.manual_grade is None:
            counts.skipped_missing_grade += 1
            return
        episode = self._episodes().get_by_episode_id(item.episode_id)
        if episode is None:
            counts.skipped_missing_episode += 1
            return
        run_id = str(episode.run_id or "").strip()
        if not run_id:
            counts.skipped_missing_episode += 1
            return
        if item.fixture_run_id is not None and item.fixture_run_id != run_id:
            raise ValueError(
                "fixture run_id does not match episode "
                f"{item.episode_id}: {item.fixture_run_id!r} vs {run_id!r}"
            )
        existing = self._labels().get_by_episode_id(item.episode_id)
        if existing is not None and existing.manual_grade == item.manual_grade:
            return
        if dry_run:
            if existing is None:
                counts.labeled += 1
            else:
                counts.updated += 1
            return
        self._labels().upsert(
            episode_id=item.episode_id,
            run_id=run_id,
            manual_grade=item.manual_grade,
        )
        if existing is None:
            counts.labeled += 1
        else:
            counts.updated += 1
