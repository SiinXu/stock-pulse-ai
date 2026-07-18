# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Isolate ambient LLM runtime config from ``os.environ`` during config tests.

A developer ``.env`` loaded into the process environment — most notably by
``litellm``'s ``load_dotenv()`` side effect at import time — must not leak LLM
model / channel / fallback settings into tests whose *temporary* ``.env`` is the
authoritative config source.

Without this, a stray ``LITELLM_FALLBACK_MODELS`` (or any ``LLM_*`` value) from
the local ``.env`` poisons config validation *only in the full-suite run* (where
``litellm`` is imported during collection and its ``load_dotenv`` populates
``os.environ``), while the same test passes in isolation. That is a classic
order-dependent flake, not a product bug: reading ``os.environ`` at validation
time is correct 12-factor behavior; the tests simply need a controlled
environment so the ambient developer config cannot bleed in.

``strip_ambient_llm_env`` removes those keys at ``setUp`` (establishing a clean
baseline, not masking end-state) and ``restore_ambient_llm_env`` puts them back
at ``tearDown`` so the process environment is left untouched for other tests.
"""
from __future__ import annotations

import os
from typing import Dict

# Any key under these namespaces is LLM connection / routing config that a temp
# ``.env`` (or explicit ``patch.dict``) must fully own during a config test.
_AMBIENT_LLM_ENV_PREFIXES = ("LLM_", "LITELLM_")

# Non-prefixed LLM runtime keys the config layer also reads.
_AMBIENT_LLM_ENV_KEYS = frozenset(
    {
        "AGENT_LITELLM_MODEL",
        "VISION_MODEL",
        "GEMINI_MODEL_FALLBACK",
        "GENERATION_BACKEND",
        "GENERATION_FALLBACK_BACKEND",
        "AGENT_GENERATION_BACKEND",
    }
)


def _is_ambient_llm_key(key: str) -> bool:
    upper = key.upper()
    return upper.startswith(_AMBIENT_LLM_ENV_PREFIXES) or upper in _AMBIENT_LLM_ENV_KEYS


def strip_ambient_llm_env() -> Dict[str, str]:
    """Pop ambient LLM config keys from ``os.environ`` and return them for restore."""
    saved: Dict[str, str] = {}
    for key in list(os.environ):
        if _is_ambient_llm_key(key):
            saved[key] = os.environ.pop(key)
    return saved


def restore_ambient_llm_env(saved: Dict[str, str]) -> None:
    """Restore keys removed by :func:`strip_ambient_llm_env`."""
    for key, value in saved.items():
        os.environ[key] = value
