// Gera a apresentação de defesa: GraphRAG / KAG — Jogos Online.
// Sem renderizador nesta máquina: todo texto passa por fit(), que estima largura/altura
// de forma conservadora e aborta o build se algo transbordar.
const pptxgen = require("pptxgenjs");
const path = require("path");
const SKILL = "/Users/rougger/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/007318ca-dbbf-4585-8a3c-9721b99d9f8d/6328a355-b703-46f2-92a2-1fba4c231f95/skills/pptx";
const { applyTheme } = require(path.join(SKILL, "scripts/apply_theme.js"));

const REPO = "/Users/rougger/dev/graphrag-kag-arxiv";
const OUT = path.join(REPO, "docs/slides/defesa-graphrag-jogos.pptx");
const IMG = (n) => path.join(REPO, "docs/img", n);

const THEME = {
  name: "GraphRAG Jogos",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "0F1114", lt1: "EEF1F5", dk2: "181C22", lt2: "9AA4B2",
    accent1: "4F9DFF", accent2: "F5B841", accent3: "343D4A", accent4: "222832",
    accent5: "3DD68C", accent6: "B48CFF", hlink: "4F9DFF", folHlink: "B48CFF",
  },
};
const HEX = THEME.colors;

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625 in
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "GraphRAG / KAG — Jogos Online";
pres.subject = "Defesa do projeto final — Tendências em Ciência da Computação";
pres.author = "Biel Aguiar e Thiago Rocha";
const C = pres.SchemeColor;
// Papéis (tema escuro): dk1 = fundo, lt1 = texto, dk2 = cartão, lt2 = texto secundário.
const BG = C.text1, TXT = C.background1, CARD = C.text2, MUTED = C.background2;
const BLUE = C.accent1, GOLD = C.accent2, EDGE = C.accent3, CARD2 = C.accent4, VIOLET = C.accent6;

// ---------- estimativa de texto ----------
function charW(ch) {
  if (ch === " ") return 0.24;
  if ("ilj.,;:|!'·".includes(ch)) return 0.27;
  if ("frt()[]-/\"“”".includes(ch)) return 0.36;
  if ("mwMW—→".includes(ch)) return 0.88;
  if (/[A-Z0-9]/.test(ch) || "≠≥~%#&_".includes(ch)) return 0.62;
  return 0.52;
}
function textW(s, size, { bold = false, head = false } = {}) {
  let w = 0;
  for (const ch of s) w += charW(ch);
  return (w * size * (head ? 1.12 : 1) * (bold ? 1.06 : 1) * 1.05) / 72; // 5% de folga
}
function wrapLines(s, size, width, o) {
  let lines = 0;
  for (const para of s.split("\n")) {
    const words = para.split(" ");
    let cur = "";
    lines++;
    for (const wd of words) {
      if (textW(wd, size, o) > width) throw new Error(`palavra não cabe: "${wd}" (${size}pt em ${width.toFixed(2)}in)`);
      const cand = cur ? cur + " " + wd : wd;
      if (textW(cand, size, o) > width) { lines++; cur = wd; } else cur = cand;
    }
  }
  return lines;
}
const PROBLEMS = [];
// paras: [{ t: string | [{t, c, b, i}], s, b, i, c, head, after, bullet }]
function fit(name, paras, w, h, marginPt) {
  const m = (marginPt || 0) / 72;
  let total = 0;
  paras.forEach((p, k) => {
    const txt = Array.isArray(p.t) ? p.t.map((r) => r.t).join("") : p.t;
    const bold = p.b || (Array.isArray(p.t) && p.t.some((r) => r.b));
    const width = w - 2 * m - (p.bullet ? 0.22 : 0);
    let n;
    try { n = wrapLines(txt, p.s, width, { bold, head: p.head }); }
    catch (e) { PROBLEMS.push(`${name}: ${e.message}`); n = 1; }
    if (p.maxLines && n > p.maxLines) PROBLEMS.push(`${name}: "${txt.slice(0, 40)}" ocupa ${n} linhas (máx ${p.maxLines})`);
    total += (n * p.s * 1.22) / 72 + (k < paras.length - 1 ? (p.after || 0) / 72 : 0);
  });
  if (total > h - 2 * m + 0.005) PROBLEMS.push(`${name}: altura ${total.toFixed(2)}in > caixa ${(h - 2 * m).toFixed(2)}in`);
  return total;
}

