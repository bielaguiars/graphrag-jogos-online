"""Testes sem Neo4j nem API: resolucao de entidades, travas de Cypher, verificador de
citacoes, validacao da extracao e montagem do grafo."""
from app.generate import answer_extractive, confidence, verify_citations
from app.ingest.extract import Extraction, validate_evidence
from app.ingest.fetch_wikipedia import parse, slugify
from app.ingest.load import build_graph, chunk_text
from app.ingest.resolve import Mention, compatible, is_acronym, norm_key, resolve
from app.retrieval.hybrid import RetrievalResult, intent_rels, lucene_query
from app.retrieval.text2cypher import ensure_limit, is_read_only

SAME = lambda texts: [[1.0, 0.0] for _ in texts]  # embedding identico: testa so as travas lexicais


def m(name, typ="Game", aliases=(), doc="d1"):
    return Mention(name, typ, list(aliases), "", doc)


# ---------- resolucao de entidades ----------
def test_norm_key_removes_plural_and_parenthesis():
    assert norm_key("Multiplayer online battle arenas (MOBAs)") == norm_key("multiplayer online battle arena")


def test_acronym():
    assert is_acronym("MOBA", "Multiplayer online battle arena")
    assert is_acronym("PUBG", "PlayerUnknown's Battlegrounds") is False  # apostrofo quebra a sigla
    assert is_acronym("FPS", "First-person shooter")


def test_compatible_blocks_versions_and_wrong_aliases():
    assert compatible("Unreal Engine 4", "Unreal Engine 4")
    assert not compatible("Counter-Strike", "Counter-Strike 2")
    assert not compatible("PlayStation 4", "PlayStation 5")
    assert not compatible("Valve", "Riot Games")
    assert compatible("Valve", "Valve Corporation")
    assert not compatible("Riot Games", "Epic Games")


def test_resolve_merges_aliases_and_spelling():
    canon, mapping = resolve([
        m("Multiplayer online battle arena", "Genre", aliases=["MOBA"], doc="a"),
        m("MOBA", "Genre", doc="b"),
        m("Free-to-play", "Concept", doc="c"), m("Free to play", "Concept", doc="d"),
    ], embed=SAME)
    assert len(canon) == 2
    assert mapping[("a", "Multiplayer online battle arena")] == mapping[("b", "MOBA")]


def test_resolve_subtitle_alias_only_when_declared():
    canon, mapping = resolve([
        m("Warcraft III: Reign of Chaos", aliases=["Warcraft III"], doc="a"),
        m("Warcraft III", doc="b"),
        m("Warcraft III: The Frozen Throne", aliases=["The Frozen Throne"], doc="c")], embed=SAME)
    assert len(canon) == 2
    assert mapping[("a", "Warcraft III: Reign of Chaos")] == mapping[("b", "Warcraft III")]


def test_resolve_semantic_step_needs_lexical_similarity():
    canon, _ = resolve([m("Dota 2", doc="a"), m("Dota Underlords", doc="b"),
                        m("Valve", "Company", doc="c"), m("Valorant", "Company", doc="d"),
                        m("Fortnite", doc="e"), m("Fortnite Battle Royale", doc="f")], embed=SAME)
    assert len(canon) == 6


def test_resolve_never_merges_different_versions():
    canon, _ = resolve([m("Overwatch", doc="a"), m("Overwatch 2", doc="b"),
                        m("Counter-Strike", doc="c"), m("Counter-Strike 2", doc="d")], embed=SAME)
    assert len(canon) == 4


# ---------- Text-to-Cypher ----------
def test_read_only_guard():
    assert is_read_only("MATCH (g:Game) RETURN g.name LIMIT 5")
    assert is_read_only("MATCH (e) WHERE e.name = 'CREATE something' RETURN e")
    for bad in ["CREATE (n:X)", "MATCH (n) DETACH DELETE n", "MATCH (n) SET n.x = 1",
                "CALL apoc.create.node(['X'], {})", "LOAD CSV FROM 'x' AS r RETURN r",
                "MATCH (n) RETURN n; MATCH (m) DELETE m", "CALL dbms.security.listUsers()",
                "CALL gds.pageRank.write('g', {writeProperty: 'p'})"]:
        assert not is_read_only(bad), bad


def test_ensure_limit():
    assert ensure_limit("MATCH (n) RETURN n").endswith("LIMIT 25")
    assert ensure_limit("MATCH (n) RETURN n LIMIT 3") == "MATCH (n) RETURN n LIMIT 3"


# ---------- geracao e verificacao ----------
def _res(**kw) -> RetrievalResult:
    r = RetrievalResult("pergunta")
    r.triples = [{"id": "T1", "src": "Dota 2", "rel": "DEVELOPED_BY", "dst": "Valve",
                  "evidence": "x", "doc_id": "dota-2", "on_shortest_path": True,
                  "src_key": "entity:dota-2", "dst_key": "entity:valve", "score": 0.9}]
    r.chunks = [{"id": "c", "text": "texto", "title": "Dota 2", "doc_id": "dota-2", "url": "u"}]
    for k, v in kw.items():
        setattr(r, k, v)
    return r


