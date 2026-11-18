"""Schema LPG: constraints de unicidade e indices (range/BTree, fulltext e vetorial).

Modelo:
  (:Article {doc_id, title, text, url})-[:DESCRIBES]->(:Entity)
  (:Chunk {id, text})-[:PART_OF]->(:Article)
  (:Entity)-[:DEVELOPED_BY|PUBLISHED_BY|HAS_GENRE|AVAILABLE_ON|USES_ENGINE|PART_OF|SEQUEL_OF|
            BASED_ON|HAS_FEATURE|FEATURED_IN|SUBSIDIARY_OF|CREATED_BY|ORGANIZED_BY
            {evidence, doc_id}]->(:Entity)
  (:Entity) recebe tambem um rotulo de tipo: :Game | :Company | :Person | :Genre | :Platform |
            :Engine | :Franchise | :Event | :Concept

Uso: python -m app.schema
"""
from __future__ import annotations

from app.config import EMBED_DIM
from app.db import run

ENTITY_LABELS = ["Game", "Company", "Person", "Genre", "Platform", "Engine", "Franchise",
                 "Event", "Concept"]
RELATIONS = ["DEVELOPED_BY", "PUBLISHED_BY", "HAS_GENRE", "AVAILABLE_ON", "USES_ENGINE", "PART_OF",
             "SEQUEL_OF", "BASED_ON", "HAS_FEATURE", "FEATURED_IN", "SUBSIDIARY_OF", "CREATED_BY",
             "ORGANIZED_BY"]

CONSTRAINTS = [
    "CREATE CONSTRAINT article_id IF NOT EXISTS FOR (a:Article) REQUIRE a.doc_id IS UNIQUE",
    "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
]

RANGE_INDEXES = [  # indices range (B-tree) para filtros e ordenacao
    "CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)",
    "CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.type)",
    "CREATE INDEX entity_pagerank IF NOT EXISTS FOR (e:Entity) ON (e.pagerank)",
    "CREATE INDEX article_title IF NOT EXISTS FOR (a:Article) ON (a.title)",
]

FULLTEXT_INDEXES = [
    "CREATE FULLTEXT INDEX entity_fulltext IF NOT EXISTS FOR (e:Entity) "
    "ON EACH [e.name, e.aliases_text, e.description]",
    "CREATE FULLTEXT INDEX article_fulltext IF NOT EXISTS FOR (a:Article) ON EACH [a.title, a.text]",
]

VECTOR_INDEXES = [
    f"CREATE VECTOR INDEX {name} IF NOT EXISTS FOR (n:{label}) ON (n.embedding) "
    f"OPTIONS {{indexConfig: {{`vector.dimensions`: {EMBED_DIM}, "
    f"`vector.similarity_function`: 'cosine'}}}}"
    for name, label in [("entity_vector", "Entity"), ("chunk_vector", "Chunk"),
                        ("article_vector", "Article")]
]

ALL_STATEMENTS = CONSTRAINTS + RANGE_INDEXES + FULLTEXT_INDEXES + VECTOR_INDEXES


def drop_all() -> None:
    """Remove constraints e indices do schema anterior (troca de dominio)."""
    for r in run("SHOW CONSTRAINTS YIELD name RETURN name"):
        run(f"DROP CONSTRAINT {r['name']} IF EXISTS")
    for r in run("SHOW INDEXES YIELD name, type WHERE type <> 'LOOKUP' RETURN name"):
        run(f"DROP INDEX {r['name']} IF EXISTS")


def apply_schema() -> None:
    for stmt in ALL_STATEMENTS:
        run(stmt)
    run("CALL db.awaitIndexes(120)")


def describe_schema() -> str:
    """Texto do schema para o prompt de Text-to-Cypher."""
    return f"""Nos:
- (:Article {{doc_id, title, text, url}}) artigo da Wikipedia
- (:Entity {{id, name, type, description, aliases, pagerank, community}}) com rotulo extra
  {' | '.join(':' + x for x in ENTITY_LABELS)}
- (:Chunk {{id, text}})
Relacoes:
- (:Article)-[:DESCRIBES]->(:Entity)
- (:Chunk)-[:PART_OF]->(:Article)
- (:Entity)-[:{'|'.join(RELATIONS)} {{evidence, doc_id}}]->(:Entity)
  Ex.: (:Game)-[:DEVELOPED_BY]->(:Company), (:Game)-[:BASED_ON]->(:Game),
  (:Company)-[:SUBSIDIARY_OF]->(:Company), (:Game)-[:FEATURED_IN]->(:Event)"""


if __name__ == "__main__":
    apply_schema()
    for row in run("SHOW INDEXES YIELD name, type, labelsOrTypes, properties RETURN *"):
        print(row)