// ---------- helpers de composição ----------
let objN = 0;
const nm = (s) => `${s}-${++objN}`;
function box(slide, name, paras, o) {
  const margin = o.margin ?? 0;
  fit(name, paras, o.w, o.h, margin);
  const runs = [];
  paras.forEach((p, k) => {
    const pr = Array.isArray(p.t) ? p.t : [{ t: p.t }];
    pr.forEach((r, j) => {
      const opt = {
        fontSize: p.s, bold: r.b ?? p.b ?? false, italic: r.i ?? p.i ?? false,
        color: r.c ?? p.c ?? TXT, paraSpaceAfter: p.after || 0, align: p.align || o.align || "left",
      };
      if (p.head) opt.fontFace = "+mj-lt";
      if (p.bullet) opt.bullet = { indent: 16 };
      if (j === pr.length - 1 && k < paras.length - 1) opt.breakLine = true;
      runs.push({ text: r.t, options: opt });
    });
  });
  slide.addText(runs, {
    x: o.x, y: o.y, w: o.w, h: o.h, margin, valign: o.valign || "top", isTextBox: true,
    objectName: nm(name), fit: "none",
    ...(o.fill ? { fill: { color: o.fill } } : {}),
  });
}
function card(slide, name, x, y, w, h, color = CARD) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: 0.08, fill: { color }, line: { color: EDGE, width: 0.75 }, objectName: nm(name),
  });
}
// Motivo: nó de grafo (círculo), opcionalmente com rótulo central.
function node(slide, name, cx, cy, d, color, label, labelSize = 14, labelColor = BG) {
  const o = { x: cx - d / 2, y: cy - d / 2, w: d, h: d, fill: { color }, line: { color: BG, width: 1.5 }, objectName: nm(name) };
  if (label) {
    fit(name + " rótulo", [{ t: label, s: labelSize, b: true, head: true }], d, d, 0);
    slide.addText(label, { ...o, shape: pres.shapes.OVAL, fontSize: labelSize, bold: true, color: labelColor, fontFace: "+mj-lt", align: "center", valign: "middle", margin: 0 });
  } else slide.addShape(pres.shapes.OVAL, o);
}
function edge(slide, name, x1, y1, x2, y2, { color = EDGE, width = 1.25, arrow = false, dash } = {}) {
  slide.addShape(pres.shapes.LINE, {
    x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1),
    flipV: (x2 - x1) * (y2 - y1) < 0, flipH: x2 < x1 && y2 === y1,
    line: { color, width, ...(arrow ? { endArrowType: "triangle" } : {}), ...(dash ? { dashType: dash } : {}) },
    objectName: nm(name),
  });
}
function titleFit(t) { fit(`título "${t}"`, [{ t, s: 28, b: true, head: true, maxLines: 1 }], 8.2, 0.7, 0); }

// ---------- layouts ----------
const FOOT = "GraphRAG / KAG — Jogos Online  ·  Tendências em Ciência da Computação";
pres.defineSlideMaster({
  title: "Capa",
  background: { color: HEX.dk1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.5, y: 1.05, w: 5.9, h: 1.45, fontSize: 40, bold: true, color: TXT, valign: "bottom", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "subtitle", type: "body", x: 0.5, y: 2.65, w: 5.6, h: 0.75, fontSize: 17, color: MUTED, valign: "top", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "meta", type: "body", x: 0.5, y: 3.6, w: 5.6, h: 1.4, fontSize: 14, color: TXT, valign: "top", margin: 0 }, text: "" } },
  ],
});
const cluster = [ // motivo fixo do layout de conteúdo: três nós ligados no canto superior direito
  { line: { x: 9.07, y: 0.475, w: 0.305, h: 0.215, line: { color: HEX.accent3, width: 1 }, flipV: true } },
  { line: { x: 9.07, y: 0.69, w: 0.36, h: 0.14, line: { color: HEX.accent3, width: 1 } } },
  { line: { x: 9.375, y: 0.475, w: 0.055, h: 0.355, line: { color: HEX.accent3, width: 1 } } },
  { text: { text: "", options: { shape: pres.shapes.OVAL, x: 9.0, y: 0.62, w: 0.14, h: 0.14, fill: { color: BLUE } } } },
  { text: { text: "", options: { shape: pres.shapes.OVAL, x: 9.32, y: 0.42, w: 0.11, h: 0.11, fill: { color: MUTED } } } },
  { text: { text: "", options: { shape: pres.shapes.OVAL, x: 9.38, y: 0.78, w: 0.1, h: 0.1, fill: { color: GOLD } } } },
];
pres.defineSlideMaster({
  title: "Conteudo",
  background: { color: HEX.dk1 },
  margin: [0.5, 0.5, 0.5, 0.5],
  objects: [
    ...cluster,
    { placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.3, w: 8.3, h: 0.7, fontSize: 28, bold: true, color: TXT, valign: "middle", margin: 0 }, text: "" } },
    { text: { text: FOOT, options: { x: 0.5, y: 5.2, w: 6.5, h: 0.28, fontSize: 10, color: MUTED, margin: 0, valign: "middle" } } },
  ],
  slideNumber: { x: 8.9, y: 5.2, w: 0.6, h: 0.28, fontSize: 10, color: HEX.lt2, align: "right", margin: 0 },
});

function content(section, title) {
  titleFit(title);
  const s = pres.addSlide({ masterName: "Conteudo", sectionTitle: section });
  s.addText(title, { placeholder: "title" });
  return s;
}

