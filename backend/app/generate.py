"""Geracao da resposta ancorada no subgrafo (KAG) e verificacao de citacoes.

Com ANTHROPIC_API_KEY: Claude responde so a partir das triplas [T#] e trechos [C#] e cita
cada afirmacao. Depois, um verificador remove citacoes inexistentes e conta frases sem apoio.
Sem chave: resposta extrativa montada direto das triplas (nunca inventa, mas nao sintetiza).
"""
from __future__ import annotations

import json
import re
from collections import defaultdict

from app.config import LLM_MODEL
from app.retrieval.hybrid import REL_PT, RetrievalResult, intent_rels

SYSTEM = """Voce e um assistente que responde perguntas sobre jogos online usando
APENAS o contexto fornecido: triplas de um grafo de conhecimento [T#] e trechos de artigos da Wikipedia [C#].
Regras:
- Responda em portugues, de forma direta, em ate 8 frases ou uma lista curta.
- Toda afirmacao factual termina com a citacao entre colchetes, ex.: [T3] ou [T1][C2].
- Em perguntas de varios saltos, explique o caminho: A -> B -> C, citando cada salto.
- Se o contexto nao basta, diga exatamente "Não encontrei essa informação no grafo." e,
  se houver, o que o grafo mostra de mais proximo. Nunca use conhecimento externo."""

CITE = re.compile(r"\[(T\d+|C\d+|Q)\]")


def build_context(res: RetrievalResult, cypher_rows: list | None = None) -> str:
    lines = ["Triplas do grafo:"]
    for t in res.triples:
        lines.append(f"[{t['id']}] ({t['src']}) -[{t['rel']}]-> ({t['dst']})"
                     f" | evidencia: \"{t['evidence'] or '-'}\" | artigo {t['doc_id']}")
    if res.paths:
        lines.append("Caminhos minimos entre entidades da pergunta: "
                     + "; ".join(" -> ".join(p) for p in res.paths))
    lines.append("Trechos de resumos:")
    for i, c in enumerate(res.chunks, 1):
        lines.append(f"[C{i}] (Wikipedia: {c['title']}) {c['text']}")
    if cypher_rows:
        lines.append("[Q] Resultado da consulta Cypher gerada: "
                     + json.dumps(cypher_rows[:25], ensure_ascii=False, default=str))
    return "\n".join(lines)


def verify_citations(answer: str, res: RetrievalResult, has_q: bool = False) -> dict:
    valid = {t["id"] for t in res.triples} | {f"C{i}" for i in range(1, len(res.chunks) + 1)}
    if has_q:
        valid.add("Q")
    cited = CITE.findall(answer)
    invalid = sorted({c for c in cited if c not in valid})
    clean = answer
    for c in invalid:
        clean = clean.replace(f"[{c}]", "")
    sentences = [s for s in re.split(r"(?<=[.!?])\s+|\n+", clean) if len(s.strip()) > 25]
    unsupported = [s.strip() for s in sentences
                   if not CITE.search(s) and "Não encontrei" not in s and not s.strip().endswith(":")]
    used = sorted({c for c in cited if c in valid}, key=lambda x: (x[0], int(x[1:] or 0)))
    grounding = 1.0 if not sentences else 1 - len(unsupported) / len(sentences)
    return {"answer": clean.strip(), "cited": used, "invalid_citations": invalid,
            "unsupported_sentences": unsupported, "grounding": round(grounding, 2)}


def answer_llm(client, res: RetrievalResult, cypher_rows: list | None = None) -> dict:
    response = client.beta.messages.create(
        model=LLM_MODEL,
        max_tokens=8000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium"},
        system=SYSTEM,
        messages=[{"role": "user", "content":
                   f"{build_context(res, cypher_rows)}\n\nPergunta: {res.question}"}],
    )
    if response.stop_reason == "refusal":
        return {"answer": "O modelo recusou a pergunta.", "cited": [], "invalid_citations": [],
                "unsupported_sentences": [], "grounding": 0.0}
    text = "".join(b.text for b in response.content if b.type == "text")
    return verify_citations(text, res, has_q=bool(cypher_rows))


def answer_extractive(res: RetrievalResult, top: int = 8) -> dict:
    """Resposta sem LLM: frases geradas das triplas mais relevantes, agrupadas por sujeito."""
    if (not res.triples and not res.chunks) or res.out_of_domain:
        return {"answer": "Não encontrei essa informação no grafo. Nenhuma entidade da pergunta "
                          "existe na base de artigos; o subgrafo exibido é só o vizinho mais "
                          "próximo e não sustenta uma resposta.", "cited": [],
                "invalid_citations": [], "unsupported_sentences": [], "grounding": 1.0}
    wanted = intent_rels(res.question)
    named = set(res.exact_links)
    near = named | {n for t in res.triples if named & {t["src"], t["dst"]} for n in (t["src"], t["dst"])}
    chosen = [t for t in res.triples if t["on_shortest_path"]]
    # estavel: primeiro a relacao pedida sobre entidades a ate 1 salto das citadas na pergunta
    rest = sorted((t for t in res.triples if not t["on_shortest_path"]),
                  key=lambda t: (t["rel"] not in wanted, t["src"] not in near))
    chosen += rest[:max(0, top - len(chosen))]
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in chosen:
        groups[t["src"]].append(t)
    parts = ["Resposta extraída do grafo (modo sem LLM):"]
    for src, ts in sorted(groups.items(), key=lambda kv: kv[0] not in named):
        facts = "; ".join(f"{REL_PT.get(t['rel'], t['rel'])} {t['dst']} [{t['id']}]" for t in ts)
        parts.append(f"- {src} {facts}.")
    if res.paths:
        tmap = {t["id"]: t for t in res.triples}
        for p in res.paths[:2]:
            chain = "; ".join(f"{tmap[x]['src']} {REL_PT.get(tmap[x]['rel'], tmap[x]['rel'])} "
                              f"{tmap[x]['dst']}" for x in p if x in tmap)
            parts.append(f"Caminho multi-hop: {chain} [{']['.join(p)}].")
    n_chunks = 1 if res.triples else 3  # sem grafo (baseline vetorial) so ha trechos
    for i, c in enumerate(res.chunks[:n_chunks], 1):
        parts.append(f"Trecho {'mais próximo ' if n_chunks == 1 else ''}({c['title']}): "
                     f"\"{c['text'][:220]}...\" [C{i}]")
    answer = "\n".join(parts)
    used = sorted({t["id"] for t in chosen}, key=lambda x: int(x[1:]))
    return {"answer": answer,
            "cited": used + [f"C{i}" for i in range(1, min(n_chunks, len(res.chunks)) + 1)],
            "invalid_citations": [], "unsupported_sentences": [], "grounding": 1.0}


def confidence(res: RetrievalResult, grounding: float) -> dict:
    """Nivel de confianca: forca da linkagem + estrutura encontrada + fundamentacao."""
    seed = res.linkage
    if res.out_of_domain:
        structure = 0.0
    elif res.paths:
        structure = 1.0
    elif len(res.triples) >= 5:
        structure = 0.6
    else:
        structure = 0.3 if res.triples else 0.0
    score = round(0.4 * seed + 0.3 * structure + 0.3 * grounding, 2)
    level = "alta" if score >= 0.7 else "média" if score >= 0.45 else "baixa"
    return {"score": score, "level": level,
            "components": {"linkagem": round(seed, 2), "estrutura": structure,
                           "fundamentacao": grounding}}
