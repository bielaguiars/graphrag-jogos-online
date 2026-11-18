"""Interface Streamlit do GraphRAG/KAG sobre jogos online (artigos da Wikipedia).

Uso (na pasta backend/): uv run streamlit run streamlit_app.py
"""
from __future__ import annotations

import html
import json
import re

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network

from app.config import LLM_MODEL, RESULTS_DIR, llm_enabled
from app.db import run_read
from app.pipeline import EXAMPLES, answer_question, health, overview, stats

st.set_page_config(page_title="GraphRAG Jogos", page_icon="🕸️", layout="wide")

TYPE_COLOR = {"Game": "#4f9dff", "Company": "#e8b84f", "Person": "#f58b62", "Genre": "#5fd08a",
              "Platform": "#a7adc4", "Engine": "#c38ff0", "Franchise": "#f07ab0",
              "Event": "#ff6b6b", "Concept": "#5cd3e8", "Article": "#e7e9ec"}
TYPE_LABEL = {"Game": "Jogo", "Company": "Empresa", "Person": "Pessoa", "Genre": "Gênero",
              "Platform": "Plataforma", "Engine": "Motor", "Franchise": "Franquia",
              "Event": "Campeonato", "Concept": "Conceito", "Article": "Artigo"}
REL_LABEL = {"DEVELOPED_BY": "desenvolvido por", "PUBLISHED_BY": "publicado por",
             "HAS_GENRE": "gênero", "AVAILABLE_ON": "disponível em", "USES_ENGINE": "usa o motor",
             "PART_OF": "série", "SEQUEL_OF": "sequência de", "BASED_ON": "baseado em",
             "HAS_FEATURE": "tem", "FEATURED_IN": "aparece em", "SUBSIDIARY_OF": "pertence a",
             "CREATED_BY": "criado por", "ORGANIZED_BY": "organizado por"}
STEP_LABEL = {"embed": "embedding da pergunta", "link": "linkagem de entidades",
              "traverse": "travessia + caminhos mínimos", "rerank": "reordenação", "total": "total"}
LEVEL_COLOR = {"alta": "#5fd08a", "média": "#f2b84b", "baixa": "#ff6b6b"}
ACCENT, HL, CANVAS, SEAM, TEXT, MUTED = "#4f9dff", "#ffd166", "#0f1114", "#3a414c", "#e7e9ec", "#8e97a3"

st.markdown(f"""
<style>
.block-container {{ padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1500px; }}
.cite {{ font: 600 0.78em ui-monospace, Menlo, monospace; padding: 1px 5px; border-radius: 4px;
        border: 1px solid {ACCENT}88; background: {ACCENT}22; color: #9cc7ff; white-space: nowrap; }}
.cite.hl {{ background: {HL}; border-color: {HL}; color: #1a1406; }}
.answer p {{ margin: 0 0 .55rem; line-height: 1.6; }}
.answer .bullet {{ padding-left: 1rem; position: relative; }}
.answer .bullet:before {{ content: ""; position: absolute; left: .2rem; top: .7em; width: 5px;
        height: 5px; border-radius: 50%; background: {MUTED}; }}
.triple {{ border-bottom: 1px solid #262b33; padding: .7rem 0; }}
.triple .head {{ display: flex; gap: .5rem; align-items: center; font-size: .85rem; }}
.triple .tid {{ font: 600 .8rem ui-monospace, Menlo, monospace; color: #9cc7ff; }}
.triple.hl .tid {{ color: {HL}; }}
.tag {{ font-size: .72rem; padding: 0 6px; border-radius: 3px; border: 1px solid {ACCENT}99; color: #9cc7ff; }}
.score {{ margin-left: auto; font: .8rem ui-monospace, Menlo, monospace; color: {MUTED}; }}
.spo {{ margin: .3rem 0; }} .rel {{ color: {MUTED}; font-size: .88rem; }}
.ev {{ background: {CANVAS}; border-radius: 4px; padding: .4rem .6rem; color: #c3c8cf; font-size: .88rem; }}
.legend {{ display: flex; flex-wrap: wrap; gap: .3rem 1rem; font-size: .8rem; color: #c3c8cf; }}
.legend i {{ display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 5px; }}
.meter {{ height: 6px; border-radius: 3px; background: #232830; overflow: hidden; margin: .3rem 0 .6rem; }}
.meter span {{ display: block; height: 100%; }}
</style>""", unsafe_allow_html=True)


