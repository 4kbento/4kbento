"""Orquestra uma varredura manual: coleta, agrupa, pontua e imprime o top.

Uso:
  python main.py                    varredura completa (abre o navegador)
  python main.py --depurar          grava tela e respostas em ./depuracao
  python main.py --arquivo X.json   usa respostas ja salvas, sem acessar a Meta
"""
import argparse
import json
import os
import random
import time
from collections import Counter

import yaml

import analisador as an
import coletor as co


def carregar_config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def descobrir(cfg, c, palavras):
    """Passo 1: busca cada palavra e conta quantos anuncios cada anunciante tem."""
    contagem, nomes, nicho_de = Counter(), {}, {}
    for nicho, lista in cfg["nichos"].items():
        for palavra in lista:
            if palavras and palavra not in palavras:
                continue
            print(f"  buscando '{palavra}' ({nicho})...")
            for a in c.buscar(palavra):
                if a["page_id"]:
                    contagem[a["page_id"]] += 1
                    nomes[a["page_id"]] = a["page_name"]
                    nicho_de.setdefault(a["page_id"], nicho)
    return contagem, nomes, nicho_de


def imprimir(ofertas, cfg):
    print("\n" + "=" * 70)
    print(f"TOP {len(ofertas)} OFERTAS")
    print("=" * 70)
    for i, o in enumerate(ofertas, 1):
        print(f"\n#{i}  {o['nome']}   (nota {o['nota']}/100)")
        print(f"Anuncios ativos: {o['ativos']}")
        print(f"Rodando ha: {o['idade_max_dias']} dias o mais antigo, "
              f"mediana {o['idade_mediana_dias']} dias | variacoes de criativo: {o['variacoes']}")
        print(f"Nicho: {o.get('nicho', '-')} | Primeiro anuncio visto: {o['primeiro_anuncio']}")
        if o["paginas"]:
            print("Paginas de vendas:")
            for p in o["paginas"][:5]:
                print(f"  - {p['url']}  ({p['anuncios']} anuncios)")
        else:
            print("Paginas de vendas: nenhuma encontrada")
        print(f"Biblioteca de anuncios: {co.link_anunciante(o['page_id'], cfg.get('pais', 'ALL'))}")
        if o.get("resumo"):
            print("Resumo:\n  " + o["resumo"].replace("\n", "\n  "))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--depurar", action="store_true")
    ap.add_argument("--arquivo", help="JSON bruto da Meta, para testar sem acessar o site")
    ap.add_argument("--palavra", action="append", help="busca so esta palavra (pode repetir)")
    ap.add_argument("--sem-paginas", action="store_true", help="nao abre as paginas de vendas")
    args = ap.parse_args()
    cfg = carregar_config()
    ofertas = []

    if args.arquivo:
        # Modo teste: le anuncios de um arquivo e agrupa por anunciante
        with open(args.arquivo) as f:
            anuncios = co.extrair_anuncios(f.read())
        por_pagina = {}
        for a in anuncios:
            por_pagina.setdefault(a["page_id"], []).append(a)
        for pid, lista in por_pagina.items():
            lista = [a for a in lista if co.eh_ingles(a["texto"]) is not False]
            if lista:
                ofertas.append(an.agrupar(lista))
    else:
        t0 = time.time()
        with co.Coletor(cfg, depurar=args.depurar) as c:
            print("Passo 1: descobrindo anunciantes...")
            contagem, nomes, nicho_de = descobrir(cfg, c, args.palavra)
            if not contagem:
                print("\nNenhum anuncio lido. A Meta pode ter bloqueado ou mudado a pagina.\n"
                      "Rode com --depurar e olhe a pasta ./depuracao (screenshot e respostas).")
                return
            candidatos = [p for p, _ in contagem.most_common(cfg["candidatos_por_varredura"])]
            print(f"\nPasso 2: aprofundando {len(candidatos)} anunciantes...")
            for pid in candidatos:
                print(f"  {nomes[pid]} ({pid})")
                anuncios, total = c.anunciante(pid)
                if anuncios:
                    o = an.agrupar(anuncios, total)
                    o["nicho"] = nicho_de[pid]
                    ofertas.append(o)
                time.sleep(random.uniform(cfg["navegador"]["pausa_min"], cfg["navegador"]["pausa_max"]))
        print(f"\nColeta levou {round(time.time() - t0)}s.")

    ofertas = [an.pontuar(o, cfg) for o in ofertas if o["ativos"] >= cfg["minimo_anuncios"]]
    ofertas.sort(key=lambda o: o["nota"], reverse=True)
    ofertas = ofertas[:cfg["top"]]

    if not args.sem_paginas:
        print("\nPasso 3: lendo paginas de vendas...")
        for o in ofertas:
            ficha = an.ler_pagina_de_vendas(o["paginas"][0]["url"]) if o["paginas"] else None
            o["ficha"] = ficha
            o["resumo"] = an.resumo_pt(o, ficha)

    imprimir(ofertas, cfg)
    os.makedirs("resultados", exist_ok=True)
    saida = time.strftime("resultados/ofertas_%Y%m%d_%H%M.json")
    with open(saida, "w") as f:
        json.dump(ofertas, f, indent=1, ensure_ascii=False)
    print(f"\nSalvo em {saida}")


if __name__ == "__main__":
    main()