// ================= 1. Capa =================
pres.addSection({ title: "Abertura" });
{
  const s = pres.addSlide({ masterName: "Capa", sectionTitle: "Abertura" });
  fit("capa título", [{ t: "GraphRAG / KAG", s: 40, b: true, head: true, maxLines: 1 }, { t: "Jogos Online", s: 40, b: true, head: true, maxLines: 1 }], 5.9, 1.45, 0);
  s.addText([{ text: "GraphRAG / KAG", options: { breakLine: true } }, { text: "Jogos Online", options: { color: BLUE } }], { placeholder: "title", align: "left" });
  const sub = "Recuperação híbrida em grafo de conhecimento com mitigação de alucinações";
  fit("capa subtítulo", [{ t: sub, s: 17 }], 5.6, 0.75, 0);
  s.addText(sub, { placeholder: "subtitle" });
  const meta = [
    { t: "Tendências em Ciência da Computação", s: 14, b: true, after: 6 },
    { t: "Biel Aguiar · Thiago Rocha", s: 14, after: 6 },
    { t: "Unipê Cruzeiro do Sul  ·  18/11/2026", s: 14, c: MUTED },
  ];
  fit("capa meta", meta, 5.6, 1.4, 0);
  s.addText(meta.map((p, k) => ({ text: p.t, options: { bold: !!p.b, color: p.c || TXT, paraSpaceAfter: p.after || 0, breakLine: k < meta.length - 1 } })), { placeholder: "meta" });

  // rede decorativa (motivo) à direita
  const N = [[7.3, 1.0, 0.32, BLUE], [8.7, 1.35, 0.5, BLUE], [7.75, 2.2, 0.62, GOLD], [9.15, 2.65, 0.28, MUTED],
    [6.95, 3.25, 0.3, MUTED], [8.45, 3.45, 0.42, BLUE], [7.6, 4.3, 0.24, BLUE], [9.0, 4.35, 0.3, VIOLET]];
  const E = [[0, 2], [1, 2], [0, 1], [2, 4], [2, 5], [1, 3], [3, 5], [4, 6], [5, 6], [5, 7], [2, 3]];
  E.forEach(([a, b]) => edge(s, "rede aresta", N[a][0], N[a][1], N[b][0], N[b][1], { color: EDGE, width: 1.5 }));
  N.forEach(([x, y, d, c]) => node(s, "rede nó", x, y, d, c));
}

// ================= 2. Problema =================
pres.addSection({ title: "Problema e proposta" });
{
  const s = content("Problema e proposta", "Os limites do RAG vetorial");
  const cards = [
    { x: 0.5, n: "1", h: "Perguntas de vários saltos", b: "Cada fato está em um artigo diferente; os trechos intermediários quase nunca são os mais parecidos com a pergunta.", c: BLUE },
    { x: 5.15, n: "2", h: "Não sabe recusar", b: "A busca vetorial sempre devolve os k vizinhos mais próximos, mesmo quando nenhum deles tem relação com a pergunta.", c: GOLD },
  ];
  cards.forEach((k) => {
    card(s, "card problema", k.x, 1.25, 4.35, 2.45);
    node(s, "nó número", k.x + 0.5, 1.7, 0.5, k.c, k.n, 18);
    box(s, "problema título", [{ t: k.h, s: 18, b: true, maxLines: 1 }], { x: k.x + 0.9, y: 1.5, w: 3.3, h: 0.4, valign: "middle" });
    box(s, "problema texto", [{ t: k.b, s: 16 }], { x: k.x + 0.3, y: 2.2, w: 3.8, h: 1.35 });
  });
  card(s, "faixa exemplo", 0.5, 3.95, 9.0, 0.95, CARD2);
  node(s, "nó exemplo", 0.95, 4.425, 0.36, GOLD);
  box(s, "exemplo", [
    { t: "Exemplo", s: 12, b: true, c: GOLD, after: 2 },
    { t: [{ t: "“Que jogo da Valve surgiu de um mod de Warcraft III?”", i: true }, { t: "  a resposta cruza três artigos", c: MUTED }], s: 16 },
  ], { x: 1.35, y: 4.0, w: 8.0, h: 0.85, valign: "middle" });
}

// ================= 3. Ideia =================
{
  const s = content("Problema e proposta", "Estruturar antes de consultar");
  const rows = [
    { y: 1.3, label: "RAG vetorial", lc: MUTED, chips: ["texto", "trechos", "vetores", "top-k por similaridade"], fill: CARD, tc: MUTED },
    { y: 2.2, label: "GraphRAG / KAG", lc: BLUE, chips: ["texto", "entidades + relações", "grafo no Neo4j", "caminhos + evidência"], fill: CARD2, tc: TXT },
  ];
  const cx0 = 2.45, cw = 1.55, gap = 0.3, ch = 0.62;
  rows.forEach((r) => {
    box(s, "linha rótulo", [{ t: r.label, s: 16, b: true, c: r.lc, maxLines: 1 }], { x: 0.5, y: r.y, w: 1.85, h: ch, valign: "middle" });
    r.chips.forEach((t, i) => {
      const x = cx0 + i * (cw + gap);
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: r.y, w: cw, h: ch, rectRadius: 0.1, fill: { color: r.fill }, line: { color: r.lc === BLUE ? BLUE : EDGE, width: 1 }, objectName: nm("chip") });
      box(s, "chip texto", [{ t, s: 13, c: r.tc, align: "center" }], { x, y: r.y, w: cw, h: ch, margin: 4, valign: "middle", align: "center" });
      if (i < 3) edge(s, "seta", x + cw + 0.04, r.y + ch / 2, x + cw + gap - 0.04, r.y + ch / 2, { color: r.lc === BLUE ? BLUE : EDGE, arrow: true });
    });
  });
  const ben = [
    { x: 0.5, c: BLUE, h: "Caminhos entre documentos", b: "Entidades e relações explícitas ligam fatos que estão em artigos diferentes." },
    { x: 5.15, c: GOLD, h: "Saber quando recusar", b: "A correspondência exata com nós do grafo dá um sinal objetivo de que a pergunta toca a base." },
  ];
  ben.forEach((k) => {
    card(s, "card benefício", k.x, 3.2, 4.35, 1.7);
    node(s, "nó benefício", k.x + 0.45, 3.62, 0.4, k.c);
    box(s, "benefício título", [{ t: k.h, s: 17, b: true, maxLines: 1 }], { x: k.x + 0.85, y: 3.42, w: 3.35, h: 0.4, valign: "middle" });
    box(s, "benefício texto", [{ t: k.b, s: 15 }], { x: k.x + 0.3, y: 3.95, w: 3.85, h: 0.85 });
  });
}

