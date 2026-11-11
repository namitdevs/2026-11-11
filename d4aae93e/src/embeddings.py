"""Text embeddings with a production path and an offline-safe fallback.

- `minilm`: sentence-transformers/all-MiniLM-L6-v2 (384-d, normalised).
- `hashing`: deterministic char n-gram encoder (384-d). No model download,
  no network, identical vectors across runs and machines.

The fallback exists so CI and offline judges can always reproduce the
benchmark; the MiniLM path is one environment variable away.
"""
from __future__ import annotations

import hashlib
import os
import re
from typing import Iterable

import numpy as np

from .config import DEDUPE_COSINE_HASH, DEDUPE_COSINE_MINILM, EMBED_DIM

_WORD_RE = re.compile(r"[^a-z0-9\s-]")


def _normalise_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32)


class HashingEmbedder:
    backend = "hashing"
    dim = EMBED_DIM
    dedupe_threshold = DEDUPE_COSINE_HASH

    def _features(self, text: str) -> list[str]:
        cleaned = _WORD_RE.sub(" ", text.lower())
        words = cleaned.split()
        features = list(words)
        features.extend(f"{a}_{b}" for a, b in zip(words, words[1:]))
        for word in words:
            padded = f"#{word}#"
            for n in (3, 4, 5):
                for i in range(max(1, len(padded) - n + 1)):
                    features.append(padded[i : i + n])
        return features

    def encode(self, texts: Iterable[str]) -> np.ndarray:
        texts = list(texts)
        matrix = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            counts: dict[int, float] = {}
            for feature in self._features(text):
                digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
                value = int.from_bytes(digest, "big")
                index = value % self.dim
                sign = 1.0 if (value >> 63) & 1 else -1.0
                counts[index] = counts.get(index, 0.0) + sign
            for index, count in counts.items():
                matrix[row, index] = np.sign(count) * (1.0 + np.log1p(abs(count)))
        return _normalise_rows(matrix)


class MiniLMEmbedder:
    backend = "minilm"
    dim = EMBED_DIM
    dedupe_threshold = DEDUPE_COSINE_MINILM

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer  # type: ignore

        self._model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    def encode(self, texts: Iterable[str]) -> np.ndarray:
        vectors = self._model.encode(
            list(texts), convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False
        )
        return np.asarray(vectors, dtype=np.float32)


def get_embedder(prefer: str | None = None):
    prefer = (prefer or os.getenv("CAMPUSPULSE_EMBEDDER") or "hashing").lower()
    if prefer in ("minilm", "sentence-transformers", "auto"):
        try:
            return MiniLMEmbedder()
        except Exception as exc:  # pragma: no cover - depends on optional extra
            print(f"[embeddings] MiniLM unavailable ({exc.__class__.__name__}); using hashing fallback")
    return HashingEmbedder()


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    return 0.0 if denominator == 0 else float(np.dot(a, b) / denominator)
