"""Pipeline de pergunta e resposta compartilhado pela API (FastAPI) e pela interface (Streamlit)."""
from __future__ import annotations

import time
from functools import lru_cache

from app.config import LLM_MODEL, llm_enabled
from app.db import run_read
from app.generate import answer_extractive, answer_llm, confidence
from app.retrieval.hybrid import NODE_KEY, _node, retrieve, retrieve_vector_only

EXAMPLES = [
    "Que jogo da Valve surgiu de um mod de Warcraft III?",
    "De quais jogos o Teamfight Tactics deriva e quem desenvolveu cada um deles?",
    "Que jogo militar deu origem ao mod que virou o DayZ, e quem criou esse mod?",
    "Quais jogos battle royale são gratuitos?",
    "De qual empresa a Psyonix é subsidiária e que campeonato ela organiza?",
    "Quais jogos usam o motor Source?",
]


@lru_cache(maxsize=1)
def _client():
    import anthropic
    return anthropic.Anthropic()


def health() -> dict:
    try:
        n = run_read("MATCH (n) RETURN count(n) AS n")[0]["n"]
        return {"neo4j": True, "nodes": n, "llm": llm_enabled(),
                "model": LLM_MODEL if llm_enabled() else None}
    except Exception as exc:
        return {"neo4j": False, "error": type(exc).__name__, "llm": llm_enabled()}


def stats() -> dict:
    labels = run_read("""MATCH (n) UNWIND labels(n) AS l
                         RETURN l AS label, count(*) AS count ORDER BY count DESC""")
    rels = run_read("MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count ORDER BY count DESC")
    top = run_read("""MATCH (e:Entity) RETURN e.name AS name, e.type AS type,
                      round(e.pagerank, 3) AS pagerank, e.mentions AS mentions
                      ORDER BY e.pagerank DESC LIMIT 12""")
    comms = run_read("""MATCH (e:Entity) WITH e.community AS c, collect(e) AS es
                        WITH c, size(es) AS size, es ORDER BY size DESC LIMIT 6
                        RETURN c AS community, size,
                        [x IN es WHERE x.pagerank IS NOT NULL | x.name][0..6] AS sample""")
    return {"labels": labels, "relationships": rels, "top_pagerank": top, "communities": comms}


def overview(limit: int = 45) -> dict:
    """Nucleo do grafo: entidades de maior PageRank e as arestas entre elas."""
    rows = run_read(f"""
        MATCH (e:Entity) WITH e ORDER BY e.pagerank DESC LIMIT $limit
        WITH collect(e) AS core
        UNWIND core AS a
        MATCH (a)-[r]-(b) WHERE b IN core AND elementId(a) < elementId(b)
        RETURN DISTINCT elementId(r) AS id, type(r) AS rel,
               {NODE_KEY.format(v='startNode(r)')} AS source,
               {NODE_KEY.format(v='endNode(r)')} AS target""", limit=limit)
    nodes = run_read(f"""MATCH (e:Entity) WITH e ORDER BY e.pagerank DESC LIMIT $limit
                         RETURN {_node('e')} AS n""", limit=limit)
    return {"nodes": [{**r["n"], "seed": False} for r in nodes],
            "edges": [{**r, "on_shortest_path": False} for r in rows]}


def answer_question(question: str, mode: str = "graph", hops: int = 2, use_llm: bool = True,
                    text2cypher: bool = True) -> dict:
    """Recupera, gera e verifica. Levanta excecao se o Neo4j estiver fora do ar."""
    t0 = time.perf_counter()
    res = retrieve(question, hops=hops) if mode == "graph" else retrieve_vector_only(question)

    t2c = None
    use_llm = use_llm and llm_enabled()
    if use_llm and mode == "graph" and text2cypher:
        from app.retrieval.text2cypher import run_text2cypher
        t2c = run_text2cypher(_client(), question)
    if use_llm:
        try:
            gen = answer_llm(_client(), res, (t2c or {}).get("rows"))
            mode_used = "llm"
        except Exception as exc:  # API fora do ar: cai para o modo extrativo
            gen = answer_extractive(res)
            gen["llm_error"] = type(exc).__name__
            mode_used = "extrativo"
    else:
        gen = answer_extractive(res)
        mode_used = "extrativo"

    cypher = list(res.cypher)
    if t2c and t2c.get("cypher"):
        cypher.append({"step": "text-to-cypher (LLM)", "query": t2c["cypher"], "params": {},
                       "error": t2c.get("error"), "rows": len(t2c.get("rows", []))})
    return {
        "question": question,
        "retrieval_mode": mode,
        "generation_mode": mode_used,
        **gen,
        "confidence": confidence(res, gen["grounding"]),
        "seeds": [{"name": s["name"], "score": round(s["score"], 4), "sources": s["sources"]}
                  for s in res.seeds],
        "triples": res.triples,
        "paths": res.paths,
        "chunks": [{k: c[k] for k in ("id", "doc_id", "title", "url", "text", "score")}
                   for c in res.chunks],
        "graph": {"nodes": res.nodes, "edges": res.edges},
        "cypher": cypher,
        "timings_ms": {**res.timings_ms, "total": round((time.perf_counter() - t0) * 1000)},
    }
