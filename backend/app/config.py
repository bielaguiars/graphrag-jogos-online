"""Configuracao central lida de variaveis de ambiente (.env na raiz do repo)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RESULTS_DIR = ROOT / "results"


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "graphrag-dev")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-opus-5-5")

EMBED_MODEL = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-small")
EMBED_DIM = int(os.getenv("EMBED_DIM", "384"))

# Resolucao de entidades: similaridade minima de embedding para fundir nos
ER_THRESHOLD = float(os.getenv("ER_THRESHOLD", "0.93"))
# Abaixo deste cosseno (sem entidade citada pelo nome) a pergunta e tratada como fora do grafo.
# Calibrado no e5-small: perguntas fora do dominio ~0.89-0.91, do dominio ~0.92-0.94.
OOD_THRESHOLD = float(os.getenv("OOD_THRESHOLD", "0.924"))


def llm_enabled() -> bool:
    return bool(ANTHROPIC_API_KEY)
