"""Coletor: le a Biblioteca de Anuncios da Meta com Playwright.

A API oficial nao cobre anuncios comerciais fora da Uniao Europeia, entao o
coletor abre a biblioteca publica e le as respostas que a propria pagina
recebe da Meta (JSON). Isso e mais estavel que ler o HTML da tela.
"""
import json
import random
import re
import time
from urllib.parse import quote

BASE = "https://www.facebook.com/ads/library/"


# ---------------------------------------------------------------- links

def link_busca(palavra, pais="ALL", idioma="en"):
    """Link da biblioteca para uma busca por palavra-chave, so ativos."""
    return (f"{BASE}?active_status=active&ad_type=all&country={pais}"
            f"&q={quote(palavra)}&search_type=keyword_unordered&media_type=all"
            f"&content_languages[0]={idioma}")


def link_anunciante(page_id, pais="ALL"):
    """Link da biblioteca filtrado em um anunciante, so ativos."""
    return (f"{BASE}?active_status=active&ad_type=all&country={pais}"
            f"&view_all_page_id={page_id}&search_type=page&media_type=all")


# ------------------------------------------------------- leitura do JSON

def _varrer(obj):
    """Anda por qualquer JSON e devolve todo dict que parece um anuncio."""
    if isinstance(obj, dict):
        if "ad_archive_id" in obj and ("snapshot" in obj or "page_id" in obj):
            yield obj
        for v in obj.values():
            yield from _varrer(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _varrer(v)


def _normalizar(d):
    """Transforma o anuncio bruto da Meta em um dict simples."""
    snap = d.get("snapshot") or {}
    corpo = snap.get("body")
    if isinstance(corpo, dict):
        corpo = corpo.get("text")
    links = [snap.get("link_url")]
    for c in snap.get("cards") or []:
        links.append(c.get("link_url"))
    texto = " ".join(x for x in [corpo or "", snap.get("title") or ""] if x)
    return {
        "id": str(d["ad_archive_id"]),
        "page_id": str(d.get("page_id") or snap.get("page_id") or ""),
        "page_name": d.get("page_name") or snap.get("page_name") or "",
        "inicio": d.get("start_date"),      # timestamp unix
        "fim": d.get("end_date"),
        "ativo": d.get("is_active"),
        "links": [l for l in links if l],
        "texto": texto.strip(),
        "formato": snap.get("display_format"),
        "cta": snap.get("cta_text"),
    }


def extrair_anuncios(texto):
    """Acha anuncios em um texto: JSON puro, JSON em linhas ou HTML com <script>."""
    pedacos = []
    if "<script" in texto:
        pedacos += re.findall(r"<script[^>]*type=\"application/json\"[^>]*>(.*?)</script>",
                              texto, flags=re.S)
    else:
        pedacos.append(texto)
    achados = {}
    for p in pedacos:
        candidatos = [p] + p.splitlines()
        for c in candidatos:
            c = c.strip()
            if c.startswith("for (;;);"):
                c = c[len("for (;;);"):]
            if not c.startswith(("{", "[")) or "ad_archive_id" not in c:
                continue
            try:
                dado = json.loads(c)
            except ValueError:
                continue
            for bruto in _varrer(dado):
                a = _normalizar(bruto)
                achados[a["id"]] = a
            break  # o texto inteiro ja foi lido, nao precisa das linhas
    return list(achados.values())


# ------------------------------------------------------------- idioma

_EN = set("the and to of a in is you your for with that this it on are be as at or "
          "from by have has not but what how why can will we our their they get "
          "more all new now just free".split())


def eh_ingles(texto):
    """True/False, ou None quando o texto e curto demais para saber."""
    palavras = re.findall(r"[a-zA-ZÀ-ɏ']+", (texto or "").lower())
    if len(palavras) < 8:
        return None
    nao_latino = len(re.findall(r"[Ѐ-ӿ؀-ۿ぀-ヿ一-鿿가-힯]", texto))
    if nao_latino > 5:
        return False
    return sum(p in _EN for p in palavras) / len(palavras) >= 0.2


# ------------------------------------------------------------ navegador

class Coletor:
    def __init__(self, cfg, depurar=False):
        self.cfg = cfg
        self.nav = cfg.get("navegador", {})
        self.depurar = depurar
        self.respostas = []

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        opcoes = {"headless": self.nav.get("invisivel", True)}
        if self.nav.get("caminho_chromium"):
            opcoes["executable_path"] = self.nav["caminho_chromium"]
            opcoes["args"] = ["--no-sandbox"]
        self._b = self._pw.chromium.launch(**opcoes)
        self._ctx = self._b.new_context(locale="en-US", viewport={"width": 1366, "height": 900})
        self.pg = self._ctx.new_page()
        self.pg.on("response", self._ao_receber)
        return self

    def __exit__(self, *a):
        self._b.close()
        self._pw.stop()

    def _pausa(self, extra=0):
        time.sleep(random.uniform(self.nav.get("pausa_min", 3), self.nav.get("pausa_max", 7)) + extra)

    def _ao_receber(self, r):
        if "graphql" not in r.url:
            return
        try:
            self.respostas.append(r.text())
        except Exception:
            pass

    def _ler(self, url, rolagens, nome):
        """Abre a url, rola a lista e devolve (anuncios, total_na_tela)."""
        self.respostas = []
        self.pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        self._pausa(3)
        vistos, sem_novo = {}, 0
        for _ in range(rolagens + 1):
            textos = list(self.respostas) + [self.pg.content()]
            antes = len(vistos)
            for t in textos:
                for a in extrair_anuncios(t):
                    vistos[a["id"]] = a
            sem_novo = sem_novo + 1 if len(vistos) == antes else 0
            if sem_novo >= 2:
                break
            self.pg.mouse.wheel(0, 4000)
            self._pausa()
        corpo = self.pg.inner_text("body")
        if self.depurar:
            self._salvar_depuracao(nome, corpo, vistos)
        return list(vistos.values()), self._total_na_tela(corpo)

    @staticmethod
    def _total_na_tela(corpo):
        """Le o '~61 results' que a biblioteca mostra no topo."""
        m = re.search(r"~?\s*([\d.,]+)\s*([KkMm]?)\s+results?", corpo)
        if not m:
            return None
        n = float(m.group(1).replace(",", ""))
        n *= {"k": 1e3, "m": 1e6}.get(m.group(2).lower(), 1)
        return int(n)

    def _salvar_depuracao(self, nome, corpo, vistos):
        import os
        os.makedirs("depuracao", exist_ok=True)
        base = "depuracao/" + re.sub(r"\W+", "_", nome)[:40]
        with open(base + "_tela.txt", "w") as f:
            f.write(corpo[:5000])
        with open(base + "_respostas.json", "w") as f:
            json.dump({"qtd_respostas": len(self.respostas),
                       "anuncios_lidos": len(vistos),
                       "amostra": [r[:1500] for r in self.respostas[:3]]}, f, indent=1)
        self.pg.screenshot(path=base + ".png")

    def buscar(self, palavra):
        """Busca por palavra-chave. Devolve anuncios ativos em ingles."""
        c = self.cfg
        url = link_busca(palavra, c.get("pais", "ALL"), c.get("idioma", "en"))
        anuncios, _ = self._ler(url, c.get("rolagens_por_busca", 6), "busca_" + palavra)
        return [a for a in anuncios if eh_ingles(a["texto"]) is not False]

    def anunciante(self, page_id):
        """Todos os anuncios ativos de um anunciante e o total mostrado na tela."""
        url = link_anunciante(page_id, self.cfg.get("pais", "ALL"))
        anuncios, total = self._ler(url, 10, "pagina_" + page_id)
        return [a for a in anuncios if eh_ingles(a["texto"]) is not False], total