def test_verify_citations_removes_invalid_and_flags_unsupported():
    out = verify_citations("Dota 2 foi desenvolvido pela Valve [T1]. O Dota 3 será lançado em 2030 "
                           "para todos os consoles [T9]. "
                           "Esta frase longa não tem citação nenhuma e deve ser marcada.", _res())
    assert out["invalid_citations"] == ["T9"]
    assert "[T9]" not in out["answer"]
    assert len(out["unsupported_sentences"]) == 2
    assert out["cited"] == ["T1"]


def test_extractive_answer_cites_only_existing_triples():
    out = answer_extractive(_res(exact_links=["Dota 2"]))
    assert "[T1]" in out["answer"] and out["grounding"] == 1.0


def test_out_of_domain_abstains_with_low_confidence():
    r = _res(seed_strength=0.85)
    out = answer_extractive(r)
    assert out["answer"].startswith("Não encontrei")
    assert confidence(r, out["grounding"])["level"] == "baixa"


def test_confidence_high_when_entity_named_and_path_found():
    r = _res(exact_links=["Dota 2"], paths=[["T1", "T2"]])
    assert confidence(r, 1.0)["score"] == 1.0


# ---------- utilitarios da busca ----------
def test_lucene_query_escapes_and_drops_stopwords():
    q = lucene_query("Quais jogos usam o Source 2?")
    assert "Source" in q and "Quais" not in q and "jogos" not in q


def test_intent_detection():
    assert "DEVELOPED_BY" in intent_rels("Qual estúdio desenvolveu o Valorant?")
    assert "BASED_ON" in intent_rels("De qual mod surgiu o Dota?")
    assert "SUBSIDIARY_OF" in intent_rels("Qual empresa é dona da Riot Games?")
    assert "FEATURED_IN" in intent_rels("Em qual campeonato o LoL aparece?")


# ---------- ingestao ----------
TEXT = "Dota 2 is a MOBA developed and published by Valve. It is a sequel to Defense of the Ancients."


def test_validate_evidence_drops_non_literal_relations():
    ex = Extraction.model_validate({
        "doc_id": "dota-2", "subject": "Dota 2",
        "entities": [{"name": "Dota 2", "type": "Game", "aliases": [], "description": "d"},
                     {"name": "Valve", "type": "Company", "aliases": [], "description": "d"}],
        "relations": [
            {"source": "Dota 2", "type": "DEVELOPED_BY", "target": "Valve",
             "evidence": "developed and published by Valve"},
            {"source": "Dota 2", "type": "PUBLISHED_BY", "target": "Valve",
             "evidence": "Valve published it worldwide in 2013"},  # nao esta no texto
            {"source": "Dota 2", "type": "SEQUEL_OF", "target": "Defense of the Ancients",
             "evidence": "It is a sequel to Defense of the Ancients"},  # alvo fora das entidades
        ]})
    kept = validate_evidence(ex, TEXT).relations
    assert [(r.type, r.target) for r in kept] == [("DEVELOPED_BY", "Valve")]


def test_build_graph_links_articles_through_shared_entities():
    extracted = {
        "dota-2": {"subject": "Dota 2",
                   "entities": [{"name": "Dota 2", "type": "Game", "aliases": []},
                                {"name": "Valve", "type": "Company", "aliases": ["Valve Corporation"]}],
                   "relations": [{"source": "Dota 2", "type": "DEVELOPED_BY", "target": "Valve",
                                  "evidence": "e"}]},
        "cs2": {"subject": "Counter-Strike 2",
                "entities": [{"name": "Counter-Strike 2", "type": "Game", "aliases": []},
                             {"name": "Valve Corporation", "type": "Company", "aliases": []}],
                "relations": [{"source": "Counter-Strike 2", "type": "DEVELOPED_BY",
                               "target": "Valve Corporation", "evidence": "e"},
                              {"source": "Counter-Strike 2", "type": "INVENTED", "target": "Valve Corporation",
                               "evidence": "e"}]},
    }
    canon, edges, subjects, dropped = build_graph(extracted)
    assert len(canon) == 3 and dropped == 1
    assert {e["dst"] for e in edges} == {"valve"}  # as duas mencoes da Valve viraram um no
    assert subjects == {"dota-2": "dota-2", "cs2": "counter-strike-2"}


def test_chunk_text():
    assert chunk_text("A. B. C. D.", size=3) == ["A. B. C.", "D."]


def test_wikipedia_parse_skips_missing_pages():
    payload = {"query": {"pages": [
        {"title": "Dota 2", "extract": "Dota 2 is a\n MOBA.", "fullurl": "https://en.wikipedia.org/wiki/Dota_2"},
        {"title": "Inexistente", "missing": True}]}}
    [d] = parse(payload)
    assert d == {"doc_id": "dota-2", "title": "Dota 2", "text": "Dota 2 is a MOBA.",
                 "url": "https://en.wikipedia.org/wiki/Dota_2", "source": "wikipedia-en"}
    assert slugify("Pokémon Go") == "pok-mon-go"