// ================= 4. Arquitetura =================
pres.addSection({ title: "Arquitetura" });
{
  const s = content("Arquitetura", "Arquitetura em quatro etapas");
  const steps = [
    { h: "Text-to-Graph", items: ["Wikipedia, 65 artigos", "Entidades e relações tipadas", "Evidência literal e resolução"] },
    { h: "Neo4j LPG", items: ["Restrições de unicidade", "Índices range, fulltext e vetor", "PageRank e Louvain (GDS)"] },
    { h: "Recuperação híbrida", items: ["Vetor + fulltext + dicionário", "Multi-hop e caminhos mínimos", "Geração citada e verificada"] },
    { h: "Interface", items: ["Streamlit + pyvis", "Subgrafo, Cypher e nós", "Nível de confiança"] },
  ];
  const gap = 0.34, bw = (9 - 3 * gap) / 4, by = 1.85, bh = 2.72;
  steps.forEach((st, i) => {
    const x = 0.5 + i * (bw + gap);
    node(s, "nó etapa", x + bw / 2, 1.42, 0.46, i === 2 ? GOLD : BLUE, String(i + 1), 16);
    card(s, "card etapa", x, by, bw, bh);
    box(s, "etapa título", [{ t: st.h, s: 16, b: true, c: i === 2 ? GOLD : BLUE }], { x: x + 0.12, y: by + 0.12, w: bw - 0.24, h: 0.58, valign: "top" });
    box(s, "etapa itens", st.items.map((t, k) => ({ t, s: 14, after: k < 2 ? 6 : 0 })), { x: x + 0.12, y: by + 0.72, w: bw - 0.24, h: bh - 0.8 });
    if (i < 3) edge(s, "seta etapa", x + bw + 0.04, by + bh / 2, x + bw + gap - 0.04, by + bh / 2, { color: BLUE, arrow: true, width: 1.5 });
  });
  box(s, "rodapé técnico", [{ t: "Python 3.12  ·  Neo4j com GDS  ·  Streamlit + pyvis  ·  API FastAPI", s: 12, c: MUTED }], { x: 0.5, y: 4.66, w: 9.0, h: 0.28, valign: "middle" });
}

// ================= 5. Corpus + Text-to-Graph =================
{
  const s = content("Arquitetura", "Corpus e Text-to-Graph");
  const stats = [["65", "artigos da Wikipedia (inglês)", BLUE], ["282", "trechos de três frases", BLUE], ["811", "entidades extraídas", GOLD], ["797", "relações extraídas", GOLD]];
  stats.forEach(([v, l, c], i) => {
    const x = 0.5 + (i % 2) * 2.1, y = 1.25 + Math.floor(i / 2) * 1.25;
    card(s, "card número", x, y, 1.95, 1.1);
    box(s, "número", [{ t: v, s: 30, b: true, head: true, c, maxLines: 1 }, { t: l, s: 12, c: MUTED }], { x: x + 0.15, y: y + 0.1, w: 1.7, h: 0.92 });
  });
  card(s, "card evidência", 0.5, 3.8, 4.05, 1.1, CARD2);
  box(s, "evidência", [
    { t: "Evidência literal", s: 14, b: true, c: GOLD, after: 3 },
    { t: "A frase da relação precisa aparecer no artigo. Nenhuma relação rejeitada; 1 descartada na carga (origem = destino).", s: 13 },
  ], { x: 0.65, y: 3.88, w: 3.75, h: 0.96 });

  // chips de esquema
  const right = { x: 4.95, w: 4.55 };
  function chips(list, y0, size, color, fill) {
    let x = right.x, y = y0;
    const h = 0.34, g = 0.1;
    list.forEach((t) => {
      const w = textW(t, size, { bold: true }) + 0.18;
      if (x + w > right.x + right.w + 0.001) { x = right.x; y += h + g; }
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.06, fill: { color: fill }, line: { color, width: 0.75 }, objectName: nm("chip esquema") });
      s.addText(t, { x, y, w, h, fontSize: size, bold: true, color, align: "center", valign: "middle", margin: 0, isTextBox: true, objectName: nm("chip esquema texto") });
      x += w + g;
    });
    return y + h;
  }
  box(s, "tipos título", [{ t: "9 tipos de entidade", s: 16, b: true, maxLines: 1 }], { x: right.x, y: 1.25, w: right.w, h: 0.35, valign: "middle" });
  const e1 = chips(["Game", "Company", "Person", "Genre", "Platform", "Engine", "Franchise", "Event", "Concept"], 1.7, 12, BLUE, CARD);
  box(s, "relações título", [{ t: "13 tipos de relação (exemplos)", s: 16, b: true, maxLines: 1 }], { x: right.x, y: e1 + 0.2, w: right.w, h: 0.35, valign: "middle" });
  const e2 = chips(["DEVELOPED_BY", "PUBLISHED_BY", "BASED_ON", "SEQUEL_OF", "CREATED_BY", "SUBSIDIARY_OF", "FEATURED_IN", "ORGANIZED_BY"], e1 + 0.65, 10, GOLD, CARD);
  if (e2 > 4.45) PROBLEMS.push(`slide 5: chips terminam em ${e2.toFixed(2)}in`);
  box(s, "extração nota", [{ t: "Extração por LLM (Claude) com JSON Schema derivado de modelos Pydantic", s: 12, c: MUTED }], { x: right.x, y: 4.47, w: right.w, h: 0.45, valign: "bottom" });
}

