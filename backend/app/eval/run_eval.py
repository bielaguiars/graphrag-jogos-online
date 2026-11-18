"""Avaliacao: GraphRAG (hibrido + multi-hop) vs RAG vetorial puro.

Mede o CONTEXTO que seria entregue ao LLM (independe de chave de API):
- recall@contexto: fracao dos itens do gabarito presentes no contexto;
- suporte completo: todos os itens presentes (condicao para responder sem inventar);
- tamanho do contexto e latencia;
- abstencao: perguntas fora do dominio devem ser recusadas.
Com --llm (exige ANTHROPIC_API_KEY) tambem gera respostas e mede recall na resposta e frases
sem apoio apontadas pelo verificador de citacoes.

Uso: python -m app.eval.run_eval [--llm]
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import time
from pathlib import Path

from app.config import RESULTS_DIR, llm_enabled
from app.generate import answer_llm, build_context
from app.retrieval.hybrid import retrieve, retrieve_vector_only

QUESTIONS = Path(__file__).with_name("questions.json")


def found(item: list[str], text: str) -> bool:
    t = text.lower()
    return any(alt.lower() in t for alt in item)


def score_context(gold: list[list[str]], context: str) -> tuple[float, bool]:
    if not gold:
        return 1.0, True
    hits = sum(found(g, context) for g in gold)
    return hits / len(gold), hits == len(gold)


def evaluate(use_llm: bool = False) -> dict:
    qs = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    client = None
    if use_llm:
        import anthropic
        client = anthropic.Anthropic()
    rows = []
    for q in qs:
        row = {"id": q["id"], "hops": q["hops"], "question": q["question"]}
        for name, fn in (("graph", retrieve), ("vector", retrieve_vector_only)):
            t0 = time.perf_counter()
            res = fn(q["question"])
            ms = (time.perf_counter() - t0) * 1000
            ctx = build_context(res)
            recall, full = score_context(q["gold"], ctx)
            abstains = res.out_of_domain if name == "graph" else False  # baseline nao tem mecanismo
            r = {"recall": round(recall, 3), "full": full, "ctx_chars": len(ctx),
                 "ms": round(ms), "abstains": abstains,
                 "missing": [g[0] for g in q["gold"] if not found(g, ctx)]}
            if client is not None and q["gold"]:
                gen = answer_llm(client, res)
                a_recall, _ = score_context(q["gold"], gen["answer"])
                r.update({"answer_recall": round(a_recall, 3),
                          "unsupported": len(gen["unsupported_sentences"]),
                          "invalid_citations": len(gen["invalid_citations"])})
            row[name] = r
        rows.append(row)
        print(f"{q['id']}: grafo {row['graph']['recall']:.2f} | vetorial {row['vector']['recall']:.2f}")
    return {"rows": rows, "summary": summarize(rows), "llm": use_llm}


def summarize(rows: list[dict]) -> dict:
    inq = [r for r in rows if r["hops"] > 0]
    ood = [r for r in rows if r["hops"] == 0]
    out = {}
    for name in ("graph", "vector"):
        s = {
            "recall_mean": round(st.mean(r[name]["recall"] for r in inq), 3),
            "full_support_rate": round(sum(r[name]["full"] for r in inq) / len(inq), 3),
            "recall_multihop": round(st.mean(r[name]["recall"] for r in inq if r["hops"] >= 2), 3),
            "recall_1hop": round(st.mean(r[name]["recall"] for r in inq if r["hops"] == 1), 3),
            "ctx_chars_mean": round(st.mean(r[name]["ctx_chars"] for r in inq)),
            "latency_ms_median": round(st.median(r[name]["ms"] for r in rows)),
            "ood_abstention_rate": round(sum(r[name]["abstains"] for r in ood) / len(ood), 3),
            "false_abstention_rate": round(sum(r[name]["abstains"] for r in inq) / len(inq), 3),
        }
        if "answer_recall" in inq[0][name]:
            s["answer_recall_mean"] = round(st.mean(r[name]["answer_recall"] for r in inq), 3)
            s["unsupported_sentences_total"] = sum(r[name]["unsupported"] for r in inq)
        out[name] = s
    return out


def to_markdown(result: dict) -> str:
    g, v = result["summary"]["graph"], result["summary"]["vector"]
    rows = result["rows"]
    n_in = sum(r["hops"] > 0 for r in rows)
    n1 = sum(r["hops"] == 1 for r in rows)
    labels = [
        ("recall_mean", f"Recall@contexto (média, {n_in} perguntas)"),
        ("full_support_rate", "Perguntas com suporte completo"),
        ("recall_1hop", f"Recall — 1 salto ({n1})"),
        ("recall_multihop", f"Recall — 2+ saltos ({n_in - n1})"),
        ("ctx_chars_mean", "Tamanho médio do contexto (caracteres)"),
        ("latency_ms_median", "Latência mediana de recuperação (ms)"),
        ("ood_abstention_rate", f"Abstenção correta fora do domínio ({len(rows) - n_in})"),
        ("false_abstention_rate", "Abstenção indevida no domínio"),
        ("answer_recall_mean", "Recall na resposta do LLM"),
        ("unsupported_sentences_total", "Frases sem apoio (verificador)"),
    ]
    lines = ["| Métrica | GraphRAG | RAG vetorial |", "|---|---:|---:|"]
    lines += [f"| {lab} | {g[k]} | {v[k]} |" for k, lab in labels if k in g]
    lines += ["", "| Pergunta | Saltos | GraphRAG | Vetorial | Faltou no GraphRAG |",
              "|---|---:|---:|---:|---|"]
    for r in rows:
        lines.append(f"| {r['id']} {r['question']} | {r['hops']} | {r['graph']['recall']:.2f} | "
                     f"{r['vector']['recall']:.2f} | {', '.join(r['graph']['missing']) or '—'} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="gera respostas com Claude")
    args = ap.parse_args()
    if args.llm and not llm_enabled():
        raise SystemExit("--llm exige ANTHROPIC_API_KEY no .env")
    result = evaluate(args.llm)
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "eval.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    (RESULTS_DIR / "eval.md").write_text(to_markdown(result), encoding="utf-8")
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
