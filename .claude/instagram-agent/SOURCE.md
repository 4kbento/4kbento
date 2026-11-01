# instagram-agent-skill (instalado no projeto)

- Origem: https://github.com/Jakeschincariol/instagram-agent-skill
- Commit: `d03c56bb598be770c60b201f94237e5d1a4268a6`
- Licença: MIT (veja `LICENSE` nesta pasta)

As 13 skills estão em `.claude/skills/ig-*` e são carregadas pelo Claude Code
quando ele é aberto neste repositório.

## Primeiro passo: o voice.md

Todas as skills leem `~/.claude/instagram/voice.md`. Copie o modelo e preencha:

```bash
mkdir -p ~/.claude/instagram
cp .claude/instagram-agent/voice.md ~/.claude/instagram/voice.md
```

Ou mande ao Claude três reels/legendas suas e peça "write my voice.md from these".

## Atualizar

```bash
git clone --depth 1 https://github.com/Jakeschincariol/instagram-agent-skill /tmp/igs
rm -rf .claude/skills/ig-* && cp -r /tmp/igs/skills/ig-* .claude/skills/
```
