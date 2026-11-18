"""Recuperacao hibrida GraphRAG.

1. Linkagem de entidades por tres sinais: busca vetorial (cosseno), fulltext (Lucene) e
   dicionario (nome exato na pergunta, mais glossario PT->EN). Fusao por Reciprocal Rank Fusion.
2. Trechos (chunks) por busca vetorial: ancoram a entidade descrita pelo artigo do trecho.
3. Travessia multi-hop (1..N saltos) a partir das sementes, priorizando nos de alto PageRank.
4. Caminhos minimos (allShortestPaths) entre pares de sementes: a conexao nao explicita que uma
   busca vetorial pura nao encontra.
5. Reordenacao das triplas por similaridade com a pergunta, intencao e proximidade das ancoras.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from functools import lru_cache

from app.config import OOD_THRESHOLD
from app.db import run_read
from app.embeddings import embed_passages, embed_query

REL_PT = {
    "DEVELOPED_BY": "foi desenvolvido por", "PUBLISHED_BY": "foi publicado por",
    "HAS_GENRE": "é do gênero", "AVAILABLE_ON": "está disponível em", "USES_ENGINE": "usa o motor",
    "PART_OF": "faz parte da série", "SEQUEL_OF": "é sequência de", "BASED_ON": "é baseado em",
    "HAS_FEATURE": "tem", "FEATURED_IN": "aparece em", "SUBSIDIARY_OF": "pertence a",
    "CREATED_BY": "foi criado por", "ORGANIZED_BY": "é organizado por",
}
STOP = set("""a o os as de da do das dos e em no na nos nas um uma uns umas que qual quais quem
como para por com sem sobre entre ao aos se ou mais menos foi sao são ser é ha há tem têm
the of and in on for to with by is are what which who how from that this jogo jogos game games
online""".split())
# intencao da pergunta -> tipos de relacao que respondem a ela
INTENTS = [
    (re.compile(r"desenvolv|est[úu]dio|fez|criou o jogo", re.I), {"DEVELOPED_BY"}),
    (re.compile(r"public|distribu", re.I), {"PUBLISHED_BY"}),
    (re.compile(r"g[êe]nero|tipo de jogo|estilo", re.I), {"HAS_GENRE"}),
    (re.compile(r"plataforma|console|celular|mobile|pc\b|dispon[íi]ve|roda", re.I), {"AVAILABLE_ON"}),
    (re.compile(r"motor|engine", re.I), {"USES_ENGINE"}),
    (re.compile(r"s[ée]rie|franquia", re.I), {"PART_OF"}),
    (re.compile(r"sequ[êe]ncia|sucessor|antecessor|substitu|vers[ãa]o anterior", re.I), {"SEQUEL_OF"}),
    (re.compile(r"\bmod\b|basead|inspira|origem|origin|deriv|surgiu", re.I), {"BASED_ON"}),
    (re.compile(r"gratuit|free-to-play|modelo|microtransa|passe|recurso|cross", re.I), {"HAS_FEATURE"}),
    (re.compile(r"campeonato|torneio|e-?sports?|mundial|liga", re.I), {"FEATURED_IN", "ORGANIZED_BY"}),
    (re.compile(r"dono|dona|pertence|subsidi|compr|controla|m[ãa]e", re.I), {"SUBSIDIARY_OF"}),
    (re.compile(r"quem criou|criador|fundador|fundou|diretor|designer", re.I), {"CREATED_BY"}),
]


def intent_rels(question: str) -> set[str]:
    return {r for rx, rels in INTENTS if rx.search(question) for r in rels}


NODE_KEY = """CASE WHEN {v}:Article THEN 'article:' + {v}.doc_id
                  WHEN {v}:Entity THEN 'entity:' + {v}.id END"""
NODE_MAP = """{{key: {k}, label: head([l IN labels({v}) WHERE l IN
               ['Article','Game','Company','Person','Genre','Platform','Engine','Franchise',
                'Event','Concept']]),
               name: coalesce({v}.name, {v}.title), pagerank: coalesce({v}.pagerank, 0.0),
               community: {v}.community, description: {v}.description}}"""


def _node(v: str) -> str:
    return NODE_MAP.format(k=NODE_KEY.format(v=v), v=v)


EDGE_RETURN = f"""RETURN DISTINCT elementId(r) AS rid, type(r) AS rel, r.evidence AS evidence,
       r.doc_id AS doc_id, {_node('startNode(r)')} AS src, {_node('endNode(r)')} AS dst"""
CHUNK_RETURN = """MATCH (node)-[:PART_OF]->(a:Article)
        OPTIONAL MATCH (a)-[:DESCRIBES]->(s:Entity)
        RETURN node.id AS id, node.text AS text, a.doc_id AS doc_id, a.title AS title,
               a.url AS url, elementId(s) AS eid, s.name AS subject, score"""


@dataclass
class RetrievalResult:
    question: str
    seeds: list[dict] = field(default_factory=list)
    chunks: list[dict] = field(default_factory=list)
    triples: list[dict] = field(default_factory=list)
    paths: list[list[str]] = field(default_factory=list)
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    cypher: list[dict] = field(default_factory=list)
    timings_ms: dict = field(default_factory=dict)
    seed_strength: float = 0.0
    exact_links: list[str] = field(default_factory=list)

    @property
    def linkage(self) -> float:
        """1.0 se a pergunta cita entidade pelo nome; senao, cosseno normalizado. O e5 da
        ~0.90 ate para perguntas fora do dominio, por isso a faixa estreita."""
        if self.exact_links:
            return 1.0
        return max(0.0, min(1.0, (self.seed_strength - OOD_THRESHOLD) / 0.025))

    @property
    def out_of_domain(self) -> bool:
        return not self.exact_links and self.seed_strength < OOD_THRESHOLD


def lucene_query(text: str) -> str:
    toks = [t for t in re.findall(r"[\wÀ-ÿ\-]+", text) if len(t) > 2 and t.lower() not in STOP]
    esc = [re.sub(r'([+\-&|!(){}\[\]^"~*?:\\/])', r"\\\1", t) for t in toks]
    return " OR ".join(esc) or "*"


# O grafo esta em ingles e as perguntas em portugues: termos-chave do dominio
PT_GLOSSARY = {
    "gratuito": "Free-to-play", "gratuitos": "Free-to-play", "de graça": "Free-to-play",
    "jogo de tiro em primeira pessoa": "First-person shooter", "tiro em primeira pessoa":
    "First-person shooter", "tiro tático": "Tactical shooter", "tiro de heróis": "Hero shooter",
    "arena de batalha": "Multiplayer online battle arena", "moba": "Multiplayer online battle arena",
    "mmorpg": "MMORPG", "rpg online": "MMORPG", "battle royale": "Battle royale",
    "e-sports": "Esports", "esports": "Esports", "esporte eletrônico": "Esports",
    "microtransações": "Microtransactions", "passe de batalha": "Battle pass",
    "jogo cruzado": "Cross-platform play", "multiplataforma": "Cross-platform play",
    "acesso antecipado": "Early access", "modificação": "Mod", "celular": "Android",
    "celulares": "Android", "mundial de league of legends": "League of Legends World Championship",
}


@lru_cache(maxsize=1)
def _dictionary() -> list[tuple[str, str, str]]:
    """(forma em minusculas, elementId, nome) para entidades e glossario PT."""
    rows = run_read("""MATCH (e:Entity) UNWIND [e.name] + coalesce(e.aliases, []) AS form
                       RETURN toLower(form) AS form, elementId(e) AS eid, e.name AS name""")
    by_name = {r["name"]: r["eid"] for r in rows}
    rows += [{"form": pt, "eid": by_name[en], "name": en}
             for pt, en in PT_GLOSSARY.items() if en in by_name]
    return [(r["form"], r["eid"], r["name"]) for r in rows if len(r["form"]) >= 3]


def dictionary_links(question: str) -> list[dict]:
    q = question.lower()
    hits: dict[str, dict] = {}
    for form, eid, name in _dictionary():
        if re.search(r"(?<![\w-])" + re.escape(form) + r"(?![\w-])", q):
            if eid not in hits or len(form) > hits[eid]["len"]:
                hits[eid] = {"eid": eid, "name": name, "len": len(form), "form": form}
    # descarta formas contidas em outra mais longa (ex.: 'Dota' dentro de 'Dota 2')
    kept: list[dict] = []
    for h in sorted(hits.values(), key=lambda h: -h["len"]):
        if not any(re.search(r"(?<![\w-])" + re.escape(h["form"]) + r"(?![\w-])", k["form"])
                   for k in kept):
            kept.append(h)
    return kept


def _log(res: RetrievalResult, step: str, query: str, params: dict) -> None:
    shown = {k: (f"<vetor {len(v)}d>" if isinstance(v, list) and v and isinstance(v[0], float)
                 else v) for k, v in params.items()}
    res.cypher.append({"step": step, "query": " ".join(query.split()), "params": shown})


def _q(res: RetrievalResult, step: str, query: str, **params) -> list[dict]:
    _log(res, step, query, params)
    return run_read(query, **params)


def retrieve(question: str, k: int = 8, hops: int = 2, max_triples: int = 30) -> RetrievalResult:
    hops = max(1, min(int(hops), 3))
    res = RetrievalResult(question)
    t0 = time.perf_counter()
    qv = embed_query(question)
    res.timings_ms["embed"] = round((time.perf_counter() - t0) * 1000)

    # 1. linkagem de entidades: vetor + fulltext + dicionario, fundidos por RRF
    t = time.perf_counter()
    vec = _q(res, "vetorial: entidades", """
        CALL db.index.vector.queryNodes('entity_vector', $k, $qv) YIELD node, score
        RETURN elementId(node) AS eid, node.name AS name, score""", k=k, qv=qv)
    ft = _q(res, "fulltext: entidades", """
        CALL db.index.fulltext.queryNodes('entity_fulltext', $q) YIELD node, score
        RETURN elementId(node) AS eid, node.name AS name, score LIMIT $k""",
            q=lucene_query(question), k=k)
    dic = dictionary_links(question)
    fused: dict[str, dict] = {}
    for source, rows in (("vetorial", vec), ("fulltext", ft)):
        for rank, r in enumerate(rows):
            f = fused.setdefault(r["eid"], {"eid": r["eid"], "name": r["name"], "score": 0.0,
                                            "sources": []})
            f["score"] += 1 / (60 + rank)
            f["sources"].append(source)
    for d in dic:
        f = fused.setdefault(d["eid"], {"eid": d["eid"], "name": d["name"], "score": 0.0,
                                        "sources": []})
        f["score"] += 0.05  # nome exato na pergunta pesa mais que qualquer posicao no ranking
        f["sources"].append("dicionário")
    seeds = sorted(fused.values(), key=lambda s: -s["score"])
    exact = [s for s in seeds if "dicionário" in s["sources"]]
    # sem nome exato, so sao ancoras as sementes confirmadas por vetor e fulltext ao mesmo tempo
    agreed = [s for s in seeds if s not in exact and len(set(s["sources"])) > 1]
    seeds = (exact + agreed + [s for s in seeds if s not in exact and s not in agreed]
             )[:max(4, len(exact))]
    anchors = [s["eid"] for s in exact + agreed][:4]
    res.seed_strength = max([r["score"] for r in vec[:1]] or [0.0])
    res.exact_links = [s["name"] for s in exact]

    # 2. trechos por busca vetorial; o artigo do trecho ancora a entidade que ele descreve
    res.chunks = _q(res, "vetorial: trechos", f"""
        CALL db.index.vector.queryNodes('chunk_vector', 4, $qv) YIELD node, score
        {CHUNK_RETURN}""", qv=qv)
    for c in res.chunks[:2]:
        if c["eid"] and c["eid"] not in {s["eid"] for s in seeds}:
            seeds.append({"eid": c["eid"], "name": c["subject"], "score": c["score"] / 100,
                          "sources": ["trecho"]})
    if len(anchors) < 2 and res.chunks and res.chunks[0]["eid"]:
        anchors.append(res.chunks[0]["eid"])  # garante ao menos um par para o caminho minimo
    anchors = list(dict.fromkeys(anchors))
    res.seeds = seeds
    res.timings_ms["link"] = round((time.perf_counter() - t) * 1000)

    # 3. travessia multi-hop a partir das sementes (so entre entidades)
    t = time.perf_counter()
    hop_rows = _q(res, f"multi-hop: vizinhança até {hops} saltos", f"""
        MATCH (s:Entity) WHERE elementId(s) IN $seeds
        MATCH path = (s)-[*1..{hops}]-(n:Entity)
        WHERE all(x IN nodes(path) WHERE x:Entity)
        WITH path, reduce(acc = 0.0, x IN nodes(path) | acc + coalesce(x.pagerank, 0)) AS pr
        ORDER BY pr DESC LIMIT 400
        UNWIND relationships(path) AS r
        {EDGE_RETURN}""", seeds=[s["eid"] for s in seeds])

    # 3b. relacoes pedidas pela pergunta ("quem criou", "quem desenvolveu") no 1o e 2o salto:
    # o corte por PageRank acima descarta nos especificos como pessoas e estudios pequenos
    wanted = sorted(intent_rels(question))
    if wanted:
        hop_rows += _q(res, f"intenção: {', '.join(wanted)} a partir das âncoras", f"""
            MATCH (s:Entity) WHERE elementId(s) IN $anchors
            MATCH (s)-[*0..1]-(m:Entity)-[r]-(:Entity) WHERE type(r) IN $rels
            WITH DISTINCT r LIMIT 60
            {EDGE_RETURN}""", anchors=anchors or [s["eid"] for s in seeds[:2]], rels=wanted)

    # 4. caminhos minimos entre pares de ancoras
    pairs = [[a, b] for i, a in enumerate(anchors) for b in anchors[i + 1:]]
    path_rows = _q(res, "allShortestPaths entre âncoras", f"""
        UNWIND $pairs AS pair
        MATCH (a:Entity), (b:Entity) WHERE elementId(a) = pair[0] AND elementId(b) = pair[1]
        MATCH p = allShortestPaths((a)-[*..4]-(b))
        WHERE all(x IN nodes(p) WHERE x:Entity)
        // caminhos por nos especificos (baixo PageRank) explicam mais que hubs como "Windows"
        WITH pair, p ORDER BY reduce(s = 0.0, x IN nodes(p) | s + coalesce(x.pagerank, 0))
        WITH pair, collect(p)[0..3] AS ps
        UNWIND range(0, size(ps) - 1) AS i
        UNWIND relationships(ps[i]) AS r
        WITH pair + [toString(i)] AS pair, r
        {EDGE_RETURN}, pair""", pairs=pairs) if pairs else []
    res.timings_ms["traverse"] = round((time.perf_counter() - t) * 1000)

    # 5. reordena e monta o subgrafo
    t = time.perf_counter()
    edges: dict[str, dict] = {}
    on_path: dict[str, set] = {}
    for r in hop_rows + path_rows:
        edges.setdefault(r["rid"], r)
        if "pair" in r:
            on_path.setdefault(r["rid"], set()).add(tuple(r["pair"]))
    edge_list = list(edges.values())
    if edge_list:
        wanted = set(wanted)
        anchor_keys = _keys_of(anchors)
        near = {n for e in edge_list for n in (e["src"]["key"], e["dst"]["key"])
                if anchor_keys & {e["src"]["key"], e["dst"]["key"]}}
        vecs = embed_passages([triple_text(e) for e in edge_list])
        for e, v in zip(edge_list, vecs):
            ends = {e["src"]["key"], e["dst"]["key"]}
            e["score"] = (sum(a * b for a, b in zip(qv, v))
                          + (0.05 if e["rid"] in on_path else 0)
                          + (0.06 if e["rel"] in wanted else 0)
                          + (0.06 if ends & anchor_keys else 0.03 if ends & near else 0))
        edge_list.sort(key=lambda e: -e["score"])
    keep = [e for e in edge_list if e["rid"] in on_path]
    keep += [e for e in edge_list if e["rid"] not in on_path][:max(0, max_triples - len(keep))]
    keep.sort(key=lambda e: -e["score"])
    for i, e in enumerate(keep, 1):
        e["tid"] = f"T{i}"
    tid = {e["rid"]: e["tid"] for e in keep}
    res.triples = [{"id": e["tid"], "src": e["src"]["name"], "src_key": e["src"]["key"],
                    "rel": e["rel"], "dst": e["dst"]["name"], "dst_key": e["dst"]["key"],
                    "evidence": e["evidence"], "doc_id": e["doc_id"],
                    "score": round(e["score"], 3), "on_shortest_path": e["rid"] in on_path}
                   for e in keep]
    by_pair: dict[tuple, list[str]] = {}
    for rid, prs in on_path.items():
        for pr in prs:
            by_pair.setdefault(pr, []).append(tid[rid])
    res.paths = [sorted(v, key=lambda x: int(x[1:])) for v in by_pair.values() if len(v) > 1]
    nodes = {}
    for e in keep:
        for n in (e["src"], e["dst"]):
            nodes[n["key"]] = n
    seed_names = {s["name"] for s in seeds}
    res.nodes = [{**n, "seed": n["name"] in seed_names} for n in nodes.values()]
    res.edges = [{"id": e["tid"], "source": e["src"]["key"], "target": e["dst"]["key"],
                  "rel": e["rel"], "on_shortest_path": e["rid"] in on_path} for e in keep]
    res.timings_ms["rerank"] = round((time.perf_counter() - t) * 1000)
    return res


def _keys_of(eids: list[str]) -> set[str]:
    if not eids:
        return set()
    rows = run_read(f"MATCH (n) WHERE elementId(n) IN $ids RETURN {NODE_KEY.format(v='n')} AS k",
                    ids=eids)
    return {r["k"] for r in rows}


def triple_text(e: dict) -> str:
    return (f"{e['src']['name']} {REL_PT.get(e['rel'], e['rel'])} {e['dst']['name']}. "
            f"{e.get('evidence') or ''}")


def retrieve_vector_only(question: str, k: int = 5) -> RetrievalResult:
    """Baseline RAG vetorial puro: so os k trechos mais similares."""
    res = RetrievalResult(question)
    t0 = time.perf_counter()
    qv = embed_query(question)
    res.chunks = _q(res, "vetorial: trechos (baseline)", f"""
        CALL db.index.vector.queryNodes('chunk_vector', $k, $qv) YIELD node, score
        {CHUNK_RETURN}""", k=k, qv=qv)
    res.seed_strength = max([c["score"] for c in res.chunks[:1]] or [0.0])
    res.nodes = [{"key": f"article:{c['doc_id']}", "label": "Article", "name": c["title"],
                  "pagerank": 0.0, "community": None, "seed": True}
                 for c in {c["doc_id"]: c for c in res.chunks}.values()]
    res.timings_ms["total"] = round((time.perf_counter() - t0) * 1000)
    return res
