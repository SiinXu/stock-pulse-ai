# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Immutable fingerprints for supported pre-registry StockPulse databases."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable, Optional, Tuple

from sqlalchemy import inspect
from sqlalchemy.engine import Connection


@dataclass(frozen=True)
class LegacySchemaProfile:
    """One released schema that may be upgraded before a registry exists."""

    profile_id: str
    source_tag: str
    source_commit: str
    schema_digest: str
    source_profile_digest: str
    table_digests: Tuple[Tuple[str, str], ...]
    forbidden_tables: Tuple[str, ...]

    @property
    def required_tables(self) -> Tuple[str, ...]:
        return tuple(table_name for table_name, _digest in self.table_digests)


def sqlite_type_affinity(declared_type: str) -> str:
    """Return SQLite's deterministic type affinity for a declaration."""
    normalized = declared_type.upper()
    if "INT" in normalized:
        return "INTEGER"
    if any(token in normalized for token in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if "BLOB" in normalized or not normalized:
        return "BLOB"
    if any(token in normalized for token in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _normalize_sql(sql: object) -> Optional[str]:
    if sql is None:
        return None
    return str(sql).strip()


def _ddl_tokens(create_sql: str) -> Tuple[str, ...]:
    """Tokenize unquoted DDL so semantic table options can be inspected."""
    tokens = []
    token = []
    index = 0

    def finish_token() -> None:
        if token:
            tokens.append("".join(token).upper())
            token.clear()

    while index < len(create_sql):
        character = create_sql[index]
        following = create_sql[index + 1] if index + 1 < len(create_sql) else ""
        if character in ("'", '"', "`"):
            finish_token()
            quote = character
            index += 1
            while index < len(create_sql):
                if create_sql[index] == quote:
                    if index + 1 < len(create_sql) and create_sql[index + 1] == quote:
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            continue
        if character == "[":
            finish_token()
            closing = create_sql.find("]", index + 1)
            index = len(create_sql) if closing < 0 else closing + 1
            continue
        if character == "-" and following == "-":
            finish_token()
            newline = create_sql.find("\n", index + 2)
            index = len(create_sql) if newline < 0 else newline + 1
            continue
        if character == "/" and following == "*":
            finish_token()
            closing = create_sql.find("*/", index + 2)
            index = len(create_sql) if closing < 0 else closing + 2
            continue
        if character.isalnum() or character == "_":
            token.append(character)
        else:
            finish_token()
        index += 1

    finish_token()
    return tuple(tokens)


def _conflict_policies(create_sql: str) -> Tuple[str, ...]:
    tokens = _ddl_tokens(create_sql)
    policies = []
    for index in range(len(tokens) - 2):
        if tokens[index:index + 2] == ("ON", "CONFLICT"):
            policies.append(tokens[index + 2])
    return tuple(policies)


def _table_options(connection: Connection, table_name: str, create_sql: str) -> tuple:
    for row in connection.exec_driver_sql("PRAGMA table_list").fetchall():
        if len(row) > 5 and str(row[1]) == table_name and str(row[2]).lower() == "table":
            return bool(row[4]), bool(row[5])

    tokens = _ddl_tokens(create_sql)
    without_rowid = any(
        current == "WITHOUT" and following == "ROWID"
        for current, following in zip(tokens, tokens[1:])
    )
    return without_rowid, tokens[-1:] == ("STRICT",)


def _unique_keys(connection: Connection, table_name: str) -> tuple:
    result = []
    quoted_table = _quote_identifier(table_name)
    for index_row in connection.exec_driver_sql(
        f"PRAGMA index_list({quoted_table})"
    ).fetchall():
        if not bool(index_row[2]) or str(index_row[3]).lower() == "pk":
            continue
        index_name = str(index_row[1])
        quoted_index = _quote_identifier(index_name)
        terms = tuple(
            (
                int(term[1]),
                None if term[2] is None else str(term[2]),
                str(term[4] or "BINARY").upper(),
                bool(term[3]),
            )
            for term in connection.exec_driver_sql(
                f"PRAGMA index_xinfo({quoted_index})"
            ).fetchall()
            if bool(term[5])
        )
        partial = bool(index_row[4]) if len(index_row) > 4 else False
        has_expression = any(term[0] < 0 or term[1] is None for term in terms)
        index_sql = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
            (index_name,),
        ).scalar_one_or_none()
        result.append(
            (
                str(index_row[3]).lower(),
                partial,
                terms,
                _normalize_sql(index_sql) if partial or has_expression else None,
            )
        )
    return tuple(sorted(result, key=repr))


def _foreign_keys(connection: Connection, table_name: str) -> tuple:
    result = []
    for foreign_key in inspect(connection).get_foreign_keys(table_name):
        options = foreign_key.get("options") or {}
        result.append(
            (
                tuple(foreign_key.get("constrained_columns") or ()),
                str(foreign_key.get("referred_schema") or ""),
                str(foreign_key.get("referred_table") or ""),
                tuple(foreign_key.get("referred_columns") or ()),
                str(options.get("ondelete") or "").upper(),
                str(options.get("onupdate") or "").upper(),
                bool(options.get("deferrable")),
                str(options.get("initially") or "").upper(),
                str(options.get("match") or "").upper(),
            )
        )
    return tuple(sorted(result, key=repr))


def _has_primary_key_backing_index(
    connection: Connection,
    table_name: str,
) -> bool:
    quoted_table = _quote_identifier(table_name)
    return any(
        str(row[3]).lower() == "pk"
        for row in connection.exec_driver_sql(
            f"PRAGMA index_list({quoted_table})"
        ).fetchall()
    )


def canonical_table_shape(connection: Connection, table_name: str) -> dict:
    """Return the semantic SQLite shape used by release fingerprints."""
    quoted_table = _quote_identifier(table_name)
    column_rows = connection.exec_driver_sql(
        f"PRAGMA table_xinfo({quoted_table})"
    ).fetchall()
    if any(len(row) < 7 or int(row[6]) != 0 for row in column_rows):
        raise ValueError("legacy_profile_hidden_column")
    if _has_primary_key_backing_index(connection, table_name):
        raise ValueError("legacy_profile_primary_key_not_rowid")
    columns = tuple(
        (
            int(row[0]),
            str(row[1]),
            sqlite_type_affinity(str(row[2] or "")),
            bool(row[3]),
            _normalize_sql(row[4]),
            int(row[5]),
        )
        for row in column_rows
    )
    create_sql = connection.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).scalar_one_or_none()
    if create_sql is None or not columns:
        raise ValueError("legacy_profile_table_missing")
    create_sql = str(create_sql)
    without_rowid, strict = _table_options(connection, table_name, create_sql)
    return {
        "columns": columns,
        "conflict_policies": _conflict_policies(create_sql),
        "foreign_keys": _foreign_keys(connection, table_name),
        "strict": strict,
        "unique_keys": _unique_keys(connection, table_name),
        "without_rowid": without_rowid,
    }


