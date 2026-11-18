"""Text-to-Cypher com Claude, protegido por duas travas de somente leitura.

1. Filtro lexical: rejeita clausulas de escrita e procedures administrativas.
2. Execucao em transacao READ (o proprio Neo4j recusa escrita).
"""
from __future__ import annotations

import re

from app.config import LLM_MODEL
from app.db import run_read
from app.schema import describe_schema

_STRINGS = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")
_COMMENTS = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
_FORBIDDEN = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|LOAD\s+CSV|GRANT|DENY|REVOKE|"
    r"ALTER|RENAME|TERMINATE|START|STOP)\b"
    r"|\bCALL\s+(dbms|db\.(create|drop|clear)|apoc\.(create|merge|refactor|periodic|"
    r"cypher\.(run|do)|load|export|trigger)|gds\.[\w.]*\.(write|mutate))",
    re.I,
)

SYSTEM = f"""Voce converte perguntas em portugues para UMA consulta Cypher de leitura no Neo4j.
Schema do grafo:
{describe_schema()}
Regras: somente MATCH/OPTIONAL MATCH/WHERE/WITH/RETURN/ORDER BY/LIMIT; nada de escrita.
Compare nomes com toLower(e.name) CONTAINS toLower('...'). Retorne colunas com nomes claros
e no maximo 25 linhas. Responda apenas com a consulta, sem markdown."""


def is_read_only(cypher: str) -> bool:
    bare = _COMMENTS.sub(" ", _STRINGS.sub("''", cypher))
    return not _FORBIDDEN.search(bare) and ";" not in bare.strip().rstrip(";")


def ensure_limit(cypher: str, limit: int = 25) -> str:
    c = cypher.strip().rstrip(";")
    return c if re.search(r"\bLIMIT\s+\d+\s*$", c, re.I) else f"{c} LIMIT {limit}"


def generate_cypher(client, question: str) -> str:
    response = client.beta.messages.create(
        model=LLM_MODEL,
        max_tokens=4000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low"},
        system=SYSTEM,
        messages=[{"role": "user", "content": question}],
    )
    if response.stop_reason == "refusal":
        return ""
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return re.sub(r"^```\w*\s*|\s*```$", "", text).strip()


def run_text2cypher(client, question: str) -> dict:
    cypher = generate_cypher(client, question)
    if not cypher:
        return {"cypher": "", "rows": [], "error": "modelo nao gerou consulta"}
    if not is_read_only(cypher):
        return {"cypher": cypher, "rows": [], "error": "consulta bloqueada: nao e somente leitura"}
    cypher = ensure_limit(cypher)
    try:
        return {"cypher": cypher, "rows": run_read(cypher), "error": None}
    except Exception as exc:  # consulta invalida gerada pelo modelo nao derruba a resposta
        return {"cypher": cypher, "rows": [], "error": f"{type(exc).__name__}: {exc}"[:300]}