# ---------- dados em cache ----------
@st.cache_resource(show_spinner="Carregando o modelo de embeddings…")
def _warmup() -> bool:
    from app.embeddings import embed_query
    embed_query("aquecimento")
    return True


@st.cache_data(ttl=60, show_spinner=False)
def _health() -> dict:
    return health()


@st.cache_data(show_spinner=False)
def _overview() -> dict:
    return overview()


@st.cache_data(show_spinner=False)
def _articles() -> dict:
    return {r["doc_id"]: r for r in run_read(
        "MATCH (a:Article) RETURN a.doc_id AS doc_id, a.title AS title, a.url AS url")}


@st.cache_data(show_spinner=False)
def _stats() -> dict:
    return stats()


@st.cache_data(show_spinner=False)
def _ask(question: str, mode: str, hops: int, use_llm: bool) -> dict:
    return answer_question(question, mode, hops, use_llm)


# ---------- grafo ----------
def graph_html(nodes: list[dict], edges: list[dict], highlight: str | None) -> str:
    net = Network(height="560px", width="100%", bgcolor=CANVAS, font_color=TEXT, directed=True,
                  cdn_resources="remote")
    focus_nodes: set[str] = set()
    if highlight:
        for e in edges:
            if e["id"] == highlight:
                focus_nodes = {e["source"], e["target"]}
    keys = {n["key"] for n in nodes}
    for n in nodes:
        dim = bool(highlight) and n["key"] not in focus_nodes
        color = TYPE_COLOR.get(n["label"], "#5cd3e8")
        border = HL if n["key"] in focus_nodes else (TEXT if n.get("seed") else color)
        net.add_node(
            n["key"], label=n["name"][:34],
            title=f"{n.get('title') or n['name']}\n{TYPE_LABEL.get(n['label'], n['label'])}"
                  f" · PageRank {n['pagerank']:.3f} · comunidade {n.get('community')}",
            color={"background": color + ("33" if dim else ""), "border": border + ("33" if dim else "")},
            borderWidth=4 if n["key"] in focus_nodes else (3 if n.get("seed") else 1),
            size=10 + min(26, (n["pagerank"] ** 0.5) * 9),
            font={"color": TEXT if not dim else MUTED, "size": 13, "strokeWidth": 3,
                  "strokeColor": CANVAS})
    for e in edges:
        if e["source"] not in keys or e["target"] not in keys:
            continue
        is_hl = e["id"] == highlight
        dim = bool(highlight) and not is_hl
        color = HL if is_hl else (ACCENT if e.get("on_shortest_path") else SEAM)
        net.add_edge(e["source"], e["target"], label=REL_LABEL.get(e["rel"], e["rel"]),
                     title=f"{e['id']} · {e['rel']}", color=color + ("33" if dim else ""),
                     width=4 if is_hl else (2.4 if e.get("on_shortest_path") else 1.2),
                     font={"color": MUTED, "size": 10, "strokeWidth": 0, "align": "middle"},
                     arrows={"to": {"enabled": True, "scaleFactor": 0.5}})
    net.set_options(json.dumps({
        "physics": {"solver": "forceAtlas2Based",
                    "forceAtlas2Based": {"gravitationalConstant": -60, "springLength": 110},
                    "stabilization": {"iterations": 200}},
        "interaction": {"hover": True, "tooltipDelay": 120},
        "edges": {"smooth": {"type": "continuous"}},
    }))
    # o template do pyvis traz moldura clara do bootstrap; o canvas segue o tema escuro
    css = (f"<style>html,body{{margin:0;background:{CANVAS}}} .card{{border:0!important;"
           f"background:{CANVAS}!important}} #mynetwork{{border:0!important}}</style>")
    return net.generate_html().replace("</head>", css + "</head>", 1)