// ================= 6. Resolução de entidades =================
{
  const s = content("Arquitetura", "Resolução de entidades");
  box(s, "hero números", [{ t: [{ t: "811", c: MUTED }, { t: "  →  ", c: MUTED }, { t: "351", c: BLUE }], s: 40, b: true, head: true, maxLines: 1 }], { x: 0.5, y: 1.15, w: 4.4, h: 0.72, valign: "middle" });
  box(s, "hero rótulo", [{ t: "menções \u2192 entidades canônicas · 93 em mais de um artigo (pontes)", s: 14, c: MUTED }], { x: 0.5, y: 1.9, w: 4.4, h: 0.5 });
  const steps = [
    ["Chave lexical", "minúsculas, sem pontuação, sempre dentro do mesmo tipo"],
    ["Aliases compatíveis", "sigla, trigramas, sufixo corporativo, título-base"],
    ["Semântica", "cosseno ≥ 0,93 e trigramas ≥ 0,85"],
  ];
  steps.forEach(([h, d], i) => {
    const y = 2.6 + i * 0.78;
    node(s, "nó passo", 0.72, y + 0.25, 0.42, BLUE, String(i + 1), 15);
    box(s, "passo", [{ t: h, s: 15, b: true, after: 1 }, { t: d, s: 13, c: MUTED }], { x: 1.1, y, w: 3.8, h: 0.72 });
  });
  const groups = [
    { y: 1.25, h: 1.5, title: "Fundem", c: BLUE, items: ["Valve ~ Valve Corporation", "Warcraft III ~ Warcraft III: Reign of Chaos", "MOBA ~ Multiplayer online battle arena"] },
    { y: 2.9, h: 1.5, title: "Não fundem", c: GOLD, items: ["Overwatch ≠ Overwatch 2", "PlayStation 4 ≠ PlayStation 5", "Dota 2 ≠ Dota Underlords", "Valve ≠ Valorant"] },
  ];
  groups.forEach((g) => {
    card(s, "card exemplos", 5.2, g.y, 4.3, g.h);
    node(s, "nó grupo", 5.45, g.y + 0.27, 0.2, g.c);
    box(s, "grupo título", [{ t: g.title, s: 15, b: true, c: g.c }], { x: 5.65, y: g.y + 0.1, w: 3.7, h: 0.34, valign: "middle" });
    box(s, "grupo itens", g.items.map((t, k) => ({ t, s: 13, after: k < g.items.length - 1 ? 2 : 0 })), { x: 5.4, y: g.y + 0.45, w: 3.95, h: g.h - 0.52 });
  });
  box(s, "travas", [{ t: [{ t: "Travas: ", b: true, c: GOLD }, { t: "tipo · números · sufixos corporativos · subtítulo" }], s: 13, maxLines: 2 }], { x: 5.2, y: 4.47, w: 4.3, h: 0.46, valign: "middle" });
}

// ================= 7. LPG no Neo4j =================
{
  const s = content("Arquitetura", "Grafo LPG no Neo4j");
  const P = { chunk: [1.2, 1.85], art: [1.2, 4.0], e1: [3.9, 4.0], e2: [3.9, 1.85] }, d = 0.95, r = d / 2;
  edge(s, "PART_OF", P.chunk[0], P.chunk[1] + r, P.art[0], P.art[1] - r, { color: MUTED, arrow: true, width: 1.5 });
  edge(s, "DESCRIBES", P.art[0] + r, P.art[1], P.e1[0] - r, P.e1[1], { color: MUTED, arrow: true, width: 1.5 });
  edge(s, "relação", P.e1[0], P.e1[1] - r, P.e2[0], P.e2[1] + r, { color: GOLD, arrow: true, width: 2 });
  node(s, "Chunk", ...P.chunk, d, MUTED, "Chunk", 13);
  node(s, "Article", ...P.art, d, MUTED, "Article", 13);
  node(s, "Entity", ...P.e1, d, BLUE, "Entity", 13);
  node(s, "Entity", ...P.e2, d, BLUE, "Entity", 13);
  box(s, "rótulo PART_OF", [{ t: "PART_OF", s: 12, b: true, c: MUTED }], { x: 1.3, y: 2.78, w: 1.0, h: 0.3, valign: "middle" });
  box(s, "rótulo DESCRIBES", [{ t: "DESCRIBES", s: 12, b: true, c: MUTED, align: "center" }], { x: 1.75, y: 3.62, w: 1.6, h: 0.3, valign: "middle", align: "center" });
  box(s, "rótulo relação", [
    { t: "13 tipos de relação", s: 12, b: true, c: GOLD, align: "right" },
    { t: "evidence · doc_id", s: 12, c: TXT, align: "right" },
  ], { x: 2.05, y: 2.6, w: 1.7, h: 0.5, align: "right" });

  const idx = [
    ["Unicidade", "Article.doc_id, Entity.id, Chunk.id"],
    ["Range (B-tree)", "nome, tipo e PageRank; título do artigo"],
    ["Fulltext (Lucene)", "nome, aliases e descrição; título e texto"],
    ["Vetor: 3 índices, 384 dim", "cosseno · multilingual-e5-small, local"],
  ];
  idx.forEach(([h, dsc], i) => {
    const y = 1.2 + i * 0.6;
    box(s, "índice", [{ t: h, s: 14, b: true, c: BLUE, maxLines: 1 }, { t: dsc, s: 13, c: TXT, maxLines: 1 }], { x: 5.0, y, w: 4.5, h: 0.56 });
  });
  card(s, "card GDS", 5.0, 3.72, 4.5, 1.18, CARD2);
  const gds = [["PageRank", "ordena vizinhança e caminhos", 16], ["24", "comunidades Louvain", 26], ["0,53", "modularidade", 26]];
  gds.forEach(([v, l, sz], i) => {
    const x = 5.12 + i * 1.45;
    box(s, "GDS", [{ t: v, s: sz, b: true, head: true, c: GOLD, maxLines: 1 }, { t: l, s: 12, c: MUTED }], { x, y: 3.82, w: 1.35, h: 1.0 });
  });
}

