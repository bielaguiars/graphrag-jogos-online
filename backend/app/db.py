"""Driver Neo4j compartilhado."""
from __future__ import annotations

from functools import lru_cache

from neo4j import Driver, GraphDatabase

from app.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER


@lru_cache(maxsize=1)
def get_driver() -> Driver:
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def run(query: str, **params) -> list[dict]:
    records, _, _ = get_driver().execute_query(query, params, database_="neo4j")
    return [r.data() for r in records]


def run_read(query: str, timeout: float = 10.0, **params) -> list[dict]:
    """Executa em transacao de leitura: o servidor rejeita qualquer escrita."""
    def work(tx):
        return [r.data() for r in tx.run(query, params)]
    with get_driver().session(database="neo4j", default_access_mode="READ") as s:
        return s.execute_read(work)
