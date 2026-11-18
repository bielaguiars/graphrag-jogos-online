"""Gera o PDF da apresentação no estilo dos trabalhos anteriores (documento A4, consulta + print).

Uso (com os prints já tirados em docs/apresentacao/prints/):
    python docs/apresentacao/gerar_pdf.py
Saída: docs/apresentacao/GraphRAG_Jogos_Online_apresentacao.pdf (e o .html usado para gerar).
"""
import html
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRINTS = HERE / "prints"
TITLE = "GraphRAG / KAG — Jogos Online"
Q = {c["shot"]: c["query"] for c in json.loads((HERE / "consultas.json").read_text(encoding="utf-8"))}

KEYWORDS = (r"OPTIONAL MATCH|MATCH|WHERE|RETURN|WITH|ORDER BY|LIMIT|CALL|YIELD|CREATE|CONSTRAINT|FULLTEXT|"
            r"VECTOR|INDEX|IF NOT EXISTS|FOR|REQUIRE|IS UNIQUE|ON EACH|ON|OPTIONS|AS|AND|OR|IN|NOT|DISTINCT|"
            r"UNWIND|MERGE|SET|DESC|SHOW|INDEXES|STARTS WITH")
TOKEN = re.compile(
    r"(?P<comment>//[^\n]*)|(?P<string>'[^']*')|(?P<label>(?<=[(\[:|])[A-Z][A-Za-z_]+(?=[\s){\]:|*]))|"
    rf"(?P<kw>\b(?:{KEYWORDS})\b)|(?P<fn>\b[a-zA-Z_.]+(?=\())"
)
COLORS = {"comment": "#9B9A97", "string": "#4D7C0F", "label": "#2F6F9F", "kw": "#A3195B", "fn": "#B35C00"}


def highlight(code: str) -> str:
    out, pos = [], 0
    for m in TOKEN.finditer(code):
        out.append(html.escape(code[pos:m.start()]))
        out.append(f'<span style="color:{COLORS[m.lastgroup]}">{html.escape(m.group())}</span>')
        pos = m.end()
    out.append(html.escape(code[pos:]))
    return "".join(out)


def inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


SCHEMA = """// Constraints de unicidade
CREATE CONSTRAINT article_id IF NOT EXISTS FOR (a:Article) REQUIRE a.doc_id IS UNIQUE;
CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE;
// RANGE (B-tree) para filtros e ordenação
CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name);
CREATE INDEX entity_pagerank IF NOT EXISTS FOR (e:Entity) ON (e.pagerank);
// ... entity_type, article_title
// FULLTEXT (Lucene)
CREATE FULLTEXT INDEX entity_fulltext IF NOT EXISTS FOR (e:Entity) ON EACH [e.name, e.aliases_text, e.description];
CREATE FULLTEXT INDEX article_fulltext IF NOT EXISTS FOR (a:Article) ON EACH [a.title, a.text];
// VECTOR: 3 índices de 384 dimensões, cosseno (entity_vector, chunk_vector, article_vector)
CREATE VECTOR INDEX chunk_vector IF NOT EXISTS FOR (n:Chunk) ON (n.embedding)
OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}};

// Conferindo
""" + Q["neo4j_indices"]

GDS = """CALL gds.graph.project('kg', ['Entity'], {ALL: {type: '*', orientation: 'UNDIRECTED'}});
CALL gds.pageRank.write('kg', {writeProperty: 'pagerank', maxIterations: 40});
CALL gds.louvain.write('kg', {writeProperty: 'community'});
// nesta carga: 23 comunidades, modularidade 0,53 (o Louvain varia um pouco a cada execução; no artigo foram 24)

"""