// ================= 8. Recuperação híbrida =================
{
  const s = content("Arquitetura", "Recuperação híbrida");
  const steps = [
    ["Ligação de entidades", "vetor + fulltext + dicionário, fundidos por RRF"],
    ["Âncoras", "entidades citadas ou confirmadas por dois canais"],
    ["Travessia multi-hop", "caminhos [*1..h], h = 2 por padrão (até 3)"],
    ["Caminhos mínimos", "allShortestPaths entre âncoras, menor soma de PageRank"],
    ["Consulta por intenção", "“quem criou”, “subsidiária” → tipos de relação"],
    ["Reordenação", "30 melhores triplas + 4 trechos mais próximos"],
  ];
  steps.forEach(([h, d], i) => {
    const y = 1.2 + i * 0.6;
    node(s, "nó passo", 0.7, y + 0.24, 0.38, i === 3 ? GOLD : BLUE, String(i + 1), 14);
    box(s, "passo", [{ t: h, s: 14, b: true, maxLines: 1 }, { t: d, s: 12, c: MUTED, maxLines: 1 }], { x: 1.05, y, w: 4.65, h: 0.56 });
  });
  card(s, "card exemplo", 5.95, 1.2, 3.55, 3.7);
  box(s, "exemplo cabeçalho", [{ t: "EXEMPLO MULTI-HOP", s: 12, b: true, c: GOLD }], { x: 6.15, y: 1.32, w: 3.2, h: 0.28, valign: "middle" });
  box(s, "exemplo pergunta", [{ t: "“Que jogo da Valve surgiu de um mod de Warcraft III?”", s: 14, i: true }], { x: 6.15, y: 1.62, w: 3.2, h: 0.62 });
  const nx = 6.45, ys = [2.62, 3.47, 4.32], d = 0.44;
  edge(s, "aresta", nx, ys[0] + d / 2, nx, ys[1] - d / 2, { color: GOLD, arrow: true, width: 2 });
  edge(s, "aresta", nx, ys[1] + d / 2, nx, ys[2] - d / 2, { color: GOLD, arrow: true, width: 2 });
  [["Dota 2", BLUE], ["Defense of the Ancients", BLUE], ["Warcraft III", BLUE]].forEach(([t, c], i) => {
    node(s, "nó caminho", nx, ys[i], d, c);
    box(s, "nó caminho rótulo", [{ t, s: 14, b: true, maxLines: 1 }], { x: 6.8, y: ys[i] - 0.17, w: 2.6, h: 0.34, valign: "middle" });
  });
  ["SEQUEL_OF", "BASED_ON"].forEach((t, i) => {
    box(s, "rótulo aresta", [{ t, s: 11, b: true, c: GOLD, maxLines: 1 }], { x: 6.8, y: (ys[i] + ys[i + 1]) / 2 - 0.14, w: 2.0, h: 0.28, valign: "middle" });
  });
}

// ================= 9. Mitigação de alucinações =================
{
  const s = content("Arquitetura", "Mitigação de alucinações");
  const layers = [
    ["Ingestão", "Relação só entra no grafo se a frase de evidência aparece literalmente no artigo."],
    ["Recuperação e recusa", "Sem entidade citada e com similaridade abaixo de 0,924, o sistema recusa antes de gerar."],
    ["Geração citada + verificador", "Toda afirmação cita [T1] ou [C1]; o verificador remove citações inexistentes."],
    ["Cypher somente leitura", "Filtro bloqueia CREATE, MERGE, DELETE e SET; roda em transação de leitura."],
  ];
  layers.forEach(([h, b], i) => {
    const x = 0.5 + (i % 2) * 4.65, y = 1.2 + Math.floor(i / 2) * 1.4;
    card(s, "card camada", x, y, 4.35, 1.3);
    node(s, "nó camada", x + 0.4, y + 0.38, 0.42, BLUE, String(i + 1), 15);
    box(s, "camada título", [{ t: h, s: 15, b: true, maxLines: 1 }], { x: x + 0.8, y: y + 0.13, w: 3.4, h: 0.36, valign: "middle" });
    box(s, "camada texto", [{ t: b, s: 14, c: TXT }], { x: x + 0.8, y: y + 0.5, w: 3.4, h: 0.74 });
  });
  box(s, "confiança rótulo", [{ t: "Confiança", s: 15, b: true, c: GOLD, maxLines: 1 }], { x: 0.5, y: 4.12, w: 1.3, h: 0.42, valign: "middle" });
  const segs = [["Ligação 0,4", "força da ligação com o grafo", 0.4, BLUE], ["Estrutura 0,3", "caminho ou triplas suficientes", 0.3, VIOLET], ["Fundamentação 0,3", "frases com citação válida", 0.3, GOLD]];
  let sx = 1.9;
  segs.forEach(([t, cap, f, c]) => {
    const w = 7.6 * f;
    s.addShape(pres.shapes.RECTANGLE, { x: sx, y: 4.12, w: w - 0.04, h: 0.42, fill: { color: c }, line: { color: c, width: 0 }, objectName: nm("segmento confiança") });
    box(s, "segmento texto", [{ t, s: 13, b: true, c: BG, maxLines: 1 }], { x: sx, y: 4.12, w: w - 0.04, h: 0.42, margin: 6, valign: "middle" });
    box(s, "segmento legenda", [{ t: cap, s: 11, c: MUTED, maxLines: 1 }], { x: sx, y: 4.58, w: w - 0.04, h: 0.26, margin: 0 });
    sx += w;
  });
}

