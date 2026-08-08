# -*- coding: utf-8 -*-
"""Optional lightweight vector ranking for agent memory (no faiss/chroma).

Uses pure-Python feature hashing (bag-of-words over word tokens) and cosine
similarity. Enabled only when ``AGENT_MEMORY_VECTOR_ENABLED=true``. When the
flag is off, callers must not invoke this module for production retrieval.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

_TOKEN_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]{2,}")
_DEFAULT_DIM = 256


def _stable_token_hash(token: str) -> int:
    """Deterministic 64-bit token hash (independent of PYTHONHASHSEED)."""
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=False)


@dataclass(frozen=True)
class VectorDocument:
    """A document eligible for hashed embedding ranking."""

    doc_id: str
    text: str
    meta: dict


def tokenize(text: str) -> List[str]:
    """Split text into lowercase alphanumeric / CJK tokens (min length 2)."""
    if not text:
        return []
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(text)]


def hash_embed(tokens: Sequence[str], dim: int = _DEFAULT_DIM) -> List[float]:
    """Hashing-trick bag-of-words embedding with L2 normalization.

    Collision-tolerant and dependency-free. Suitable for coarse ranking only.
    """
    if dim <= 0:
        raise ValueError("dim must be positive")
    vec = [0.0] * dim
    if not tokens:
        return vec
    for tok in tokens:
        h = _stable_token_hash(tok)
        idx = h % dim
        sign = 1.0 if (h & 1) == 0 else -1.0
        vec[idx] += sign
    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity for equal-length L2-normalized (or raw) vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))


class HashingVectorIndex:
    """In-memory hashed-BoW index for ranking memory documents."""

    def __init__(self, dim: int = _DEFAULT_DIM):
        self.dim = dim
        self._docs: List[VectorDocument] = []
        self._embeddings: List[List[float]] = []

    def clear(self) -> None:
        self._docs.clear()
        self._embeddings.clear()

    def add(self, doc: VectorDocument) -> None:
        tokens = tokenize(doc.text)
        self._docs.append(doc)
        self._embeddings.append(hash_embed(tokens, dim=self.dim))

    def add_many(self, docs: Iterable[VectorDocument]) -> None:
        for doc in docs:
            self.add(doc)

    def __len__(self) -> int:
        return len(self._docs)

    def query(self, text: str, top_k: int = 5) -> List[Tuple[VectorDocument, float]]:
        """Return top_k documents ranked by cosine similarity to ``text``."""
        if not self._docs or top_k <= 0:
            return []
        q = hash_embed(tokenize(text), dim=self.dim)
        scored: List[Tuple[VectorDocument, float]] = []
        for doc, emb in zip(self._docs, self._embeddings):
            scored.append((doc, cosine_similarity(q, emb)))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]
