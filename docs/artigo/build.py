"""Gera artigo.tex (modelo SBC) e artigo.docx a partir de artigo.md, a fonte unica do texto.

Subconjunto de Markdown aceito: cabecalho com chave: "valor"; ## secao; ### subsecao;
paragrafos; listas com "- " e "1. "; **negrito**, *italico*, `codigo`, $math$; citacoes
[@chave] ou [@a; @b]; tabelas em pipe precedidas de "Tabela: legenda"; imagens
![legenda](caminho); bloco ```cypher seguido de "Listagem: legenda".

Uso (na raiz do repositorio):
  uv run --project backend --with python-docx==1.1.2 python docs/artigo/build.py
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

HERE = Path(__file__).parent
INLINE = re.compile(r"(\*\*.+?\*\*|\*[^*\s][^*]*?\*|`[^`]+`|\$[^$]+\$|\[@[^\]]+\])")


# ---------------- leitura ----------------
def parse_md(text: str) -> tuple[dict, list[tuple]]:
    meta, body = {}, text
    if text.startswith("---"):
        head, body = text[3:].split("\n---\n", 1)
        for line in head.strip().splitlines():
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"')
    blocks, lines, i = [], body.splitlines(), 0
    caption = None
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1
            continue
        if ln.startswith("### "):
            blocks.append(("h3", ln[4:]))
        elif ln.startswith("## "):
            blocks.append(("h2", ln[3:]))
        elif ln.startswith(("Tabela: ", "Listagem: ")):
            caption = ln.split(": ", 1)[1]
        elif ln.startswith("!["):
            cap, path = re.match(r"!\[(.*)\]\((.*)\)", ln).groups()
            blocks.append(("img", cap, path))
        elif ln.startswith("```"):
            j = lines.index("```", i + 1)
            code = "\n".join(lines[i + 1:j])
            i = j + 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            cap = lines[i].split(": ", 1)[1] if i < len(lines) and lines[i].startswith("Listagem: ") else ""
            blocks.append(("code", code, cap))
        elif ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip("|").split("|")]
                if not set("".join(cells)) <= set("-: "):
                    rows.append(cells)
                i += 1
            blocks.append(("table", rows, caption or ""))
            caption = None
            continue
        elif re.match(r"(- |\d+\. )", ln):
            kind = "ol" if ln[0].isdigit() else "ul"
            items = []
            while i < len(lines) and re.match(r"(- |\d+\. )", lines[i]):
                items.append(re.sub(r"^(- |\d+\. )", "", lines[i]))
                i += 1
            blocks.append((kind, items))
            continue
        else:
            para = [ln]
            while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(
                    r"(#|- |\d+\. |\||!\[|```|Tabela: |Listagem: )", lines[i + 1]):
                i += 1
                para.append(lines[i])
            blocks.append(("p", " ".join(para)))
        i += 1
    return meta, blocks


def parse_bib(text: str) -> dict[str, dict]:
    out = {}
    for m in re.finditer(r"@(\w+)\{([^,]+),(.*?)\n\}", text, re.S):
        typ, key, body = m.groups()
        f = {k.lower(): re.sub(r"[{}]", "", _unlatex(v))
             for k, v in re.findall(r"(\w+)\s*=\s*\{(.*?)\},?\s*$", body, re.M)}
        f["type"] = typ.lower()
        out[key.strip()] = f
    return out


def _unlatex(s: str) -> str:  # acentos LaTeX usados na bib -> unicode
    for a, b in (('{\\"u}', "ü"), ('{\\"a}', "ä"), ("{\\'e}", "é"), ("{\\'a}", "á")):
        s = s.replace(a, b)
    return s


def authors(f: dict) -> list[str]:
    return [a.strip() for a in f.get("author", "").split(" and ") if a.strip()]


def cite_label(f: dict) -> str:
    au = authors(f)
    last = lambda a: a.split(",")[0].strip()
    if au and au[-1] == "others" or len(au) > 2:
        who = f"{last(au[0])} et al."
    elif len(au) == 2:
        who = f"{last(au[0])} and {last(au[1])}"
    else:
        who = last(au[0]) if au else "?"
    return f"{who} {f.get('year', '')}"


def ref_text(f: dict) -> str:
    au = [a for a in authors(f) if a != "others"]
    names = []
    for a in au:
        last, _, first = a.partition(",")
        initials = " ".join(p[0] + "." for p in first.split() if p)
        names.append(f"{last.strip()}, {initials}".strip(", "))
    who = ", ".join(names[:-1]) + (" and " if len(names) > 1 else "") + names[-1]
    if authors(f) and authors(f)[-1] == "others":
        who += " et al."
    venue = f.get("booktitle") or f.get("journal") or f.get("publisher") or f.get("institution", "")
    if f["type"] == "inproceedings":
        venue = "In " + venue
    extra = ", ".join(x for x in (f.get("volume") and f"v. {f['volume']}",
                                  f.get("number") and f"n. {f['number']}",
                                  f.get("pages") and f"p. {f['pages'].replace('--', '–')}") if x)
    return f"{who} ({f.get('year')}). {f['title']}. {venue}{', ' + extra if extra else ''}."


# ---------------- LaTeX ----------------
def tex_escape(s: str) -> str:
    s = s.replace("\\", r"\textbackslash{}")
    for a, b in (("&", r"\&"), ("%", r"\%"), ("#", r"\#"), ("_", r"\_"), ("{", r"\{"),
                 ("}", r"\}"), ("~", r"\textasciitilde{}"), ("^", r"\^{}"),
                 ("→", r"$\rightarrow$")):
        s = s.replace(a, b)
    return re.sub(r'"([^"]*)"', r"``\1''", s)


def tex_inline(s: str) -> str:
    out = []
    for part in INLINE.split(s):
        if not part:
            continue
        if part.startswith("**"):
            out.append(r"\textbf{" + tex_inline(part[2:-2]) + "}")
        elif part.startswith("`"):
            out.append(r"\texttt{" + tex_escape(part[1:-1]) + "}")
        elif part.startswith("$"):
            out.append(part)
        elif part.startswith("[@"):
            out.append(r"\cite{" + ",".join(k.strip(" @") for k in part[2:-1].split(";")) + "}")
        elif part.startswith("*"):
            out.append(r"\emph{" + tex_inline(part[1:-1]) + "}")
        else:
            out.append(tex_escape(part))
    return "".join(out)


def to_tex(meta: dict, blocks: list[tuple]) -> str:
    L = [r"""\documentclass[12pt]{article}