# blocos: ("h2", t) seção · ("h3", t) item com ▼ · ("p", t) · ("ul", [..]) · ("code", t) · ("img", arquivo, legenda)
C = [
    ("p", "Tendências em Ciência da Computação · Prof. Ricardo Roberto de Lima · 18/11/2026"),
    ("p", "**Biel Aguiar e Thiago Rocha** · Unipê Cruzeiro do Sul"),
    ("p", "Tudo roda localmente: Neo4j 5.26 (Docker) com Graph Data Science e APOC, embeddings "
          "multilingual-e5-small na própria máquina e interface em Streamlit. Sem chave de API, o sistema funciona em "
          "modo extrativo: a resposta é montada direto das triplas do grafo."),
    ("h2", "1 - Problema e dados"),
    ("p", "O RAG vetorial devolve os trechos mais parecidos com a pergunta. Isso falha em dois casos: perguntas de "
          "vários saltos, em que cada fato está num artigo diferente, e perguntas fora da base, que ele não sabe "
          "recusar. Pergunta-guia: **“Que jogo da Valve surgiu de um mod de Warcraft III?”** A resposta cruza três "
          "artigos: Dota 2, Defense of the Ancients e Warcraft III."),
    ("ul", ["**65 artigos** da Wikipedia em inglês sobre jogos online (MOBAs, battle royale, FPS, MMOs, mobile e "
            "campeonatos de e-sports), divididos em **282 trechos** de três frases.",
            "Extração: **811 entidades** e **797 relações**; depois da resolução, **351 entidades canônicas**, "
            "93 delas presentes em mais de um artigo (as pontes entre documentos).",
            "Avaliação com 26 perguntas em português: 12 de um salto, 9 de dois ou mais saltos e 5 fora do domínio."]),
    ("h2", "2 - Arquitetura"),
    ("img", ROOT / "docs" / "img" / "arquitetura.png",
     "Text-to-Graph (Wikipedia → entidades e relações) → Neo4j LPG → recuperação híbrida → interface."),
    ("h2", "3 - Pilar 1: Text-to-Graph (NER/RE com LLM)"),
    ("ul", ["Um LLM (Claude) extrai entidades e relações com saída estruturada: um JSON Schema gerado de modelos "
            "Pydantic, com **9 tipos de entidade** (Game, Company, Person, Genre, Platform, Engine, Franchise, Event, "
            "Concept) e **13 tipos de relação** (DEVELOPED_BY, BASED_ON, SEQUEL_OF, CREATED_BY, SUBSIDIARY_OF…).",
            "**Evidência literal:** cada relação traz a frase do artigo que a sustenta, e um validador descarta a "
            "relação se essa frase não aparece no texto. É a primeira barreira contra alucinação.",
            "**Resolução de entidades** em três passos (chave lexical, aliases compatíveis e semântica com cosseno "
            "≥ 0,93), com travas: nomes com números diferentes nunca se fundem (Overwatch ≠ Overwatch 2)."]),
    ("h3", "Proveniência: a relação guarda a frase de evidência e o artigo de origem"),
    ("code", Q["neo4j_proveniencia"]),
    ("img", "neo4j_proveniencia.png", ""),
    ("h2", "4 - Pilar 2: modelo LPG no Neo4j"),
    ("p", "`(:Article)-[:DESCRIBES]->(:Entity)`, `(:Chunk)-[:PART_OF]->(:Article)` e "
          "`(:Entity)-[:13 tipos {evidence, doc_id}]->(:Entity)`; cada entidade ganha também o rótulo do seu tipo "
          "(:Game, :Company…)."),
    ("h3", "Constraints de unicidade e índices RANGE, FULLTEXT e VECTOR"),
    ("code", SCHEMA),
    ("img", "neo4j_indices.png", ""),
    ("h3", "Esquema do grafo (db.schema.visualization)"),
    ("code", Q["neo4j_esquema"]),
    ("img", "neo4j_esquema.png", ""),
    ("h3", "Tamanho do grafo carregado"),
    ("code", Q["neo4j_tamanho"] + ";\n\n" + Q["neo4j_tipos"]),
    ("img", "neo4j_tamanho.png", ""),
    ("img", "neo4j_tipos.png", ""),
    ("h2", "5 - Pilar 3: recuperação híbrida e algoritmos de grafo"),
    ("ul", ["**Ligação de entidades** por três canais (vetor, fulltext e dicionário de nomes com glossário "
            "português-inglês), fundidos por Reciprocal Rank Fusion.",
            "**Travessia multi-hop** de até 2 saltos (até 3) a partir das âncoras e **allShortestPaths** entre elas, "
            "preferindo caminhos por nós pouco centrais.",
            "**Consulta por intenção:** “quem criou”, “subsidiária” viram tipos de relação. No fim, as 30 melhores "
            "triplas e os 4 trechos mais próximos formam o contexto."]),
    ("h3", "Busca vetorial nos trechos (índice VECTOR)"),
    ("code", Q["neo4j_vetor"]),
    ("img", "neo4j_vetor.png", ""),
    ("h3", "Ligação de entidades com tolerância a erro (índice FULLTEXT)"),
    ("code", Q["neo4j_fulltext"]),
    ("img", "neo4j_fulltext.png", ""),
    ("h3", "Multi-hop: o jogo da Valve que veio de um mod de Warcraft III"),
    ("code", Q["neo4j_multihop"]),
    ("img", "neo4j_multihop.png", ""),
    ("h3", "Menor caminho entre League of Legends e Dota 2 (shortestPath)"),
    ("code", Q["neo4j_caminho"]),
    ("img", "neo4j_caminho.png", ""),
    ("h3", "PageRank (GDS): centralidade usada para ordenar a vizinhança"),
    ("code", GDS + Q["neo4j_pagerank"]),
    ("img", "neo4j_pagerank.png", ""),
    ("h3", "Louvain (GDS): comunidades do grafo"),
    ("code", Q["neo4j_louvain"]),
    ("img", "neo4j_louvain.png", ""),
    ("h2", "6 - Pilar 4: interface e explicabilidade"),
    ("h3", "“Que jogo da Valve surgiu de um mod de Warcraft III?” — resposta citada e subgrafo usado"),
    ("img", "ui_multihop.png", "Cada frase cita a tripla de origem [T1], [T2]…; à direita, os 23 nós e 30 arestas usados."),
    ("h3", "Triplas citadas, com a frase de evidência de cada uma"),
    ("img", "ui_triplas.png", ""),
    ("h3", "Consultas Cypher executadas para responder"),
    ("img", "ui_cypher.png", ""),
    ("h3", "“Que jogo militar deu origem ao mod que virou o DayZ, e quem criou esse mod?”"),
    ("img", "ui_dayz.png", ""),
    ("h3", "A mesma pergunta da Valve no modo só vetorial"),
    ("img", "ui_vetorial.png", "Só vetorial: o subgrafo tem 3 nós soltos e nenhuma aresta; sem a ponte entre Dota 2 e "
                               "Warcraft III, o sistema não monta a resposta."),
    ("h3", "Pergunta fora do domínio: o sistema recusa em vez de inventar"),
    ("img", "ui_fora_dominio.png", "“Qual é a capital da França?”: nenhuma entidade da base é citada e a similaridade "
                                   "fica abaixo do limiar, então a resposta é “Não encontrei essa informação no grafo”."),
    ("h2", "7 - Redução de alucinação"),
    ("ul", ["**Na ingestão:** só entra no grafo a relação cuja frase de evidência aparece literalmente no artigo.",
            "**Na recuperação:** sem entidade citada e com similaridade abaixo de 0,924, a pergunta é tratada como "
            "fora do domínio e o sistema recusa antes de gerar.",
            "**Na geração:** toda afirmação cita uma tripla [T#] ou trecho [C#], e um verificador remove citações "
            "que não existem. Sem contexto suficiente, a resposta é “Não encontrei essa informação no grafo.”",
            "**Text-to-Cypher somente leitura:** o filtro bloqueia CREATE, MERGE, DELETE e SET, e a consulta roda "
            "numa transação de leitura. Confiança = ligação (0,4) + estrutura (0,3) + fundamentação (0,3)."]),
    ("h2", "8 - Avaliação"),
    ("ul", ["26 perguntas (12 de um salto, 9 de dois ou mais saltos e 5 fora do domínio), medindo o **contexto "
            "recuperado** contra um RAG vetorial puro no mesmo índice.",
            "**Suporte completo:** 100% no GraphRAG contra 71,4% no vetorial. **Recall em 2+ saltos:** 1,00 contra "
            "0,77. **Recusa correta fora do domínio:** 100% contra 0%.",
            "Custo: contexto cerca de 3 vezes maior (7.159 × 2.352 caracteres) e latência mediana de 320 ms contra "
            "14 ms, ainda pequena perto do tempo de geração de um LLM.",
            "Limitação: as perguntas foram escritas pela equipe a partir do grafo e dois ajustes foram feitos nesse "
            "mesmo conjunto, então os 100% mostram que o mecanismo funciona, não a taxa em perguntas novas."]),
    ("img", "ui_avaliacao.png", ""),
    ("h2", "9 - Como rodar"),
    ("code", "docker compose up -d                       # Neo4j 5.26 + GDS + APOC\n"
             "cd backend\n"
             "uv sync                                    # dependências\n"
             "uv run python -m app.ingest.load --reset   # schema, carga, embeddings, PageRank e Louvain\n"
             "uv run streamlit run streamlit_app.py      # interface\n"
             "uv run python -m app.eval.run_eval         # avaliação GraphRAG × RAG vetorial"),
    ("ul", ["Próximos passos: avaliar com perguntas independentes e com as respostas geradas, usar o texto completo "
            "dos artigos, resumir as comunidades do Louvain para perguntas globais e atualizar o grafo aos poucos."]),
]