// ================= 10. Demo multi-hop =================
pres.addSection({ title: "Demonstração" });
function shot(s, file, x, alt) {
  const w = 5.9, h = (w * 1900) / 3000; // 3000:1900 preservado
  s.addShape(pres.shapes.RECTANGLE, { x: x - 0.03, y: 1.17, w: w + 0.06, h: h + 0.06, fill: { color: EDGE }, line: { color: EDGE, width: 0 }, objectName: nm("moldura") });
  s.addImage({ path: IMG(file), x, y: 1.2, w, h, altText: alt, objectName: nm("captura") });
  return h;
}
function callouts(s, x, w, items) {
  items.forEach(([h, b, c], i) => {
    const y = 1.2 + i * 0.95;
    node(s, "nó destaque", x + 0.12, y + 0.15, 0.22, c || BLUE);
    box(s, "destaque", [{ t: h, s: 14, b: true, after: 1 }, { t: b, s: 12, c: MUTED }], { x: x + 0.35, y, w: w - 0.35, h: 0.88 });
  });
}
{
  const s = content("Demonstração", "Demonstração: pergunta multi-hop");
  const h = shot(s, "ui-multihop.png", 0.5, "Interface respondendo uma pergunta de vários saltos: resposta citada à esquerda e subgrafo usado à direita.");
  if (1.2 + h > 4.95) PROBLEMS.push("slide 10: imagem passa de 4,95in");
  callouts(s, 6.7, 2.8, [
    ["Pergunta", "“Que jogo da Valve surgiu de um mod de Warcraft III?”", GOLD],
    ["Resposta citada", "cada frase aponta a tripla de origem [T1], [T2]…"],
    ["Subgrafo usado", "23 nós e 30 arestas, cores por tipo, caminhos mínimos destacados"],
    ["Modo extrativo", "sem chave de API, a resposta sai direto das triplas"],
  ]);
}

// ================= 11. Proveniência =================
{
  const s = content("Demonstração", "Proveniência de cada resposta");
  shot(s, "ui-cypher.png", 3.6, "Aba de proveniência com as consultas Cypher executadas e as entidades ligadas a cada canal.");
  callouts(s, 0.5, 2.8, [
    ["Confiança", "valor final e os três componentes", GOLD],
    ["Entidades ligadas", "e por qual canal: vetorial, fulltext, dicionário"],
    ["Consultas Cypher", "todas as executadas, com parâmetros"],
    ["Triplas, nós e trechos", "com evidência, link e tempos de cada etapa"],
  ]);
}

// ================= 12. Avaliação =================
pres.addSection({ title: "Avaliação" });
{
  const s = content("Avaliação", "GraphRAG vs RAG vetorial");
  s.addChart(pres.charts.BAR, [
    { name: "GraphRAG", labels: ["Suporte completo", "Recall 1 salto", "Recall 2+ saltos", "Abstenção fora do domínio"], values: [100, 100, 100, 100] },
    { name: "RAG vetorial", labels: ["Suporte completo", "Recall 1 salto", "Recall 2+ saltos", "Abstenção fora do domínio"], values: [71.4, 91.7, 76.9, 0] },
  ], {
    x: 0.5, y: 1.15, w: 5.4, h: 3.5, objectName: "gráfico avaliação",
    barDir: "bar", barGrouping: "clustered", barGapWidthPct: 55,
    chartColors: [HEX.accent1, "5C6675"],
    showTitle: true, title: "Contexto recuperado (%)", titleColor: HEX.lt1, titleFontSize: 13, titleFontFace: "+mn-lt",
    showLegend: true, legendPos: "b", legendColor: HEX.lt2, legendFontSize: 12, legendFontFace: "+mn-lt",
    catAxisOrientation: "maxMin", catAxisLabelColor: HEX.lt1, catAxisLabelFontSize: 12, catAxisLabelFontFace: "+mn-lt", catAxisLineShow: false,
    valAxisHidden: true, valAxisLabelColor: HEX.lt2, valAxisLabelFontFace: "+mn-lt", valAxisMinVal: 0, valAxisMaxVal: 118, valGridLine: { style: "none" }, catGridLine: { style: "none" },
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: 'General"%"', dataLabelColor: HEX.lt1, dataLabelFontSize: 11, dataLabelFontFace: "+mn-lt",
    plotArea: { fill: { color: HEX.dk1 } }, chartArea: { fill: { color: HEX.dk1 } },
  });
  box(s, "protocolo", [{ t: "26 perguntas em português: 12 de um salto, 9 de 2+ saltos, 5 fora do domínio. Medida no contexto, não na resposta.", s: 11, c: MUTED }], { x: 0.5, y: 4.68, w: 5.4, h: 0.4 });
  const kpis = [
    ["100%", "71,4%", "suporte completo (21 perguntas)"],
    ["1,000", "0,769", "recall no contexto, 2+ saltos (9)"],
    ["100%", "0%", "abstenção correta fora do domínio (5)"],
    ["7.159", "2.352", "caracteres de contexto (média)"],
    ["320", "14 ms", "latência mediana de recuperação"],
  ];
  kpis.forEach(([a, b, l], i) => {
    const y = 1.15 + i * 0.77, cost = i >= 3;
    box(s, "kpi", [
      { t: [{ t: a, c: cost ? GOLD : BLUE }, { t: " vs ", c: MUTED, b: false }, { t: b, c: MUTED }], s: 21, b: true, head: true, maxLines: 1 },
      { t: l, s: 12, c: MUTED, maxLines: 1 },
    ], { x: 6.25, y, w: 3.25, h: 0.72 });
  });
}