def legend() -> None:
    items = "".join(f'<span><i style="background:{c}"></i>{TYPE_LABEL[t]}</span>'
                    for t, c in TYPE_COLOR.items())
    st.markdown(f'<div class="legend">{items}<span><i style="background:{ACCENT};border-radius:2px;'
                f'height:3px;width:16px"></i>caminho mínimo</span>'
                f'<span><i style="background:{HL}"></i>destaque</span></div>',
                unsafe_allow_html=True)


# ---------- resposta ----------
CITE = re.compile(r"\[(T\d+|C\d+|Q)\]")


def render_answer(text: str, highlight: str | None) -> None:
    out = []
    for line in [ln for ln in text.split("\n") if ln.strip()]:
        bullet = line.startswith("- ")
        safe = html.escape(line[2:] if bullet else line)  # texto vem da Wikipedia/LLM: escapar
        safe = CITE.sub(lambda m: f'<span class="cite{" hl" if m.group(1) == highlight else ""}">'
                                  f'{m.group(1)}</span>', safe)
        out.append(f'<p class="{"bullet" if bullet else ""}">{safe}</p>')
    st.markdown(f'<div class="answer">{"".join(out)}</div>', unsafe_allow_html=True)


def render_confidence(r: dict) -> None:
    c = r["confidence"]
    color = LEVEL_COLOR[c["level"]]
    st.markdown(f"**Confiança:** <span style='color:{color};font-weight:600'>{c['level']} "
                f"({c['score']:.2f})</span><div class='meter'><span style='width:{c['score'] * 100}%;"
                f"background:{color}'></span></div>", unsafe_allow_html=True)
    comp = c["components"]
    a, b, d = st.columns(3)
    a.metric("Linkagem", f"{comp['linkagem']:.2f}", help="1.0 quando a pergunta cita uma entidade "
             "do grafo pelo nome; senão, similaridade vetorial normalizada.")
    b.metric("Estrutura", f"{comp['estrutura']:.2f}", help="1.0 quando há caminho mínimo entre "
             "entidades da pergunta.")
    d.metric("Fundamentação", f"{comp['fundamentacao']:.2f}", help="Fração das frases da resposta "
             "com citação válida.")
    if r["invalid_citations"] or r["unsupported_sentences"]:
        st.warning(f"Verificador: {len(r['invalid_citations'])} citação(ões) inexistente(s) "
                   f"removida(s), {len(r['unsupported_sentences'])} frase(s) sem apoio no grafo.")
    if r.get("llm_error"):
        st.warning(f"A API do Claude falhou ({r['llm_error']}); resposta extrativa no lugar.")


def render_triples(triples: list[dict], highlight: str | None) -> None:
    if not triples:
        st.info("Nenhuma tripla: no modo só vetorial o grafo não é consultado.")
        return
    parts = []
    for t in triples:
        tag = '<span class="tag">caminho mínimo</span>' if t["on_shortest_path"] else ""
        ev = f'<div class="ev">“{html.escape(t["evidence"])}”</div>' if t.get("evidence") else ""
        art = _articles().get(t.get("doc_id") or "")
        link = (f'<a href="{art["url"]}" target="_blank">Wikipedia: {html.escape(art["title"])}</a>'
                if art else "")
        parts.append(
            f'<div class="triple{" hl" if t["id"] == highlight else ""}"><div class="head">'
            f'<span class="tid">{t["id"]}</span>{tag}<span class="score">{t["score"]:.3f}</span></div>'
            f'<div class="spo"><b>{html.escape(t["src"])}</b> <span class="rel">'
            f'{REL_LABEL.get(t["rel"], t["rel"])}</span> <b>{html.escape(t["dst"])}</b></div>'
            f'{ev}<small>{link}</small></div>')
    st.markdown("".join(parts), unsafe_allow_html=True)


