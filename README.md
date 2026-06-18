# Dossiê CVM — Recompra & CVM 44

Dashboard por empresa com **programas de recompra** (buyback) e **movimentações
CVM 44** (Resolução CVM 44, art. 11 — VLMO: compras/vendas de controlador,
administradores e tesouraria). Começa com a **RDOR3 (Rede D'Or)**; expandir é
adicionar a empresa em `companies.py` e fatiar seus dados em `data/`.

Os dados são reaproveitados do projeto `cvm-insider-monitor` (já processados),
então o build **não acessa a rede** — só renderiza e publica.

```
python build.py      # -> output/index.html
```

Publicado via GitHub Pages (build pelo Actions).
