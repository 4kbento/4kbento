"""Analisador: agrupa anuncios por anunciante, pontua e le a pagina de vendas."""
import math
import re
import statistics
import time
from collections import Counter
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

# Dominios que nao sao pagina de vendas
IGNORAR = ("facebook.com", "fb.com", "fb.me", "instagram.com", "messenger.com",
           "wa.me", "whatsapp.com", "m.me", "play.google.com", "apps.apple.com")


def limpar_link(url):
    """Desembrulha links l.facebook.com/l.php?u=..., tira www e parametros de rastreio."""
    p = urlparse(url)
    if p.netloc.endswith("facebook.com") and p.path.startswith("/l.php"):
        alvo = parse_qs(p.query).get("u")
        if alvo:
            return limpar_link(alvo[0])
    q = [(k, v) for k, v in parse_qs(p.query).items() if not k.lower().startswith(("utm", "fbclid", "gclid"))]
    host = p.netloc[4:] if p.netloc.lower().startswith("www.") else p.netloc
    base = f"{p.scheme}://{host}{p.path}".rstrip("/") if p.path != "/" else f"{p.scheme}://{host}"
    return base + ("?" + "&".join(f"{k}={v[0]}" for k, v in q) if q else "")


def dominio(url):
    host = urlparse(url).netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def eh_pagina_de_vendas(url):
    d = dominio(url)
    return bool(d) and not any(d == i or d.endswith("." + i) for i in IGNORAR)


# ------------------------------------------------------------ agrupar

def agrupar(anuncios, total_na_tela=None):
    """Junta os anuncios de UM anunciante em uma 'oferta'."""
    ativos = [a for a in anuncios if a.get("ativo") is not False]
    agora = time.time()
    idades = [(agora - a["inicio"]) / 86400 for a in ativos if a.get("inicio")]

    paginas = Counter()
    for a in ativos:
        for l in a["links"]:
            l = limpar_link(l)
            if eh_pagina_de_vendas(l):
                paginas[l] += 1

    por_dominio = Counter()
    for l, n in paginas.items():
        por_dominio[dominio(l)] += n

    primeiro = a0 = ativos[0] if ativos else {}
    return {
        "page_id": a0.get("page_id"),
        "nome": a0.get("page_name") or "(sem nome)",
        # a contagem da tela da Meta e a mais fiel; se faltar, usamos o que lemos
        "ativos": total_na_tela or len(ativos),
        "lidos": len(ativos),
        "idade_max_dias": round(max(idades)) if idades else 0,
        "idade_mediana_dias": round(statistics.median(idades)) if idades else 0,
        "primeiro_anuncio": time.strftime("%Y-%m-%d", time.gmtime(agora - max(idades) * 86400)) if idades else None,
        "variacoes": len({re.sub(r"\W+", " ", a["texto"].lower())[:120] for a in ativos if a["texto"]}),
        "paginas": [{"url": u, "anuncios": n} for u, n in paginas.most_common()],
        "dominios": dict(por_dominio.most_common()),
        "exemplo_texto": next((a["texto"] for a in ativos if a["texto"]), ""),
        "formatos": dict(Counter(a.get("formato") for a in ativos if a.get("formato"))),
    }


# ------------------------------------------------------------ pontuar

def pontuar(oferta, cfg):
    """Nota de 0 a 100: quantidade, tempo no ar e variacoes de criativo."""
    p = cfg["pesos"]
    q = min(1, math.log1p(oferta["ativos"]) / math.log1p(cfg["quantidade_maxima"]))
    # tempo no ar: o anuncio mais antigo pesa mais, a mediana confirma que nao e so um
    idade = 0.6 * oferta["idade_max_dias"] + 0.4 * oferta["idade_mediana_dias"]
    t = min(1, idade / cfg["dias_maximos"])
    v = min(1, oferta["variacoes"] / cfg["variacoes_maximas"])
    nota = 100 * (p["quantidade"] * q + p["tempo_no_ar"] * t + p["variacoes"] * v)
    oferta["nota"] = round(nota)
    return oferta


# ------------------------------------------------------ pagina de vendas

_PRECO = re.compile(r"(?:US\$|\$|USD\s?)\s?\d{1,4}(?:[.,]\d{2})?|\d{1,4}(?:[.,]\d{2})?\s?(?:USD|dollars)", re.I)


def ler_pagina_de_vendas(url, timeout=15):
    """Baixa a pagina e extrai produto, promessa, tipo, preco e formato."""
    ficha = {"url": url, "ok": False}
    try:
        r = requests.get(url, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"})
        r.raise_for_status()
    except Exception as e:
        ficha["erro"] = str(e)[:120]
        return ficha

    sopa = BeautifulSoup(r.text, "html.parser")
    meta = lambda n: (sopa.find("meta", attrs={"property": n}) or sopa.find("meta", attrs={"name": n}) or {}).get("content", "")
    h1 = sopa.find("h1")
    texto = sopa.get_text(" ", strip=True)
    baixo = (texto + " " + r.text[:200000]).lower()

    precos = _PRECO.findall(texto)
    if any(k in baixo for k in ("add to cart", "free shipping", "shop now", "buy now") ) and "/products/" in r.url:
        tipo = "produto fisico"
    elif any(k in baixo for k in ("per month", "/month", "/mo", "subscription", "free trial", "cancel anytime")):
        tipo = "assinatura ou app"
    elif any(k in baixo for k in ("course", "lesson", "module", "masterclass", "training program", "ebook", "guide")):
        tipo = "curso ou infoproduto"
    else:
        tipo = "nao identificado"

    ficha.update({
        "ok": True,
        "titulo": (meta("og:title") or (sopa.title.string if sopa.title else "") or "").strip()[:120],
        "promessa": (h1.get_text(" ", strip=True) if h1 else meta("og:description"))[:200],
        "tipo": tipo,
        "preco": precos[0] if precos else None,
        "vsl": any(k in baixo for k in ("wistia", "vturb", "vsl", "<video", "watch this video", "watch the video")),
        "quiz": any(k in baixo for k in ("quiz", "take the test", "answer a few questions", "step 1 of")),
        "advertorial": any(k in baixo for k in ("sponsored", "advertorial", "as seen on", "reporter", "breaking")),
    })
    return ficha


# ---------------------------------------------------------------- resumo

def resumo_pt(oferta, ficha):
    """Resumo de 3 linhas em portugues, montado a partir dos dados."""
    if not ficha or not ficha.get("ok"):
        return ("Nao consegui abrir a pagina de vendas.\n"
                f"Texto de um dos anuncios: {oferta['exemplo_texto'][:140]}\n"
                "Abra a biblioteca para ver os criativos.")
    formatos = [n for n, v in (("VSL", ficha["vsl"]), ("quiz", ficha["quiz"]), ("advertorial", ficha["advertorial"])) if v]
    preco = f", preco visto: {ficha['preco']}" if ficha["preco"] else ""
    return (f"Tipo: {ficha['tipo']}{preco}.\n"
            f"Promessa da pagina (em ingles): {ficha['promessa'] or ficha['titulo']}\n"
            f"Formato da pagina: {', '.join(formatos) if formatos else 'pagina direta, sem VSL, quiz ou advertorial detectado'}.")