def render_eval() -> None:
    f = RESULTS_DIR / "eval.json"
    if not f.exists():
        st.info("Rode `uv run python -m app.eval.run_eval` para gerar a avaliação.")
        return
    data = json.loads(f.read_text(encoding="utf-8"))
    labels = {"recall_mean": "Recall@contexto (média)", "full_support_rate": "Suporte completo",
              "recall_1hop": "Recall — 1 salto", "recall_multihop": "Recall — 2+ saltos",
              "ctx_chars_mean": "Contexto médio (caracteres)",
              "latency_ms_median": "Latência mediana (ms)",
              "ood_abstention_rate": "Abstenção fora do domínio",
              "false_abstention_rate": "Abstenção indevida",
              "answer_recall_mean": "Recall na resposta do LLM",
              "unsupported_sentences_total": "Frases sem apoio"}
    s = data["summary"]
    st.dataframe(pd.DataFrame([{"Métrica": lab, "GraphRAG": s["graph"][k], "RAG vetorial": s["vector"][k]}
                               for k, lab in labels.items() if k in s["graph"]]),
                 hide_index=True, use_container_width=True)
    st.dataframe(pd.DataFrame([{"Pergunta": r["question"], "Saltos": r["hops"],
                                "GraphRAG": r["graph"]["recall"], "Vetorial": r["vector"]["recall"],
                                "Faltou no GraphRAG": ", ".join(r["graph"]["missing"])}
                               for r in data["rows"]]), hide_index=True, use_container_width=True)


# ---------- pagina ----------
hstate = _health()
with st.sidebar:
    st.markdown("### GraphRAG · KAG\nJogos online · Wikipedia")
    if hstate["neo4j"]:
        st.success(f"Neo4j conectado · {hstate['nodes']:,} nós".replace(",", "."))
    else:
        st.error("Neo4j offline. Rode `docker compose up -d` e a ingestão.")
    if llm_enabled():
        st.success(f"Claude ativo · {LLM_MODEL}")
    else:
        st.warning("Modo extrativo: sem ANTHROPIC_API_KEY, a resposta é montada das triplas.")
    mode = st.radio("Recuperação", ["graph", "vector"], horizontal=True,
                    format_func=lambda m: "GraphRAG" if m == "graph" else "Só vetorial")
    hops = st.slider("Saltos na travessia", 1, 3, 2, disabled=mode == "vector")
    use_llm = st.toggle("Gerar com Claude", value=llm_enabled(), disabled=not llm_enabled())
    st.markdown("#### Perguntas de exemplo")
    for ex in EXAMPLES:
        if st.button(ex, use_container_width=True):
            st.session_state["question"] = ex
            st.session_state["submitted"] = ex

if not hstate["neo4j"]:
    st.stop()
_warmup()

st.markdown("## Pergunte ao grafo de conhecimento")
qp = st.query_params.get("q")
if qp and "submitted" not in st.session_state:  # link direto: ?q=pergunta
    st.session_state["question"] = st.session_state["submitted"] = qp

with st.form("ask", border=False):
    q = st.text_area("Pergunta", key="question", height=80, max_chars=500,
                     placeholder="Ex.: Quais trabalhos superam o Chain-of-Thought?",
                     label_visibility="collapsed")
    if st.form_submit_button("Perguntar", type="primary") and len(q.strip()) >= 3:
        st.session_state["submitted"] = q.strip()

question = st.session_state.get("submitted")
result = None
if question:
    with st.spinner("Consultando o grafo…"):
        result = _ask(question, mode, hops, use_llm)

