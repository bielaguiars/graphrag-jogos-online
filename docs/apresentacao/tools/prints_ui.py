"""Tira os prints da interface Streamlit do projeto (rodando em http://localhost:8502).

Uso: python prints_ui.py
"""
import urllib.parse
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8502/"
OUT = Path(__file__).resolve().parent.parent / "prints"
OUT.mkdir(exist_ok=True)
VALVE = "Que jogo da Valve surgiu de um mod de Warcraft III?"
DAYZ = "Que jogo militar deu origem ao mod que virou o DayZ, e quem criou esse mod?"
FORA = "Qual é a capital da França?"


def abrir(pg, pergunta):
    pg.goto(BASE + "?q=" + urllib.parse.quote(pergunta), wait_until="networkidle")
    pg.get_by_text("Subgrafo usado na resposta").first.wait_for(timeout=120000)
    pg.wait_for_timeout(5000)  # pyvis estabiliza o layout


def aba(pg, prefixo, nome):
    pg.get_by_role("tab", name=prefixo).first.click()
    pg.wait_for_timeout(1500)
    tabs = pg.locator('[data-testid="stTabs"]').first
    tabs.scroll_into_view_if_needed()
    pg.wait_for_timeout(500)
    tabs.screenshot(path=str(OUT / f"{nome}.png"))


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1.25)

    abrir(pg, VALVE)
    pg.screenshot(path=str(OUT / "ui_multihop.png"))
    aba(pg, "Triplas", "ui_triplas")
    aba(pg, "Cypher", "ui_cypher")
    aba(pg, "Avaliação", "ui_avaliacao")

    # mesma pergunta no modo só vetorial
    pg.evaluate("window.scrollTo(0, 0)")
    pg.locator('[data-testid="stSidebar"]').get_by_text("Só vetorial").click()
    pg.wait_for_timeout(6000)
    pg.screenshot(path=str(OUT / "ui_vetorial.png"))
    pg.locator('[data-testid="stSidebar"]').get_by_text("GraphRAG", exact=True).click()
    pg.wait_for_timeout(3000)

    abrir(pg, DAYZ)
    pg.screenshot(path=str(OUT / "ui_dayz.png"))

    pg.goto(BASE + "?q=" + urllib.parse.quote(FORA), wait_until="networkidle")
    pg.wait_for_timeout(8000)
    pg.screenshot(path=str(OUT / "ui_fora_dominio.png"))
    b.close()
print("ok")