CSS = """
@page { size: A4; margin: 22mm 20mm 22mm 20mm; }
body { font-family: 'Inter', 'Segoe UI', Arial, sans-serif; color: #37352F; font-size: 14.5px; line-height: 1.55; }
h1 { font-size: 38px; font-weight: 700; line-height: 1.15; margin: 0 0 18px; letter-spacing: -0.5px; }
h2 { font-size: 26px; font-weight: 700; margin: 34px 0 10px; break-after: avoid; }
h3 { font-size: 16px; font-weight: 600; margin: 22px 0 8px; break-after: avoid; }
h3::before { content: "▼ "; font-size: 12px; color: #37352F; }
p { margin: 6px 0; }
ul { margin: 6px 0 6px 0; padding-left: 26px; }
li { margin: 3px 0; }
code { font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace; font-size: 85%;
       background: rgba(135,131,120,0.15); color: #EB5757; padding: 1px 4px; border-radius: 3px; }
pre { background: #F7F6F3; border-radius: 4px; padding: 18px 22px; margin: 8px 0 12px;
      font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace; font-size: 11.5px; line-height: 1.6;
      white-space: pre-wrap; word-break: break-word; break-inside: avoid; color: #37352F; }
figure { margin: 8px 0 18px; break-inside: avoid; }
figure img { width: 100%; border: 1px solid #E9E9E7; border-radius: 4px; display: block; }
figcaption { font-size: 12px; color: #787774; margin-top: 4px; }
.meta { color: #787774; }
.item { break-inside: avoid; page-break-inside: avoid; padding-top: 2px; }
.item figure img { max-height: 205mm; object-fit: contain; }
"""


