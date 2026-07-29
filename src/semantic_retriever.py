"""Local sentence-embedding scores with a reusable on-disk report index."""

import hashlib
import os
from functools import lru_cache
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = "BAAI/bge-small-en-v1.5"
MODEL_CACHE_DIR = PROJECT_ROOT / ".cache" / "fastembed"
INDEX_CACHE_DIR = PROJECT_ROOT / ".cache" / "semantic_indexes"

# Keep all model files inside the project instead of writing to a user's
# system-level cache. This also avoids Hugging Face Xet log permission issues.
os.environ.setdefault(
    "HF_HOME",
    str(PROJECT_ROOT / ".cache" / "huggingface"),
)
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")


@lru_cache(maxsize=1)
def _load_model() -> object:
    """Load the small local embedding model only when semantic search is used."""
    from fastembed import TextEmbedding

    return TextEmbedding(
        model_name=MODEL_NAME,
        cache_dir=str(MODEL_CACHE_DIR),
        threads=min(os.cpu_count() or 2, 4),
    )


def _index_cache_path(texts: tuple[str, ...]) -> Path:
    """Return a stable cache filename for one exact set of report chunks."""
    digest = hashlib.sha256()
    digest.update(MODEL_NAME.encode("utf-8"))
    for text in texts:
        digest.update(len(text).to_bytes(8, byteorder="big"))
        digest.update(text.encode("utf-8"))
    return INDEX_CACHE_DIR / f"{digest.hexdigest()[:24]}.npy"


def _normalise_rows(matrix: np.ndarray) -> np.ndarray:
    """Convert embedding rows to unit length for cosine similarity."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return matrix / norms


@lru_cache(maxsize=4)
def _passage_matrix(texts: tuple[str, ...]) -> np.ndarray:
    """Embed report chunks once and reuse the index across questions and runs."""
    cache_path = _index_cache_path(texts)
    if cache_path.exists():
        cached_matrix = np.load(cache_path, allow_pickle=False)
        if cached_matrix.shape[0] == len(texts):
            return cached_matrix

    model = _load_model()
    matrix = np.asarray(
        list(model.passage_embed(texts, batch_size=64)),
        dtype=np.float32,
    )
    matrix = _normalise_rows(matrix)

    # Tiny synthetic unit-test inputs are cheaper to rebuild than to store.
    if len(texts) >= 50:
        INDEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        np.save(cache_path, matrix, allow_pickle=False)

    return matrix


def semantic_similarity_scores(
    query: str,
    texts: list[str],
) -> list[float] | None:
    """Return local cosine similarities, or None if embeddings are unavailable."""
    if not query.strip() or not texts:
        return []

    try:
        model = _load_model()
        query_vector = np.asarray(
            next(iter(model.query_embed(query))),
            dtype=np.float32,
        )
        query_norm = np.linalg.norm(query_vector)
        if query_norm == 0:
            return [0.0] * len(texts)

        passage_matrix = _passage_matrix(tuple(texts))
        scores = passage_matrix @ (query_vector / query_norm)
        return [float(score) for score in scores]
    except (ImportError, OSError, RuntimeError, ValueError):
        # The transparent lexical retriever remains available if a new user
        # has not downloaded the optional local model yet.
        return None