left, right = st.columns([5, 7], gap="large")
if result is None:
    with left:
        st.markdown(
            "Cada resposta vem com o **caminho no grafo** que a sustenta: triplas extraídas de 65 "
            "artigos da Wikipedia sobre jogos online, cada uma com a frase literal do artigo como "
            "evidência. Perguntas fora "
            "da base recebem um *não encontrei* em vez de uma resposta inventada.\n\n"
            "Escolha uma pergunta de exemplo na barra lateral ou escreva a sua.")
        s = _stats()
        st.markdown("##### Entidades mais centrais (PageRank)")
        st.dataframe(pd.DataFrame(s["top_pagerank"]).rename(columns={
            "name": "Entidade", "type": "Tipo", "pagerank": "PageRank", "mentions": "Artigos"}),
            hide_index=True, use_container_width=True)
    with right:
        st.markdown("##### Núcleo do grafo (45 entidades de maior PageRank)")
        o = _overview()
        components.html(graph_html(o["nodes"], o["edges"], None), height=580)
        legend()
    st.stop()

options = ["(nenhuma)"] + [f"{t['id']} · {t['src']} {REL_LABEL.get(t['rel'], t['rel'])} {t['dst']}"
                           for t in result["triples"]]
with left:
    badge = "Gerada por Claude" if result["generation_mode"] == "llm" else "Extrativa (sem LLM)"
    st.caption(f"{badge} · {'GraphRAG' if result['retrieval_mode'] == 'graph' else 'Só vetorial'}")
    pick = st.selectbox("Destacar no grafo", options, index=0,
                        help="Escolha uma tripla citada para acendê-la no subgrafo e na lista.")
    highlight = None if pick == "(nenhuma)" else pick.split(" · ")[0]
    render_answer(result["answer"], highlight)
    st.divider()
    render_confidence(result)
    if result["seeds"]:
        st.markdown("##### Entidades ligadas à pergunta")
        st.markdown("\n".join(f"- {s['name']} · *{' + '.join(dict.fromkeys(s['sources']))}*"
                              for s in result["seeds"]))

with right:
    g = result["graph"]
    st.markdown(f"##### Subgrafo usado na resposta · {len(g['nodes'])} nós · {len(g['edges'])} arestas")
    if g["nodes"]:
        components.html(graph_html(g["nodes"], g["edges"], highlight), height=580)
        legend()
    else:
        st.info("O modo só vetorial não percorre o grafo: a resposta usa apenas trechos dos artigos.")

tabs = st.tabs([f"Triplas ({len(result['triples'])})", f"Cypher ({len(result['cypher'])})",
                f"Nós ({len(result['graph']['nodes'])})", f"Trechos ({len(result['chunks'])})",
                "Tempos", "Avaliação"])
with tabs[0]:
    render_triples(result["triples"], highlight)
with tabs[1]:
    for c in result["cypher"]:
        st.markdown(f"**{c['step']}**" + (f" · erro: `{c['error']}`" if c.get("error") else ""))
        st.code(c["query"], language="cypher")
        if c["params"]:
            st.caption("  ·  ".join(f"${k} = {json.dumps(v, ensure_ascii=False)}"
                                    for k, v in c["params"].items())[:400])
with tabs[2]:
    st.dataframe(pd.DataFrame([{"Nó": n["name"], "Tipo": TYPE_LABEL.get(n["label"], n["label"]),
                                "PageRank": round(n["pagerank"], 3), "Comunidade": n.get("community"),
                                "Semente": "sim" if n.get("seed") else ""}
                               for n in result["graph"]["nodes"]]).sort_values("PageRank", ascending=False),
                 hide_index=True, use_container_width=True)
with tabs[3]:
    for i, c in enumerate(result["chunks"], 1):
        st.markdown(f"**C{i}** · [Wikipedia: {c['title']}]({c['url']})"
                    f" · similaridade {c['score']:.3f}")
        st.markdown(f"> {c['text']}")
with tabs[4]:
    st.dataframe(pd.DataFrame([{"Etapa": STEP_LABEL.get(k, k), "ms": v}
                               for k, v in result["timings_ms"].items()]),
                 hide_index=True, use_container_width=True)
with tabs[5]:
    render_eval()