\usepackage{sbc-template}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[brazil]{babel}
\usepackage{graphicx,url,booktabs,listings,xcolor}
\lstset{basicstyle=\ttfamily\footnotesize,frame=single,breaklines=true,columns=fullflexible,
  keywordstyle=\bfseries,morekeywords={MATCH,WHERE,WITH,RETURN,DISTINCT,LIMIT,IN,AS}}
\renewcommand{\lstlistingname}{Listagem}
\sloppy
""",
         r"\title{" + tex_escape(meta["title"]) + "}",
         r"\author{" + tex_escape(meta["authors"]).replace(", ", r", ") + "}",
         r"\address{" + tex_escape(meta["address"]).replace("--", "--")
         + ((r"\\" + "\n  \\email{" + tex_escape(meta["email"]) + "}") if meta.get("email") else "") + "}",
         r"\begin{document}", r"\maketitle"]
    env = None
    for b in blocks:
        kind = b[0]
        if kind == "h2" and b[1] in ("Abstract", "Resumo"):
            if env:
                L.append(rf"\end{{{env}}}")
            env = "abstract" if b[1] == "Abstract" else "resumo"
            L.append(rf"\begin{{{env}}}")
            continue
        if env and kind in ("h2", "h3"):
            L.append(rf"\end{{{env}}}")
            env = None
        if kind == "h2":
            L.append(r"\section{" + tex_inline(b[1]) + "}")
        elif kind == "h3":
            L.append(r"\subsection{" + tex_inline(b[1]) + "}")
        elif kind == "p":
            L.append(tex_inline(b[1]) + "\n")
        elif kind in ("ul", "ol"):
            e = "itemize" if kind == "ul" else "enumerate"
            L.append(rf"\begin{{{e}}}" + "".join(r"\item " + tex_inline(x) + "\n" for x in b[1])
                     + rf"\end{{{e}}}")
        elif kind == "img":
            path = b[2].replace("../img/", "img/")
            L.append(r"\begin{figure}[ht]\centering" + "\n" + rf"\includegraphics[width=\linewidth]{{{path}}}"
                     + "\n" + r"\caption{" + tex_inline(b[1]) + "}\n" + r"\end{figure}")
        elif kind == "code":
            L.append(r"\begin{lstlisting}[caption={" + tex_inline(b[2]) + "}]\n" + b[1] + "\n" + r"\end{lstlisting}")
        elif kind == "table":
            rows, cap = b[1], b[2]
            ncol = len(rows[0])
            spec = "p{0.62\\linewidth}" + "r" * (ncol - 1) if ncol == 2 else "l" + "r" * (ncol - 1)
            body = [" & ".join(r"\textbf{" + tex_inline(c) + "}" for c in rows[0]) + r" \\ \midrule"]
            body += [" & ".join(tex_inline(c) for c in r) + r" \\" for r in rows[1:]]
            L.append(r"\begin{table}[ht]\centering\small" + "\n" + r"\caption{" + tex_inline(cap) + "}\n"
                     + rf"\begin{{tabular}}{{{spec}}}\toprule" + "\n" + "\n".join(body)
                     + "\n" + r"\bottomrule\end{tabular}" + "\n" + r"\end{table}")
    L += [r"\IfFileExists{sbc.bst}{\bibliographystyle{sbc}}{\bibliographystyle{apalike}}", r"\bibliography{referencias}", r"\end{document}", ""]
    return "\n".join(L)


# ---------------- DOCX ----------------
def to_docx(meta: dict, blocks: list[tuple], bib: dict, out: Path) -> None:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt

    doc = Document()
    sec = doc.sections[0]
    sec.page_height, sec.page_width = Cm(29.7), Cm(21)
    sec.top_margin, sec.bottom_margin, sec.left_margin, sec.right_margin = Cm(3.5), Cm(2.5), Cm(3), Cm(3)
    st = doc.styles["Normal"]
    st.font.name, st.font.size = "Times New Roman", Pt(12)
    st.paragraph_format.space_after = Pt(6)
    for name, size in (("Heading 1", 13), ("Heading 2", 12)):
        h = doc.styles[name]
        h.font.name, h.font.size, h.font.bold = "Times New Roman", Pt(size), True
        h.font.color.rgb = None

    cited: list[str] = []

    def runs(par, text: str, bold=False, italic=False):
        for part in INLINE.split(text):
            if not part:
                continue
            if part.startswith("**"):
                runs(par, part[2:-2], True, italic)
            elif part.startswith("`"):
                r = par.add_run(part[1:-1]); r.font.name = "Courier New"; r.font.size = Pt(10.5)
            elif part.startswith("$"):
                r = par.add_run(part[1:-1]); r.italic = True
            elif part.startswith("[@"):
                keys = [k.strip(" @") for k in part[2:-1].split(";")]
                cited.extend(k for k in keys if k not in cited)
                par.add_run("[" + "; ".join(cite_label(bib[k]) for k in keys) + "]")
            elif part.startswith("*"):
                runs(par, part[1:-1], bold, True)
            else:
                r = par.add_run(part); r.bold, r.italic = bold, italic

    def center(text, size=12, bold=False, italic=False):
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(text); r.font.size, r.bold, r.italic = Pt(size), bold, italic

    center(meta["title"], 16, bold=True)
    center(meta["authors"])
    center(meta["address"].replace("--", "–"), 10)
    if meta.get("email"):
        center(meta["email"], 10, italic=False)

    n_sec = n_sub = n_fig = n_tab = n_lst = 0
    in_abs = False
    for b in blocks:
        kind = b[0]
        if kind == "h2" and b[1] in ("Abstract", "Resumo"):
            in_abs = True
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            r = p.add_run(f"{b[1]}. "); r.bold = True
            continue
        if kind == "h2":
            in_abs = False
            n_sec += 1; n_sub = 0
            doc.add_heading(f"{n_sec}. {b[1]}", level=1)
        elif kind == "h3":
            n_sub += 1
            doc.add_heading(f"{n_sec}.{n_sub}. {b[1]}", level=2)
        elif kind == "p":
            if in_abs:  # resumo: paragrafo unico, recuado, italico
                p = doc.paragraphs[-1]
                p.paragraph_format.left_indent = p.paragraph_format.right_indent = Cm(0.8)
                runs(p, b[1], italic=True)
            else:
                p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                runs(p, b[1])
        elif kind in ("ul", "ol"):
            for x in b[1]:
                p = doc.add_paragraph(style="List Bullet" if kind == "ul" else "List Number")
                runs(p, x)
        elif kind == "img":
            n_fig += 1
            doc.add_picture(str((HERE / b[2]).resolve()), width=Cm(15))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(f"Figura {n_fig}. "); r.bold = True; r.font.size = Pt(10)
            runs(p, b[1])
        elif kind == "code":
            n_lst += 1
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(f"Listagem {n_lst}. "); r.bold = True
            runs(p, b[2])
            p = doc.add_paragraph()
            r = p.add_run(b[1]); r.font.name = "Courier New"; r.font.size = Pt(9.5)
        elif kind == "table":
            n_tab += 1
            rows = b[1]
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(f"Tabela {n_tab}. "); r.bold = True
            runs(p, b[2])
            t = doc.add_table(rows=len(rows), cols=len(rows[0]))
            t.style = "Table Grid"
            for i, row in enumerate(rows):
                for j, c in enumerate(row):
                    cell = t.cell(i, j); cell.text = ""
                    cp = cell.paragraphs[0]
                    if j > 0:
                        cp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    runs(cp, c, bold=(i == 0))
                    for rr in cp.runs:
                        rr.font.size = Pt(10)
            doc.add_paragraph()

    doc.add_heading("Referências", level=1)
    for key in sorted(cited, key=lambda k: authors(bib[k])[0].lower()):
        p = doc.add_paragraph(ref_text(bib[key]))
        p.paragraph_format.left_indent = Cm(0.8)
        p.paragraph_format.first_line_indent = Cm(-0.8)
    doc.save(out)


def main() -> None:
    meta, blocks = parse_md((HERE / "artigo.md").read_text(encoding="utf-8"))
    bib = parse_bib((HERE / "referencias.bib").read_text(encoding="utf-8"))
    (HERE / "img").mkdir(exist_ok=True)  # Overleaf nao aceita caminhos com ../
    for b in blocks:
        if b[0] == "img":
            shutil.copy(HERE / b[2], HERE / "img" / Path(b[2]).name)
    (HERE / "artigo.tex").write_text(to_tex(meta, blocks), encoding="utf-8")
    to_docx(meta, blocks, bib, HERE / "artigo.docx")
    print("ok: artigo.tex, artigo.docx")


if __name__ == "__main__":
    main()
