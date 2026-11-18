"""Carga do grafo no Neo4j: artigos, chunks, entidades resolvidas, relacoes com evidencia,
embeddings e algoritmos GDS (PageRank + Louvain).

Uso: python -m app.ingest.load [--reset]
"""
from __future__ import annotations

import argparse
import json
import re

from app.config import DATA_DIR, ER_THRESHOLD
from app.db import run
from app.embeddings import embed_passages
from app.ingest.resolve import Mention, resolve
from app.schema import ENTITY_LABELS, RELATIONS, apply_schema, drop_all


def chunk_text(text: str, size: int = 3) -> list[str]:
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    return [" ".join(sents[i:i + size]) for i in range(0, len(sents), size)]


def load_inputs() -> tuple[list[dict], dict[str, dict]]:
    docs = json.loads((DATA_DIR / "raw" / "articles.json").read_text(encoding="utf-8"))
    extracted = {}
    for d in docs:
        f = DATA_DIR / "extracted" / f"{d['doc_id']}.json"
        if f.exists():
            extracted[d["doc_id"]] = json.loads(f.read_text(encoding="utf-8"))
    return docs, extracted


def build_graph(extracted: dict[str, dict], embed=None):
    """Transforma extracoes em entidades canonicas + arestas (puro, testavel sem Neo4j)."""
    mentions = [Mention(e["name"], e["type"], e.get("aliases", []), e.get("description", ""), did)
                for did, ex in extracted.items() for e in ex["entities"]]
    canon, mapping = resolve(mentions, embed=embed, threshold=ER_THRESHOLD)
    edges, dropped = [], 0
    for did, ex in extracted.items():
        for r in ex["relations"]:
            src, dst = mapping.get((did, r["source"])), mapping.get((did, r["target"]))
            if r["type"] in RELATIONS and src and dst and src != dst:
                edges.append({"src": src, "type": r["type"], "dst": dst,
                              "evidence": r["evidence"], "doc": did})
            else:
                dropped += 1
    subjects = {did: mapping.get((did, ex["subject"])) for did, ex in extracted.items()}
    return canon, edges, subjects, dropped


def write_graph(docs, canon, edges, subjects) -> None:
    vecs = embed_passages([f"{d['title']}. {d['text'][:1500]}" for d in docs])
    run("""UNWIND $rows AS r
           MERGE (a:Article {doc_id: r.doc_id})
           SET a.title = r.title, a.text = r.text, a.url = r.url, a.embedding = r.embedding""",
        rows=[{**d, "embedding": v} for d, v in zip(docs, vecs)])

    chunks = [{"id": f"{d['doc_id']}#{i}", "doc": d["doc_id"], "text": t}
              for d in docs for i, t in enumerate(chunk_text(d["text"]))]
    for c, v in zip(chunks, embed_passages([c["text"] for c in chunks])):
        c["embedding"] = v
    run("""UNWIND $rows AS r MATCH (a:Article {doc_id: r.doc})
           MERGE (c:Chunk {id: r.id}) SET c.text = r.text, c.embedding = r.embedding
           MERGE (c)-[:PART_OF]->(a)""", rows=chunks)

    e_vecs = embed_passages([f"{c.name}: {c.description}" for c in canon])
    rows = [{"id": c.id, "name": c.name, "type": c.type, "aliases": c.aliases,
             "aliases_text": " | ".join(c.aliases), "description": c.description,
             "mentions": len(c.docs), "embedding": v} for c, v in zip(canon, e_vecs)]
    for label in ENTITY_LABELS:  # rotulo de tipo nao pode ser parametro no Cypher
        run(f"""UNWIND $rows AS r
                MERGE (e:Entity {{id: r.id}})
                SET e:{label}, e.name = r.name, e.type = r.type, e.aliases = r.aliases,
                    e.aliases_text = r.aliases_text, e.description = r.description,
                    e.mentions = r.mentions, e.embedding = r.embedding""",
            rows=[r for r in rows if r["type"] == label])

    run("""UNWIND $rows AS r MATCH (a:Article {doc_id: r.doc}), (e:Entity {id: r.entity})
           MERGE (a)-[:DESCRIBES]->(e)""",
        rows=[{"doc": d, "entity": e} for d, e in subjects.items() if e])
    for rel in RELATIONS:
        run(f"""UNWIND $rows AS r
                MATCH (a:Entity {{id: r.src}}), (b:Entity {{id: r.dst}})
                MERGE (a)-[x:{rel}]->(b)
                ON CREATE SET x.evidence = r.evidence, x.doc_id = r.doc""",
            rows=[e for e in edges if e["type"] == rel])


def run_gds() -> dict:
    run("CALL gds.graph.drop('kg', false) YIELD graphName RETURN graphName")
    run("""CALL gds.graph.project('kg', ['Entity'],
           {ALL: {type: '*', orientation: 'UNDIRECTED'}})""")
    pr = run("""CALL gds.pageRank.write('kg', {writeProperty: 'pagerank', maxIterations: 40})
                YIELD nodePropertiesWritten RETURN nodePropertiesWritten""")
    lv = run("""CALL gds.louvain.write('kg', {writeProperty: 'community'})
                YIELD communityCount, modularity RETURN communityCount, modularity""")
    run("CALL gds.graph.drop('kg') YIELD graphName RETURN graphName")
    return {"pagerank_nodes": pr[0]["nodePropertiesWritten"], **lv[0]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="apaga grafo, indices e constraints")
    args = ap.parse_args()
    if args.reset:
        run("MATCH (n) DETACH DELETE n")  # grafo pequeno (< 10 mil nos)
        drop_all()
    apply_schema()
    docs, extracted = load_inputs()
    canon, edges, subjects, dropped = build_graph(extracted, embed=embed_passages)
    write_graph(docs, canon, edges, subjects)
    gds = run_gds()
    print(f"{len(docs)} artigos, {len(extracted)} com extracao, {len(canon)} entidades canonicas, "
          f"{len(edges)} relacoes, {dropped} descartadas. GDS: {gds}")


if __name__ == "__main__":
    main()