// ================= 13. Limitações =================
{
  const s = content("Avaliação", "Limitações e ameaças à validade");
  const lim = [
    ["Conjunto pequeno e não independente", "26 perguntas escritas pela equipe a partir de fatos conhecidos do grafo."],
    ["Ajustes feitos no mesmo conjunto", "Consulta por intenção e limiar de recusa vieram de falhas vistas nele: 100% mostra que o mecanismo funciona, não o desempenho em perguntas novas."],
    ["Medida no contexto", "Ter o fato no contexto é necessário, não suficiente; avaliar a resposta gerada exige a chave de API."],
    ["Extração não revisada manualmente", "Validada de forma automática; escolhas de tipo (remake como SEQUEL_OF) mudam quais caminhos existem."],
  ];
  lim.forEach(([h, b], i) => {
    const y = 1.15 + i * 0.94;
    card(s, "card limitação", 0.5, y, 9.0, 0.84);
    node(s, "nó limitação", 0.88, y + 0.42, 0.4, GOLD, String(i + 1), 15);
    box(s, "limitação título", [{ t: h, s: 15, b: true }], { x: 1.3, y: y + 0.06, w: 2.75, h: 0.72, valign: "middle" });
    box(s, "limitação texto", [{ t: b, s: 14, c: TXT }], { x: 4.2, y: y + 0.06, w: 5.15, h: 0.72, valign: "middle" });
  });
}

// ================= 14. Conclusão =================
pres.addSection({ title: "Encerramento" });
{
  const s = content("Encerramento", "Conclusão e próximos passos");
  box(s, "conclusão título", [{ t: "O que entregamos", s: 17, b: true, c: BLUE }], { x: 0.5, y: 1.2, w: 4.4, h: 0.38, valign: "middle" });
  const concl = [
    "Sistema completo: da coleta na Wikipedia à interface com proveniência.",
    "Junta fatos de artigos diferentes que a busca vetorial não reúne.",
    "Critério objetivo para recusar perguntas fora da base.",
  ];
  concl.forEach((t, i) => {
    const y = 1.72 + i * 0.68;
    node(s, "nó conclusão", 0.62, y + 0.14, 0.2, BLUE);
    box(s, "conclusão item", [{ t, s: 15 }], { x: 0.85, y, w: 4.05, h: 0.6 });
  });
  card(s, "card futuros", 5.2, 1.2, 4.3, 2.75);
  box(s, "futuros", [
    { t: "Trabalhos futuros", s: 17, b: true, c: GOLD, after: 6 },
    { t: "Avaliar com perguntas independentes e respostas geradas", s: 14, bullet: true, after: 4 },
    { t: "Usar o texto completo dos artigos", s: 14, bullet: true, after: 4 },
    { t: "Resumir comunidades Louvain para perguntas globais", s: 14, bullet: true, after: 4 },
    { t: "Atualizar o grafo de forma incremental", s: 14, bullet: true },
  ], { x: 5.4, y: 1.32, w: 3.95, h: 2.55 });
  [[0.62, 4.5, 0.2, BLUE], [0.95, 4.32, 0.14, MUTED], [1.0, 4.68, 0.12, GOLD]].forEach(([x, y, d, c], i, a) => { if (i) edge(s, "aresta fim", a[0][0], a[0][1], x, y); });
  [[0.62, 4.5, 0.2, BLUE], [0.95, 4.32, 0.14, MUTED], [1.0, 4.68, 0.12, GOLD]].forEach(([x, y, d, c]) => node(s, "nó fim", x, y, d, c));
  box(s, "obrigado", [{ t: [{ t: "Obrigado!  ", c: TXT }, { t: "Perguntas?", c: GOLD }], s: 30, b: true, head: true, maxLines: 1 }], { x: 1.25, y: 4.18, w: 8.25, h: 0.65, valign: "middle" });
}

if (PROBLEMS.length) {
  console.error("PROBLEMAS DE LAYOUT:\n- " + PROBLEMS.join("\n- "));
  process.exit(1);
}
(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("ok:", OUT);
})();
