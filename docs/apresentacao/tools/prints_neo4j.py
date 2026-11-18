"""Roda as consultas da apresentação no Neo4j Browser (container graphrag-neo4j, portas 7476/7689)
e salva um print de cada uma em docs/apresentacao/prints/. Também grava consultas.json com o texto.

Uso (com o grafo já carregado): python prints_neo4j.py
"""
import json
import re
from pathlib import Path

from neo import Neo, SHOTS

T, G = "Table", "Graph"
QUERIES = [
    ("neo4j_tamanho",
     "MATCH (n)\nRETURN labels(n)[0] AS rotulo, count(*) AS nos\nORDER BY nos DESC", T),
    ("neo4j_tipos",
     "MATCH (e:Entity)\nRETURN e.type AS tipo, count(*) AS entidades\nORDER BY entidades DESC", T),
    ("neo4j_indices",
     "SHOW INDEXES\nYIELD name, type, labelsOrTypes, properties\nWHERE type <> 'LOOKUP'\n"
     "RETURN name, type, labelsOrTypes, properties", T),
    ("neo4j_esquema", "CALL db.schema.visualization()", G),
    ("neo4j_proveniencia",
     "MATCH (a:Entity {name: 'Defense of the Ancients'})-[r:BASED_ON]->(b:Entity {name: 'Warcraft III: Reign of Chaos'})\n"
     "MATCH (art:Article {doc_id: r.doc_id})\n"
     "RETURN a.name AS origem, type(r) AS relacao, b.name AS destino, r.evidence AS evidencia, art.title AS artigo", T),
    ("neo4j_vetor",
     "MATCH (c:Chunk)-[:PART_OF]->(:Article {title: 'Dota 2'})\nWITH c LIMIT 1\n"
     "CALL db.index.vector.queryNodes('chunk_vector', 5, c.embedding) YIELD node, score\n"
     "MATCH (node)-[:PART_OF]->(a:Article)\n"
     "RETURN a.title AS artigo, left(node.text, 70) AS trecho, round(score, 3) AS similaridade", T),
    ("neo4j_fulltext",
     "CALL db.index.fulltext.queryNodes('entity_fulltext', 'valv~1 OR \"warcraft iii\"') YIELD node, score\n"
     "RETURN node.type AS tipo, node.name AS entidade, round(score, 3) AS score\nLIMIT 6", T),
    ("neo4j_multihop",
     "MATCH p = (v:Entity {name: 'Valve'})<-[:DEVELOPED_BY]-(g:Game)-[:SEQUEL_OF]->(mod:Entity)-[:BASED_ON]->(w:Entity)\n"
     "WHERE w.name STARTS WITH 'Warcraft III'\nRETURN p", G),
    ("neo4j_caminho",
     "MATCH (a:Entity {name: 'League of Legends'}), (b:Entity {name: 'Dota 2'})\n"
     "MATCH p = shortestPath((a)-[:BASED_ON|SEQUEL_OF|DEVELOPED_BY|CREATED_BY|PUBLISHED_BY|SUBSIDIARY_OF*..6]-(b))\n"
     "RETURN p", G),
    ("neo4j_pagerank",
     "MATCH (e:Entity)\nRETURN e.name AS entidade, e.type AS tipo, round(e.pagerank, 3) AS pagerank\n"
     "ORDER BY pagerank DESC\nLIMIT 10", T),
    ("neo4j_louvain",
     "MATCH (e:Entity)\nWITH e.community AS comunidade, count(*) AS entidades, collect(e.name)[..5] AS exemplos\n"
     "RETURN comunidade, entidades, exemplos\nORDER BY entidades DESC\nLIMIT 8", T),
]


def main():
    n = Neo()
    first = n.run("MATCH (e:Entity) RETURN count(e) AS entidades")
    assert re.search(r"entidades\s+1\s+351\b", first), f"grafo errado ou vazio: {first[:200]}"
    out = []
    for shot, q, view in QUERIES:
        txt = n.run(q, shot=shot, view=view, wait_ms=3500 if view == G else 1200, timeout=90)
        if re.search(r"\bError\b|Neo\.ClientError|failed", txt):
            raise SystemExit(f"ERRO em {shot}:\n{txt[:600]}")
        print(f"[{shot}] {re.sub(r'\\s+', ' ', txt)[-160:]}")
        out.append({"shot": shot, "query": q, "text": txt})
    (SHOTS.parent / "consultas.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    n.close()


if __name__ == "__main__":
    main()
