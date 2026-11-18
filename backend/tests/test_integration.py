"""Testes operacionais contra o Neo4j carregado (docker compose up -d + ingestao)."""
import pytest

from app.db import run, run_read

try:
    run("RETURN 1")
    HAS_NEO4J = bool(run("MATCH (a:Article) RETURN count(a) AS n")[0]["n"])
except Exception:
    HAS_NEO4J = False

pytestmark = [pytest.mark.neo4j,
              pytest.mark.skipif(not HAS_NEO4J, reason="Neo4j sem dados (rode a ingestao)")]


def test_schema_has_constraints_and_all_index_kinds():
    cons = {r["name"] for r in run("SHOW CONSTRAINTS YIELD name RETURN name")}
    assert {"article_id", "entity_id", "chunk_id"} <= cons
    kinds = {r["type"] for r in run("SHOW INDEXES YIELD type RETURN type")}
    assert {"RANGE", "FULLTEXT", "VECTOR"} <= kinds


def test_every_relation_carries_evidence_and_source_article():
    n = run("""MATCH (:Entity)-[r]->(:Entity)
               WHERE r.evidence IS NULL OR r.doc_id IS NULL RETURN count(r) AS n""")[0]["n"]
    assert n == 0


def test_every_article_describes_an_entity():
    n = run("MATCH (a:Article) WHERE NOT (a)-[:DESCRIBES]->() RETURN count(a) AS n")[0]["n"]
    assert n == 0


def test_gds_properties_written():
    row = run("""MATCH (e:Entity) RETURN count(e.pagerank) AS pr, count(e.community) AS c,
                 count(e) AS n""")[0]
    assert row["pr"] == row["n"] and row["c"] == row["n"]


def test_read_transaction_rejects_writes():
    with pytest.raises(Exception):
        run_read("CREATE (:Hack {x: 1})")
    assert run("MATCH (h:Hack) RETURN count(h) AS n")[0]["n"] == 0


def test_multihop_question_crosses_articles():
    from app.retrieval.hybrid import retrieve
    res = retrieve("Que jogo da Valve surgiu de um mod de Warcraft III?", hops=2)
    docs = {t["doc_id"] for t in res.triples}
    assert len(docs) >= 2, "a resposta deveria juntar fatos de mais de um artigo"
    assert res.paths


def test_out_of_domain_question_is_refused():
    from app.generate import answer_extractive
    from app.retrieval.hybrid import retrieve
    res = retrieve("Qual a receita de bolo de cenoura?")
    assert res.out_of_domain
    assert answer_extractive(res)["answer"].startswith("Não encontrei")


def test_api_ask_returns_full_provenance():
    from fastapi.testclient import TestClient
    from app.api import app
    r = TestClient(app).post("/api/ask", json={"question": "Quem desenvolveu o Dota 2?",
                                               "use_llm": False})
    body = r.json()
    assert r.status_code == 200
    assert body["triples"] and body["graph"]["nodes"] and body["cypher"]
    assert set(body["cited"]) <= {t["id"] for t in body["triples"]} | {"C1", "C2", "C3"}


def test_api_rejects_empty_question():
    from fastapi.testclient import TestClient
    from app.api import app
    assert TestClient(app).post("/api/ask", json={"question": ""}).status_code == 422
