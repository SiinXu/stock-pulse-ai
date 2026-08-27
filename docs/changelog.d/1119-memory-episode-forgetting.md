- [Added] Add deterministic per-symbol episode forgetting over existing `agent_episodes` rows, with clock-injectable transactional deletes, exact age/count boundaries, no-policy preservation, and metadata-only EvolutionEvent audit that fail-closes the delete (Refs #1119).
- [Changed] `AGENT_EPISODE_RETENTION_DAYS` and `AGENT_EPISODE_MAX_ROWS` now apply per-symbol after that symbol is appended; they are not table-wide caps, and unscoped `apply_retention` / `apply_capacity` fail closed (Refs #1119).
- [Fixed] Chunk per-symbol episode forget `DELETE ... id IN (...)` lists so they stay within SQLite bind limits while remaining one transaction with a single EvolutionEvent audit (Refs #1119).