def build_html() -> str:
    parts = [f"<h1>{html.escape(TITLE)}</h1>"]
    in_item = False  # cada item ▼ (título + código + print) vira um bloco que não se divide entre páginas
    for i, block in enumerate(C):
        kind = block[0]
        if kind in {"h2", "h3"} and in_item:
            parts.append("</div>")
            in_item = False
        if kind == "h2":
            parts.append(f"<h2>{inline(block[1])}</h2>")
        elif kind == "h3":
            parts.append(f"<div class='item'><h3>{inline(block[1])}</h3>")
            in_item = True
        elif kind == "p":
            cls = ' class="meta"' if i < 3 else ""
            parts.append(f"<p{cls}>{inline(block[1])}</p>")
        elif kind == "ul":
            parts.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in block[1]) + "</ul>")
        elif kind == "code":
            parts.append(f"<pre>{highlight(block[1])}</pre>")
        elif kind == "img":
            path = Path(block[1]) if Path(block[1]).is_absolute() else PRINTS / block[1]
            if not path.exists():
                raise SystemExit(f"print ausente: {path}")
            cap = f"<figcaption>{inline(block[2])}</figcaption>" if block[2] else ""
            parts.append(f'<figure><img src="{path.as_uri()}">{cap}</figure>')
    if in_item:
        parts.append("</div>")
    return ("<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><title>GraphRAG Jogos Online</title>"
            "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap'>"
            f"<style>{CSS}</style></head><body>" + "\n".join(parts) + "</body></html>")


def main() -> None:
    from playwright.sync_api import sync_playwright

    out_html = HERE / "GraphRAG_Jogos_Online_apresentacao.html"
    out_pdf = HERE / "GraphRAG_Jogos_Online_apresentacao.pdf"
    out_html.write_text(build_html(), encoding="utf-8")
    footer = ("<div style='font-family:Arial;font-size:8px;color:#9B9A97;width:100%;padding:0 20mm;"
              f"display:flex;justify-content:space-between'><span>{html.escape(TITLE)}</span>"
              "<span class='pageNumber'></span></div>")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(out_html.as_uri(), wait_until="networkidle")
        page.pdf(path=str(out_pdf), format="A4", print_background=True, display_header_footer=True,
                 header_template="<div></div>", footer_template=footer,
                 margin={"top": "22mm", "bottom": "22mm", "left": "20mm", "right": "20mm"})
        browser.close()
    print("Gerado:", out_pdf)


if __name__ == "__main__":
    main()
