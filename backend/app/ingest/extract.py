"""Pipeline Text-to-Graph: extracao de entidades (NER) e relacoes (RE) com Claude.

Cada artigo da Wikipedia vira um JSON em data/extracted/<doc_id>.json validado pelo schema
abaixo. Arquivos ja existentes sao reaproveitados (cache): o repositorio traz a extracao
pre-gerada, e `--force` refaz tudo pela API (exige ANTHROPIC_API_KEY).

Uso: python -m app.ingest.extract [--force] [--only league-of-legends ...]
"""
from __future__ import annotations

import argparse
import json
from typing import Literal

from pydantic import BaseModel, Field

from app.config import DATA_DIR, LLM_MODEL, llm_enabled

EntityType = Literal["Game", "Company", "Person", "Genre", "Platform", "Engine", "Franchise",
                     "Event", "Concept"]
RelationType = Literal[
    "DEVELOPED_BY",   # Game -> Company|Person
    "PUBLISHED_BY",   # Game -> Company
    "HAS_GENRE",      # Game -> Genre
    "AVAILABLE_ON",   # Game -> Platform
    "USES_ENGINE",    # Game -> Engine
    "PART_OF",        # Game -> Franchise
    "SEQUEL_OF",      # Game -> Game (sequencia, remake ou sucessor)
    "BASED_ON",       # Game -> Game|Concept (mod de, inspirado em, derivado de)
    "HAS_FEATURE",    # Game -> Concept (free-to-play, battle pass, cross-play...)
    "FEATURED_IN",    # Game -> Event (campeonato, liga)
    "SUBSIDIARY_OF",  # Company -> Company (pertence a / foi comprada por)
    "CREATED_BY",     # Game|Company|Event -> Person (criador, fundador, diretor)
    "ORGANIZED_BY",   # Event -> Company
]


class Entity(BaseModel):
    name: str = Field(description="Nome canonico curto, ex.: 'Riot Games', 'Unreal Engine 4'")
    type: EntityType
    aliases: list[str] = Field(default_factory=list)
    description: str = Field(description="Uma frase em portugues")


class Relation(BaseModel):
    source: str = Field(description="Nome de entidade presente em entities")
    type: RelationType
    target: str
    evidence: str = Field(description="Trecho copiado literalmente do texto")


class Extraction(BaseModel):
    doc_id: str
    subject: str = Field(description="Nome canonico da entidade que o artigo descreve")
    entities: list[Entity]
    relations: list[Relation]


EXTRACTION_PROMPT = """Voce e um extrator de grafo de conhecimento sobre jogos online.
Leia o titulo e o texto (introducao de um artigo da Wikipedia) e extraia entidades e relacoes.

Tipos de entidade:
- Game: jogo, mod jogavel ou modo de jogo lancado separadamente (Dota 2, Fortnite Battle Royale)
- Company: desenvolvedora, publicadora, dona (Riot Games, Valve, Tencent, Epic Games)
- Person: criador, diretor, fundador (IceFrog, Brendan Greene, Markus Persson)
- Genre: genero (multiplayer online battle arena, battle royale, MMORPG, first-person shooter)
- Platform: plataforma (Windows, macOS, PlayStation 4, Xbox One, Nintendo Switch, Android, iOS)
- Engine: motor grafico (Unreal Engine 4, Source, Source 2, Unity)
- Franchise: serie (Warcraft, Counter-Strike, Call of Duty, Final Fantasy)
- Event: campeonato ou liga (League of Legends World Championship, The International)
- Concept: modelo de negocio ou mecanica (free-to-play, microtransactions, battle pass,
  cross-platform play, early access, esports, mod)

Relacoes (source -> target):
- Game DEVELOPED_BY Company|Person; Game PUBLISHED_BY Company
- Game HAS_GENRE Genre; Game AVAILABLE_ON Platform; Game USES_ENGINE Engine
- Game PART_OF Franchise; Game SEQUEL_OF Game (sequencia, sucessor ou remake)
- Game BASED_ON Game|Concept (era mod de, foi inspirado em, deriva de)
- Game HAS_FEATURE Concept; Game FEATURED_IN Event
- Company SUBSIDIARY_OF Company (subsidiaria, comprada por)
- Game|Company|Event CREATED_BY Person; Event ORGANIZED_BY Company

Regras:
1. So extraia o que esta escrito no texto. Nada de conhecimento externo.
2. `evidence` e um trecho copiado literalmente do texto (ate ~25 palavras).
3. Nomes canonicos curtos e consistentes entre artigos: "Valve", "Riot Games", "Blizzard
   Entertainment", "Epic Games", "Tencent", "Microsoft Windows" -> use "Windows",
   "PlayStation 4", "Xbox One", "Android", "iOS", "Free-to-play", "Battle royale",
   "Multiplayer online battle arena", "MMORPG", "First-person shooter", "Esports".
   Formas longas ou siglas vao em `aliases`.
4. `subject` e a entidade que o artigo descreve; ela tambem aparece em `entities`.
5. Toda entidade usada em relacao aparece em `entities`. Entre 6 e 25 entidades.
6. `description` em portugues, uma frase.
"""


def build_user_message(doc: dict) -> str:
    return f"doc_id: {doc['doc_id']}\nTitulo: {doc['title']}\nTexto: {doc['text']}"


def extract_with_claude(client, doc: dict) -> Extraction:
    """Uma chamada com saida JSON restrita ao schema."""
    response = client.beta.messages.create(
        model=LLM_MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=EXTRACTION_PROMPT,
        messages=[{"role": "user", "content": build_user_message(doc)}],
        output_config={"format": {"type": "json_schema",
                                  "schema": Extraction.model_json_schema()}},
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"extracao recusada para {doc['doc_id']}")
    text = "".join(b.text for b in response.content if b.type == "text")
    return Extraction.model_validate_json(text)


def validate_evidence(ex: Extraction, text: str) -> Extraction:
    """Descarta relacoes cuja evidencia nao aparece no texto (anti-alucinacao na ingestao)."""
    norm = " ".join(text.lower().split())
    kept = [r for r in ex.relations if " ".join(r.evidence.lower().split())[:60] in norm]
    names = {e.name for e in ex.entities}
    kept = [r for r in kept if r.source in names and r.target in names]
    return ex.model_copy(update={"relations": kept})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="refaz mesmo com cache")
    ap.add_argument("--only", nargs="*", help="doc_ids especificos")
    args = ap.parse_args()

    docs = json.loads((DATA_DIR / "raw" / "articles.json").read_text(encoding="utf-8"))
    out_dir = DATA_DIR / "extracted"
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = [d for d in docs if (not args.only or d["doc_id"] in args.only)
            and (args.force or not (out_dir / f"{d['doc_id']}.json").exists())]
    if not todo:
        print("Nada a extrair: todos os artigos ja tem extracao em data/extracted/.")
        return
    if not llm_enabled():
        raise SystemExit(f"{len(todo)} artigos sem extracao e ANTHROPIC_API_KEY ausente.")

    import anthropic
    client = anthropic.Anthropic()
    for d in todo:
        ex = validate_evidence(extract_with_claude(client, d), d["text"])
        (out_dir / f"{d['doc_id']}.json").write_text(ex.model_dump_json(indent=2), encoding="utf-8")
        print(f"{d['doc_id']}: {len(ex.entities)} entidades, {len(ex.relations)} relacoes")


if __name__ == "__main__":
    main()
