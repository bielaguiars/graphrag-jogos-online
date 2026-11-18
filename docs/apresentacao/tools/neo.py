"""Dirige o Neo4j Browser (Query) do container `graphrag-neo4j` e tira prints de cada consulta.

Só conecta em neo4j://localhost:7689 (o container dos exercícios), nunca na porta padrão.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://localhost:7476/browser/?dbms=neo4j://localhost:7689"
SHOTS = Path(__file__).resolve().parent.parent / "prints"
SHOTS.mkdir(exist_ok=True)


class Neo:
    def __init__(self, width=1440, height=900, scale=1.5):
        self._p = sync_playwright().start()
        self.browser = self._p.chromium.launch()
        self.page = self.browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=scale)
        pg = self.page
        pg.goto(URL, wait_until="networkidle")
        pg.wait_for_timeout(1500)
        btn = pg.get_by_role("button", name="Connect", exact=True)
        if btn.count():
            assert "localhost:7689" in pg.inner_text("body"), "conexão não aponta para o container de exercícios"
            btn.click()
        pg.wait_for_selector('[data-testid="connection-status-indicator-success"]', timeout=20000)
        pg.wait_for_timeout(1000)
        self.dismiss()
        # limpa os frames de boas-vindas e recolhe o painel lateral
        for _ in range(5):
            rm = pg.get_by_role("button", name="Remove frame")
            if not rm.count():
                break
            rm.first.click()
            pg.wait_for_timeout(200)
        # botão de recolher o painel lateral (sem rótulo acessível): fica à esquerda da aba "Stream"
        stream = pg.locator("button", has_text="Stream")
        box = stream.first.bounding_box()
        pg.mouse.click(box["x"] - 30, box["y"] + box["height"] / 2)
        pg.wait_for_timeout(600)
        self.dismiss()

    def dismiss(self):
        for _ in range(3):
            d = self.page.get_by_role("button", name="Dismiss", exact=True)
            if d.count() and d.first.is_visible():
                d.first.click()
                self.page.wait_for_timeout(300)
            else:
                break

    # ---------- editor ----------
    def set_query(self, q: str):
        pg = self.page
        ed = pg.locator('[data-testid="main-editor"] .cm-content')
        ed.click()
        pg.keyboard.press("Control+A")
        pg.keyboard.press("Delete")
        pg.keyboard.insert_text(q)
        got = ed.inner_text().replace("\u00a0", " ")
        norm = lambda s: re.sub(r"\s+", " ", s).strip()
        if len(q) > 2500:  # o CodeMirror s\u00f3 desenha as linhas vis\u00edveis
            if not norm(got).startswith(norm(q)[:60]):
                raise RuntimeError("in\u00edcio do script n\u00e3o confere no editor")
        elif norm(got) != norm(q):
            raise RuntimeError(f"editor ficou diferente:\n{got!r}\n!=\n{q!r}")

    def frames(self):
        return self.page.locator('[data-testid="frame"]')

    def run(self, q: str, shot: str | None = None, view: str | None = None, wait_ms: int = 1200,
            timeout: float = 60) -> str:
        """Roda a consulta, espera o frame novo terminar e, se pedido, salva o print do frame."""
        pg = self.page
        before = self.frames().count()
        q = q.strip().rstrip(";").strip()
        self.set_query(q)
        pg.locator('[data-testid="run-button"]').first.click()
        t0 = time.time()
        while self.frames().count() <= before:
            if time.time() - t0 > timeout:
                raise TimeoutError("frame não apareceu")
            pg.wait_for_timeout(200)
        frame = self.frames().first
        # espera o rodapé de status (sucesso ou erro) e o texto parar de mudar
        last, stable_since = None, None
        while time.time() - t0 < timeout:
            txt = frame.inner_text()
            done = re.search(r"Started streaming|Completed after|error|Error|failed", txt)
            if txt != last:
                last, stable_since = txt, time.time()
            elif done and time.time() - stable_since > 1.5:
                break
            pg.wait_for_timeout(300)
        self.dismiss()
        if view:
            tab = frame.get_by_role("tab", name=view, exact=True)
            if tab.count():
                tab.first.click()
        pg.wait_for_timeout(wait_ms)
        if shot:
            frame.scroll_into_view_if_needed()
            frame.screenshot(path=str(SHOTS / f"{shot}.png"))
        return frame.inner_text()

    def close(self):
        self.browser.close()
        self._p.stop()