def table_shape_digest(connection: Connection, table_name: str) -> str:
    material = json.dumps(
        canonical_table_shape(connection, table_name),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


_POST_V3_20_TABLES = (
    "decision_signal_feedback",
    "decision_signal_outcomes",
    "decision_signals",
    "intelligence_items",
    "intelligence_sources",
    "portfolio_idempotency_records",
    "schema_migrations",
)

_POST_V3_4_TABLES = (
    "agent_provider_turns",
    "alert_cooldowns",
    "alert_notifications",
    "alert_rules",
    "alert_triggers",
    "conversation_summaries",
    "fundamental_snapshot",
    "llm_usage",
    "portfolio_accounts",
    "portfolio_cash_ledger",
    "portfolio_corporate_actions",
    "portfolio_daily_snapshots",
    "portfolio_fx_rates",
    "portfolio_position_lots",
    "portfolio_positions",
    "portfolio_trades",
) + _POST_V3_20_TABLES

_POST_V3_0_TABLES = (
    "backtest_results",
    "backtest_summaries",
    "conversation_messages",
) + _POST_V3_4_TABLES


# Generated from the fixed release databases documented in the fixture manifest.
LEGACY_SCHEMA_PROFILES: Tuple[LegacySchemaProfile, ...] = (
    LegacySchemaProfile(
        profile_id="stockpulse_v3_20_0",
        source_tag="v3.20.0",
        source_commit="d22ff1c42d37d1b1d7d955c6dfb00daf1f62e69d",
        schema_digest="476b2e179a2506344fc10c0289017e0ba00307505f8cd9bb5842724cbffd156f",
        source_profile_digest="ce59784e3a49e140d6586a5e49235df875829031dd0c8ca36243f73405f350c6",
        table_digests=(
            ("agent_provider_turns", "33f3732f72b70f6d196f7122dd2b98ac7a161d8317ebaa8fd4ad8c00b7c3f419"),
            ("alert_cooldowns", "066b97a24cfafd5be439feb47b6c6d5a67a2cfd6d480246b86723d3ced08924d"),
            ("alert_notifications", "79b8f4c80bc8b2cbaca1686daa72c150af800fb1361a7dd590001a97fa1e6e9a"),
            ("alert_rules", "0be1b2e362a41fe635cb4a7843e86ec2e24603ce3ce343724ce0625d3ca7d47e"),
            ("alert_triggers", "ed835e69ffb5ae7a9c62c7c884ca1faaf472f08329bca1b8f7068d1297995b8f"),
            ("analysis_history", "6bd20050dea102853997bf000b98fca465d06fc9b6a97caa4319532beaa16e86"),
            ("backtest_results", "7f0b00eb33ff290acb52add3ddc35ea8226b691463b0de42bf97103c643f5fe2"),
            ("backtest_summaries", "2a943aee5ccc03d3c8a2c5002e2987b5df9293e8432199345f324a85e95dc802"),
            ("conversation_messages", "828cbd590b25735e5439551df67f58e9ff69c2362475c6da23a1496d75b1f790"),
            ("conversation_summaries", "96eb3ef5e505a177b2b34a3b3d4ed089474c7cee58e1bdf6bd7429f01e50f04f"),
            ("fundamental_snapshot", "b6190ef4a1dfaa4a060fd73dc4902d7f68252aa9e82bdb24b60ac6b3ab220128"),
            ("llm_usage", "57b86ab8250af0883a3544aa5e41c042ab75b9fd5b58ac06f6e2784cecbfb3d6"),
            ("news_intel", "6697701cdb59f4060e47509dbeaecc487388f76aac886979ba7cb68c078129f4"),
            ("portfolio_accounts", "b062628251c29bf1afd5b4cbfaa019580f0e309abf7922a0158461c5b7058190"),
            ("portfolio_cash_ledger", "9605e7051461b642622b8fa2c8cddb568f3ee15c174792b50d60b8abefafce16"),
            ("portfolio_corporate_actions", "0fb179e0f402954ea3f4e8d262c27e7cbef3a601010882fc4b49e68524a311f7"),
            ("portfolio_daily_snapshots", "3f55e1642813415dd1fa304d1c6f0a309fc8a6bc04663b746484a022bb2fd34b"),
            ("portfolio_fx_rates", "a60c40b302b79e614bcfe78e2a5ac8fd36ac32ed713301894a0dcc3ae54b752a"),
            ("portfolio_position_lots", "ce1aa5f357a83c94912086a93f985cab70e7631d09d8a999a5f93c493f183d61"),
            ("portfolio_positions", "1defb32e57f314f5a444ba5976e1c5e348d4180ca06eb01226f2d98e2806348c"),
            ("portfolio_trades", "3cd25a235c88a8475233fc0f8952e0ee32cbdfcf226114d91ff8862477f46778"),
            ("stock_daily", "40cc1a88647385dc34055fe234f4d539646aef3a943a8aa07b52553bb1c4266f"),
        ),
        forbidden_tables=_POST_V3_20_TABLES,
    ),
    LegacySchemaProfile(
        profile_id="stockpulse_v3_4_0",
        source_tag="v3.4.0",
        source_commit="0154992e18f6a5a09199a151ee75661e78b9c12f",
        schema_digest="1dec14940883b5571ae43e88f93c31974a9d403defc9ccc835ca2e53a3055a4f",
        source_profile_digest="86a9c06247e0ef4f3cf20eebe091a261ce05fa4e5eba8dc729c0c42cc312d93a",
        table_digests=(
            ("analysis_history", "6bd20050dea102853997bf000b98fca465d06fc9b6a97caa4319532beaa16e86"),
            ("backtest_results", "7f0b00eb33ff290acb52add3ddc35ea8226b691463b0de42bf97103c643f5fe2"),
            ("backtest_summaries", "2a943aee5ccc03d3c8a2c5002e2987b5df9293e8432199345f324a85e95dc802"),
            ("conversation_messages", "828cbd590b25735e5439551df67f58e9ff69c2362475c6da23a1496d75b1f790"),
            ("news_intel", "6697701cdb59f4060e47509dbeaecc487388f76aac886979ba7cb68c078129f4"),
            ("stock_daily", "40cc1a88647385dc34055fe234f4d539646aef3a943a8aa07b52553bb1c4266f"),
        ),
        forbidden_tables=_POST_V3_4_TABLES,
    ),
    LegacySchemaProfile(
        profile_id="stockpulse_v3_0_0",
        source_tag="v3.0.0",
        source_commit="52917baa02210fb7911491fcf48ecbf3f70e5812",
        schema_digest="ec853a3e7ad482efbcfdd0a31a5f0affce1031725950bbae8006d7d300ade1c0",
        source_profile_digest="dc374be346f7c821deb25f72844ebaaad3eca9eea6c6186f8a9893240680ccf0",
        table_digests=(
            ("analysis_history", "6bd20050dea102853997bf000b98fca465d06fc9b6a97caa4319532beaa16e86"),
            ("news_intel", "6697701cdb59f4060e47509dbeaecc487388f76aac886979ba7cb68c078129f4"),
            ("stock_daily", "40cc1a88647385dc34055fe234f4d539646aef3a943a8aa07b52553bb1c4266f"),
        ),
        forbidden_tables=_POST_V3_0_TABLES,
    ),
)


def match_legacy_schema_profile(
    connection: Connection,
    table_names: Iterable[str],
) -> Optional[LegacySchemaProfile]:
    """Return a supported release profile, or fail closed with ``None``."""
    actual_tables = set(table_names)
    for profile in LEGACY_SCHEMA_PROFILES:
        if not set(profile.required_tables).issubset(actual_tables):
            continue
        if set(profile.forbidden_tables).intersection(actual_tables):
            continue
        try:
            actual_digests = tuple(
                (table_name, table_shape_digest(connection, table_name))
                for table_name in profile.required_tables
            )
        except Exception:
            continue
        if actual_digests == profile.table_digests:
            return profile
    return None
