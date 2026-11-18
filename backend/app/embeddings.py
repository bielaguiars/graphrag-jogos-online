"""Embeddings locais multilingues (perguntas em PT, papers em EN)."""
from __future__ import annotations

from functools import lru_cache

from app.config import EMBED_MODEL


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBED_MODEL)


def embed_passages(texts: list[str]) -> list[list[float]]:
    # modelos E5 esperam os prefixos "passage:" e "query:"
    vecs = _model().encode([f"passage: {t}" for t in texts], normalize_embeddings=True,
                           batch_size=32, show_progress_bar=False)
    return vecs.tolist()


def embed_query(text: str) -> list[float]:
    return _model().encode(f"query: {text}", normalize_embeddings=True).tolist()
