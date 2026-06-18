"""
Dossiê CVM por empresa — v1: RDOR3.

Foco: programas de recompra (buyback) + movimentações CVM 44 (Res. CVM 44,
art. 11 — VLMO: compras/vendas de administradores, controlador e tesouraria).

Lê os dados já processados (data/recompra.parquet, data/cvm44.parquet — fatias
geradas a partir do cvm-insider-monitor) e renderiza um HTML autossuficiente.
Não acessa a rede: o deploy é só renderizar + publicar. Parametrizado por ticker.

  python build.py            -> output/index.html (empresa em foco)
"""
from __future__ import annotations

import datetime as dt
import math
from pathlib import Path

import pandas as pd

import companies
import theme

BASE = Path(__file__).resolve().parent
OUT = BASE / "output"
OUT.mkdir(exist_ok=True)
_MES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


# ---------------------------------------------------------------------------
# formatadores — formato internacional 1,000.00 (vírgula milhar, ponto decimal)
# ---------------------------------------------------------------------------
def _na(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def _qtd(v) -> str:
    return "—" if _na(v) else f"{abs(v):,.0f}"


def _brl(v, signed=False) -> str:
    if _na(v):
        return "—"
    a = abs(v)
    if a >= 1e9: s = f"R$ {v/1e9:,.2f} bi"
    elif a >= 1e6: s = f"R$ {v/1e6:,.1f} mi"
    elif a >= 1e3: s = f"R$ {v/1e3:,.0f} mil"
    else: s = f"R$ {v:,.0f}"
    return ("+" + s) if (signed and v > 0) else s


def _preco(v) -> str:
    return "—" if _na(v) else f"R$ {v:,.2f}"


def _data(s) -> str:                       # "2024-06-11" -> "11/06/2024"
    s = str(s or "")
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if len(s) >= 10 else "—"


def _mes(ym) -> str:                        # "2026-05" -> "mai/26"
    try:
        return f"{_MES[int(ym[5:7]) - 1]}/{ym[2:4]}"
    except Exception:
        return ym


def _org(o) -> str:
    return str(o or "—").replace(" ou Vinculado", "").strip() or "—"


# ---------------------------------------------------------------------------
# gráfico de barras mensal (fluxo líquido CVM 44), SVG inline vertical
# ---------------------------------------------------------------------------
def _monthly_svg(months, values) -> str:
    """Barras mensais de fluxo líquido — adapta-se à série inteira (sem janela):
    em séries longas afina as barras, rotula esparsamente e marca a virada de ano."""
    n = len(months)
    if n == 0:
        return '<div class="lead">Sem movimentações no período.</div>'
    W, H = 720, 240
    padL, padR, padT, padB = 8, 8, 20, 30
    plotW, plotH = W - padL - padR, H - padT - padB
    y0 = padT + plotH / 2
    maxabs = max((abs(v) for v in values), default=1) or 1
    sc = (plotH / 2 - 12) / maxabs
    slot = plotW / n
    bw = min(40, slot * 0.62)
    show_vals = n <= 16
    p = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Fluxo líquido mensal CVM 44">']
    p.append(f'<line class="svg-zero" x1="{padL}" y1="{y0:.1f}" x2="{W-padR}" y2="{y0:.1f}"/>')
    prev_year = None
    for i, (m, v) in enumerate(zip(months, values)):
        xc = padL + slot * i + slot / 2
        h = abs(v) * sc
        y = y0 - h if v >= 0 else y0
        color = "var(--buy)" if v >= 0 else "var(--sell)"
        p.append(f'<rect x="{xc-bw/2:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{max(h,0.6):.1f}" rx="2" fill="{color}"/>')
        if show_vals:
            vy = (y - 5) if v >= 0 else (y + h + 12)
            p.append(f'<text class="svg-val" x="{xc:.1f}" y="{vy:.1f}" text-anchor="middle">{("+" if v>0 else "")}{v:,.0f}</text>')
        yr = m[:4]
        if yr != prev_year:                       # rótulo só na virada de ano
            p.append(f'<line class="svg-zero" x1="{xc-slot/2:.1f}" y1="{padT}" x2="{xc-slot/2:.1f}" y2="{H-padB}" opacity="0.35"/>')
            p.append(f'<text class="svg-axis" x="{xc-slot/2+3:.1f}" y="{H-10:.1f}">{yr}</text>')
            prev_year = yr
    p.append(f'<text class="svg-bm" x="{padL}" y="{padT-7:.1f}">compra líq. (+) · R$ mi</text>')
    p.append("</svg>")
    return "".join(p)


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------
def _recompra_section(rec: pd.DataFrame) -> tuple[str, dict]:
    rec = rec.copy()
    rec["_d"] = rec.get("data_aprovacao")
    rec["_d"] = rec["_d"].fillna(rec.get("data_entrega")).fillna("").astype(str)

    rows = []
    seen = set()
    n_prog = 0
    total_exec = 0.0

    # Classifica cada doc para exibição. A quantidade EXECUTADA costuma estar no
    # comunicado de ENCERRAMENTO ("foram adquiridas X ações"), não num tipo
    # 'execucao' — então qualquer doc com qtd_executada vira "Recompra executada".
    ev = []
    for _, r in rec.iterrows():
        tipo = r["tipo"]
        if tipo in ("opa", "debenture"):
            continue  # oferta de aquisição / dívida — não é recompra de ações
        exec_q = r.get("qtd_executada")
        has_exec = not _na(exec_q) and exec_q > 0
        if tipo == "aprovacao":
            qty, label, cls = r.get("qtd_autorizada"), "Programa aprovado", "b-aprovacao"
        elif has_exec:
            qty, label, cls = exec_q, "Recompra executada", "b-execucao"
        elif tipo == "encerramento":
            qty, label, cls = None, "Encerramento", "b-encerramento"
        elif tipo == "cancelamento":
            qty, label, cls = None, "Cancelamento", "b-cancelamento"
        else:
            qty, label, cls = None, "Comunicado", "b-aprovacao"
        key = (label, None if _na(qty) else int(qty), r["_d"][:7])
        if key in seen:
            continue
        seen.add(key)
        ev.append((r, label, cls, qty))

    for r, label, cls, qty in sorted(ev, key=lambda e: e[0]["_d"], reverse=True):
        if label == "Programa aprovado" and not _na(qty):
            n_prog += 1
        if label == "Recompra executada" and not _na(qty):
            total_exec += qty
        pct = f'{r["pct_float"]:.2f}%' if not _na(r.get("pct_float")) else "—"
        prazo = f'{int(r["prazo_meses"])}m' if not _na(r.get("prazo_meses")) else "—"
        pm = r.get("preco_medio_exec")
        extra = f' · {_preco(pm)} méd' if (label == "Recompra executada" and not _na(pm)) else ""
        link = r.get("link") or ""
        doc = f'<a href="{link}" target="_blank" rel="noopener">↗</a>' if link else "—"
        rows.append(
            f'<tr><td class="muted">{_data(r["_d"])}</td>'
            f'<td><span class="badge {cls}">{label}</span></td>'
            f'<td class="num strong">{_qtd(qty)} <span class="faint">ações</span>{extra}</td>'
            f'<td class="num hide-sm">{pct}</td>'
            f'<td class="ctr hide-sm">{prazo}</td>'
            f'<td class="ctr">{doc}</td></tr>')

    body = f"""
  <h2>Recompra de ações <span class="h-meta">programas &amp; execução</span></h2>
  <p class="lead">Programas de recompra autorizados pelo Conselho e o quanto foi
    <b>efetivamente recomprado</b> (dos comunicados de conclusão). Quantidade = limite
    autorizado (programa) ou ações de fato adquiridas (execução).</p>
  <div class="card" style="margin-top:14px">
    <table class="tbl"><thead><tr><th>Data</th><th>Evento</th><th class="num">Quantidade</th>
      <th class="num hide-sm">% float</th><th class="ctr hide-sm">Prazo</th><th class="ctr">Doc</th></tr></thead>
      <tbody>{''.join(rows) or '<tr><td colspan=6 class=muted>Sem eventos de recompra.</td></tr>'}</tbody></table>
  </div>"""
    return body, {"n_prog": n_prog, "total_exec": total_exec}


def _cvm44_section(v: pd.DataFrame) -> tuple[str, dict]:
    v = v.copy()
    sign = v["direcao"].map({"compra": 1, "venda": -1}).fillna(0)
    v["_sv"] = v["volume"].fillna(0) * sign
    net = float(v["_sv"].sum())
    vol = float(v["volume"].fillna(0).sum())

    months = sorted(v["data_ref"].astype(str).str[:7].unique())
    by_m = v.assign(_m=v["data_ref"].astype(str).str[:7]).groupby("_m")["_sv"].sum()
    chart = _monthly_svg(months, [round(by_m.get(m, 0) / 1e6, 1) for m in months])

    rows = []
    vv = v.copy()
    vv["_dm"] = vv.get("data_mov").fillna(vv["data_ref"]).astype(str)
    for _, r in vv.sort_values("_dm", ascending=False).iterrows():
        d = r["direcao"]
        cls = "b-compra" if d == "compra" else "b-venda"
        rows.append(
            f'<tr><td class="muted">{_data(r["_dm"])}</td>'
            f'<td>{_org(r.get("orgao"))}</td>'
            f'<td><span class="badge {cls}">{"COMPRA" if d=="compra" else "VENDA"}</span></td>'
            f'<td class="num">{_qtd(r.get("quantidade"))}</td>'
            f'<td class="num hide-sm">{_preco(r.get("preco"))}</td>'
            f'<td class="num strong">{_brl(r.get("volume"))}</td></tr>')

    by_org = v.assign(_o=v["orgao"].map(_org)).groupby("_o")["_sv"].sum().sort_values(key=abs, ascending=False)
    org_line = " · ".join(f'{o}: <b>{_brl(s, True)}</b>' for o, s in by_org.items())

    body = f"""
  <h2>Movimentações CVM 44 <span class="h-meta">Res. 44 art. 11 · VLMO · {_mes(months[0])}–{_mes(months[-1])}</span></h2>
  <p class="lead">Compras e vendas declaradas por <b>controlador, administradores e tesouraria</b>
    (Resolução CVM 44, art. 11), desde o IPO. <b>{len(v)}</b> movimentos · fluxo líquido por mês e o detalhe pregão a pregão. {org_line}</p>
  <div class="card chart-box" style="margin-top:14px">{chart}</div>
  <div class="card" style="margin-top:16px">
    <div class="scroll"><table class="tbl"><thead><tr><th>Negócio</th><th>Órgão</th><th>Operação</th>
      <th class="num">Qtde</th><th class="num hide-sm">Preço</th><th class="num">Valor</th></tr></thead>
      <tbody>{''.join(rows) or '<tr><td colspan=6 class=muted>Sem movimentações.</td></tr>'}</tbody></table></div>
  </div>"""
    return body, {"net": net, "vol": vol, "n": len(v)}


def render(ticker: str) -> str:
    info = companies.COMPANIES[ticker]
    rec = pd.read_parquet(BASE / "data" / "recompra.parquet")
    cvm = pd.read_parquet(BASE / "data" / "cvm44.parquet")
    rec = rec[rec["ticker"] == ticker]
    cvm = cvm[cvm["ticker"] == ticker]

    rec_body, rk = _recompra_section(rec)
    cvm_body, ck = _cvm44_section(cvm)
    gerado = dt.datetime.now().strftime("%d/%m/%Y %H:%M")

    kpis = f"""
  <section class="kpis">
    <div class="kpi"><div class="lbl">Programas de recompra</div><div class="val">{rk['n_prog']}</div><div class="foot">aprovados</div></div>
    <div class="kpi"><div class="lbl">Ações recompradas</div><div class="val acc">{_qtd(rk['total_exec'])}</div><div class="foot">executado · concluídos</div></div>
    <div class="kpi"><div class="lbl">Fluxo CVM 44 líquido</div><div class="val {'pos' if ck['net']>=0 else 'neg'}">{_brl(ck['net'],True)}</div><div class="foot">compras − vendas</div></div>
    <div class="kpi"><div class="lbl">Volume CVM 44</div><div class="val">{_brl(ck['vol'])}</div><div class="foot">{ck['n']} movimentos</div></div>
  </section>"""

    return f"""<!doctype html><html lang="pt-BR">{theme.head(f"{ticker} · Recompra & CVM 44")}
<body><div class="wrap">
  <header>
    <div class="kicker">Dossiê CVM · Recompra &amp; Insiders</div>
    <h1>{info['nome']} · <span class="tk">{ticker}</span></h1>
    <div class="sub"><span>{info['setor']}</span>·
      <span>CNPJ <b>{info['cnpj']}</b></span>·
      <span>Gerado em <b>{gerado}</b></span><span class="chip">v1 · {ticker}</span></div>
  </header>
  {kpis}
  {rec_body}
  {cvm_body}
  <footer><span>dossiê CVM · recompra + CVM 44 (art. 11)</span><span>fonte: comunicados IPE &amp; VLMO da CVM · {gerado}</span></footer>
</div></body></html>"""


def main():
    html = render(companies.FOCO)
    out = OUT / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"[dossie] {out}  ({companies.FOCO})")


if __name__ == "__main__":
    main()
