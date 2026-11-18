"""API FastAPI do GraphRAG/KAG (opcional: a interface Streamlit chama o pipeline direto).

Uso: uvicorn app.api:app --reload --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import pipeline
from app.pipeline import EXAMPLES  # noqa: F401  (reexportado para os testes e scripts)


@asynccontextmanager
async def lifespan(_: FastAPI):
    from app.embeddings import embed_query
    embed_query("aquecimento")  # carrega o modelo antes da primeira pergunta
    yield


app = FastAPI(title="GraphRAG/KAG arXiv", version="1.0.0", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    mode: Literal["graph", "vector"] = "graph"
    hops: int = Field(default=2, ge=1, le=3)
    use_llm: bool = True
    text2cypher: bool = True


@app.get("/api/health")
def health():
    return pipeline.health()


@app.get("/api/stats")
def stats():
    return pipeline.stats()


@app.get("/api/overview")
def overview(limit: int = 45):
    return pipeline.overview(limit)


@app.get("/api/examples")
def examples():
    return pipeline.EXAMPLES


@app.post("/api/ask")
def ask(req: AskRequest):
    try:
        return pipeline.answer_question(req.question, req.mode, req.hops, req.use_llm,
                                        req.text2cypher)
    except Exception as exc:
        from neo4j.exceptions import Neo4jError, ServiceUnavailable
        if isinstance(exc, (Neo4jError, ServiceUnavailable)):
            raise HTTPException(503, f"Falha ao consultar o Neo4j: {type(exc).__name__}") from exc
        raise
