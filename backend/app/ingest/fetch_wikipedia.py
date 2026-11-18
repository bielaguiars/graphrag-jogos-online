"""Baixa a introducao dos artigos da Wikipedia (en) sobre jogos online para data/raw/articles.json.

API publica MediaWiki (action=query, prop=extracts, exintro), sem chave.
Uso: python -m app.ingest.fetch_wikipedia
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request

from app.config import DATA_DIR

TITLES = [
    # MOBA e derivados
    "League of Legends", "Dota 2", "Defense of the Ancients", "Warcraft III: Reign of Chaos",
    "Heroes of the Storm", "Smite (video game)", "Mobile Legends: Bang Bang", "Honor of Kings",
    "Arena of Valor", "Teamfight Tactics", "Dota Auto Chess",
    # battle royale
    "Fortnite", "Fortnite Battle Royale", "PUBG: Battlegrounds", "Apex Legends",
    "Call of Duty: Warzone", "Free Fire (video game)", "H1Z1", "DayZ (video game)", "Arma 2",
    "Fall Guys",
    # tiro competitivo
    "Counter-Strike (video game)", "Counter-Strike: Global Offensive", "Counter-Strike 2",
    "Half-Life (video game)", "Valorant", "Overwatch (video game)", "Overwatch 2",
    "Team Fortress 2", "Tom Clancy's Rainbow Six Siege", "Destiny 2", "Halo Infinite",
    "Titanfall 2",
    # MMO
    "World of Warcraft", "Final Fantasy XIV", "EVE Online", "RuneScape", "Old School RuneScape",
    "Guild Wars 2", "Lineage II", "Ragnarok Online", "Tibia (video game)", "Black Desert Online",
    "The Elder Scrolls Online", "Lost Ark", "New World (video game)", "MapleStory",
    # mundos abertos, sandbox e social
    "Minecraft", "Roblox", "Among Us", "Rust (video game)", "Grand Theft Auto Online",
    "Genshin Impact", "Sea of Thieves", "Rocket League", "Path of Exile", "Diablo IV",
    # mobile, cartas e estrategia
    "Clash of Clans", "Clash Royale", "Brawl Stars", "Hearthstone", "Pokémon Go",
    "StarCraft II: Wings of Liberty",
    # e-sports
    "League of Legends World Championship", "The International (esports)",
]

API = ("https://en.wikipedia.org/w/api.php?action=query&format=json&formatversion=2"
       "&prop=extracts|info&inprop=url&exintro=1&explaintext=1&redirects=1&titles={titles}")
HEADERS = {"User-Agent": "graphrag-kag-academic/0.1 (projeto academico)"}


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def parse(payload: dict) -> list[dict]:
    out = []
    for p in payload.get("query", {}).get("pages", []):
        text = " ".join((p.get("extract") or "").split())
        if p.get("missing") or not text:
            continue
        out.append({"doc_id": slugify(p["title"]), "title": p["title"], "text": text,
                    "url": p.get("fullurl", ""), "source": "wikipedia-en"})
    return out


def fetch(titles: list[str], batch: int = 20) -> list[dict]:
    docs: list[dict] = []
    for i in range(0, len(titles), batch):
        q = urllib.parse.quote("|".join(titles[i:i + batch]))
        req = urllib.request.Request(API.format(titles=q), headers=HEADERS)
        with urllib.request.urlopen(req, timeout=60) as r:
            docs.extend(parse(json.loads(r.read().decode("utf-8"))))
        time.sleep(1)
    return docs


def main() -> None:
    docs = fetch(TITLES)
    dest = DATA_DIR / "raw" / "articles.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8")
    got = {d["title"] for d in docs}
    print(f"{len(docs)} artigos salvos em {dest}. Faltando/redirecionados: "
          f"{sorted(t for t in TITLES if t not in got) or 'nenhum'}")


if __name__ == "__main__":
    main()
