# Minerador de ofertas (MVP)

Varre a Biblioteca de Anuncios da Meta, agrupa por anunciante e mostra as ofertas
com mais anuncios ativos e mais tempo no ar.

## Instalar (no seu computador)

    cd minerador
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    playwright install chromium

## Rodar

    python main.py                  # varredura completa, imprime o top 10
    python main.py --palavra "typing course" --depurar   # teste pequeno + arquivos de diagnostico
    python main.py --arquivo tests/fixture_meta_sintetico.json --sem-paginas   # teste offline

O resultado tambem fica salvo em `resultados/`.

## O que cada oferta mostra

Numero de anuncios ativos, dias no ar (mais antigo e mediana), variacoes de criativo,
todas as paginas de vendas que o anunciante roda (com quantos anuncios em cada),
link da biblioteca filtrado no anunciante e um resumo de 3 linhas em portugues.

## Ajustar

Tudo em `config.yaml`: palavras-chave por nicho, pais (`ALL` = mundo), minimo de anuncios,
pesos da nota (quantidade e tempo no ar valem mais) e pausas do navegador.

## Limites conhecidos

- A API oficial da Meta nao traz anuncios comerciais fora da UE, por isso usamos o navegador.
- A Meta pode bloquear ou mudar a pagina. Se nada for lido, rode com `--depurar` e olhe `depuracao/`.
- IP de datacenter costuma ser bloqueado; no seu computador de casa deve funcionar melhor.
- O resumo e montado por regras, sem IA paga. O idioma e filtrado por heuristica de texto.
