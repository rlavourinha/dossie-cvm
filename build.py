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
import unicodedata
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


def _ascii(s) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()


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
def _date_obj(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def _daily_buys(ticker: str) -> list[tuple]:
    """Compras diárias da tesouraria (execução real da recompra), validadas por
    saldo. (data_obj, quantidade, preco). Vazio se o arquivo não existir."""
    f = BASE / "data" / "recompra_diaria.parquet"
    if not f.exists():
        return []
    d = pd.read_parquet(f)
    d = d[(d["ticker"] == ticker) & (d["operacao"] == "compra")]
    out = []
    for _, r in d.iterrows():
        do = _date_obj(r["data"])
        if do is not None:
            out.append((do, float(r["quantidade"]), float(r.get("preco")) if not _na(r.get("preco")) else None))
    return sorted(out)


def _programs(rec: pd.DataFrame, ticker: str) -> list[dict]:
    """Programas de recompra (início, prazo final, autorizado, executado).
    A execução é reportada num doc posterior; cada programa fica com a execução
    cujo registro cai entre o seu início e o início do programa seguinte."""
    rec = rec.copy()
    rec["_d"] = rec.get("data_aprovacao")
    rec["_d"] = rec["_d"].fillna(rec.get("data_entrega")).fillna("").astype(str)
    apr = rec[rec["tipo"] == "aprovacao"].copy()
    apr["_k"] = apr.apply(lambda r: f'{None if _na(r.get("qtd_autorizada")) else int(r["qtd_autorizada"])}|{r["_d"][:7]}', axis=1)
    apr = apr.sort_values("_d").drop_duplicates("_k")
    progs = []
    for _, r in apr.iterrows():
        start = _date_obj(r["_d"])
        if start is None or _na(r.get("qtd_autorizada")):
            continue
        prazo = int(r["prazo_meses"]) if not _na(r.get("prazo_meses")) else 12
        progs.append(dict(start=start, deadline=start + dt.timedelta(days=round(prazo * 30.44)),
                          auth=float(r["qtd_autorizada"]), prazo=prazo, exec=None, exec_date=None,
                          valor_auth=(None if _na(r.get("valor_autorizado")) else float(r["valor_autorizado"])),
                          exec_value=None))
    progs.sort(key=lambda p: p["start"])
    # encerramento REAL: programas são sequenciais (sem sobreposição); cada um é
    # encerrado quando o próximo abre. O último em aberto não tem data de fim.
    for i, p in enumerate(progs):
        p["end"] = progs[i + 1]["start"] if i + 1 < len(progs) else None
    # execuções (dedup por valor+mês); carrega também o valor (R$) executado
    ex = rec[rec.get("qtd_executada").fillna(0) > 0].copy()
    seen, execs = set(), []
    for _, e in ex.sort_values("_d").iterrows():
        d, q = _date_obj(e["_d"]), float(e["qtd_executada"])
        v = None if _na(e.get("valor_executado")) else float(e["valor_executado"])
        k = (round(q), str(e["_d"])[:7])
        if d is None or k in seen:
            continue
        seen.add(k); execs.append((d, q, v))
    for i, p in enumerate(progs):
        hi = progs[i + 1]["start"] if i + 1 < len(progs) else dt.date(2100, 1, 1)
        cand = [(d, q, v) for d, q, v in execs if p["start"] < d <= hi]
        if cand:
            d, q, v = max(cand, key=lambda t: t[0])
            p["exec_date"], p["exec"], p["exec_value"] = d, q, v
    # anexa as compras DIÁRIAS (execução real) a cada programa: a compra cai no
    # programa ativo na sua data (último iniciado antes dela).
    daily = _daily_buys(ticker)
    for d, q, pr in daily:
        ativo = [p for p in progs if p["start"] <= d < (progs[progs.index(p) + 1]["start"] if progs.index(p) + 1 < len(progs) else dt.date(2100, 1, 1))]
        if ativo:
            ativo[-1].setdefault("buys", []).append((d, q, pr))
    for p in progs:
        b = sorted(p.get("buys", []))
        cum, acc = [], 0.0
        for d, q, pr in b:
            acc += q
            cum.append((d, acc))
        p["cum"] = cum
        p["exec_real"] = acc if cum else None
        vol = sum(q * pr for d, q, pr in b if pr)
        qty = sum(q for d, q, pr in b if pr)
        p["preco_med"] = vol / qty if qty else None
    for p in progs:
        p["reason"] = _closure_reason(p)
    return progs


def _closure_reason(p: dict):
    """Por que o programa encerrou. Um programa só acaba por uma de quatro vias:
    limite de ações, limite de valor (R$), fim do prazo, ou decisão antecipada do
    Conselho (nenhum teto atingido). Retorna (rótulo, detalhe, classe) ou None se
    ainda em andamento."""
    if not p.get("end"):
        return None
    sh = (p.get("exec") or 0) / p["auth"] if p.get("auth") else 0
    val = (p.get("exec_value") or 0) / p["valor_auth"] if p.get("valor_auth") else 0
    if sh >= 0.995:
        return ("limite de ações", f"executou {_qtd(p['exec'])} de {_qtd(p['auth'])} (100%)", "lim")
    if val >= 0.995:
        return ("limite de valor", f"gastou R$ {p['exec_value']/1e6:,.0f} mi de R$ {p['valor_auth']/1e6:,.0f} mi", "lim")
    if p["end"] >= p["deadline"] - dt.timedelta(days=7):
        return ("fim do prazo", f"venceu em {_data(p['deadline'].isoformat())} ({p['prazo']} meses)", "prazo")
    return ("decisão do Conselho", f"encerrado antes do prazo (em {_data(p['end'].isoformat())}, "
            f"a {sh*100:.0f}% das ações e {val*100:.0f}% do valor)", "disc")


def _prog_panel(p: dict, idx: int) -> str:
    W, H = 720, 150
    padL, padR, padT, padB = 46, 120, 16, 30
    ybot, ytop = H - padB, padT
    span = max((p["deadline"] - p["start"]).days, 1)
    x = lambda d: padL + (d - p["start"]).days / span * (W - padL - padR)
    y = lambda q: ybot - (q / p["auth"]) * (ybot - ytop) if p["auth"] else ybot
    s = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Execução do programa {idx}">']
    # eixo base
    s.append(f'<line class="svg-zero" x1="{padL}" y1="{ybot}" x2="{x(p["deadline"]):.1f}" y2="{ybot}"/>')
    # execução observada DIA A DIA (tesouraria) — pode estar incompleta no mês corrente
    cum = p.get("cum")
    daily_end, xe = None, None
    if cum:
        pts = [(padL, ybot)] + [(x(d), y(c)) for d, c in cum]
        xe, ye = pts[-1]
        daily_end = cum[-1][1]
        poly = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
        s.append(f'<polygon points="{padL},{ybot} {poly} {xe:.1f},{ybot}" fill="rgba(70,185,138,.16)"/>')
        s.append(f'<polyline points="{poly}" fill="none" stroke="var(--buy)" stroke-width="2"/>')
        for px, py in pts[1:]:
            s.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2.2" fill="var(--buy)"/>')
    # EXECUTADO FINAL (oficial do encerramento = a verdade); o diário é complementar.
    # Sem doc de execução ainda (programa em aberto), cai pro diário acumulado.
    final = p.get("exec") or daily_end
    if final:
        yo = y(final); pct = 100 * final / p["auth"] if p["auth"] else 0
        s.append(f'<line x1="{padL}" y1="{yo:.1f}" x2="{x(p["deadline"]):.1f}" y2="{yo:.1f}" stroke="var(--buy)" stroke-width="1.6"/>')
        s.append(f'<text class="svg-tkr" x="{x(p["deadline"])+6:.1f}" y="{yo+4:.1f}" fill="var(--buy)">{_qtd(final)} · {pct:.0f}%</text>')
        # diário ainda parcial (faltam formulários do mês corrente)
        if daily_end and final - daily_end > 0.02 * p["auth"] and xe is not None:
            s.append(f'<text class="svg-val" x="{xe+6:.1f}" y="{y(daily_end)+4:.1f}" fill="var(--muted)">diário {_qtd(daily_end)} · parcial</text>')
    # linha do MÁXIMO autorizado (teto) — o programa NÃO precisa chegar nela
    s.append(f'<line x1="{padL}" y1="{ytop:.1f}" x2="{x(p["deadline"]):.1f}" y2="{ytop:.1f}" stroke="var(--gold)" stroke-width="1.3" stroke-dasharray="5 4"/>')
    s.append(f'<text class="svg-val" x="{x(p["deadline"])+6:.1f}" y="{ytop+4:.1f}" fill="var(--gold)">máx {_qtd(p["auth"])}</text>')
    # vertical da VALIDADE nominal (vence aqui se não for encerrado antes)
    s.append(f'<line x1="{x(p["deadline"]):.1f}" y1="{ytop-6:.1f}" x2="{x(p["deadline"]):.1f}" y2="{ybot+4:.1f}" stroke="var(--sell)" stroke-width="1.2" stroke-dasharray="4 4"/>')
    s.append(f'<text class="svg-axis" x="{x(p["deadline"]):.1f}" y="{ybot+18:.1f}" text-anchor="middle" fill="var(--sell)">validade {_data(p["deadline"].isoformat())}</text>')
    # marcador do ENCERRAMENTO REAL, quando o programa acabou antes da validade
    end = p.get("end")
    if end and end < p["deadline"]:
        xc = x(end)
        s.append(f'<line x1="{xc:.1f}" y1="{ytop-6:.1f}" x2="{xc:.1f}" y2="{ybot+4:.1f}" stroke="var(--accent)" stroke-width="1.4"/>')
        s.append(f'<text class="svg-axis" x="{xc:.1f}" y="{ytop-9:.1f}" text-anchor="middle" fill="var(--accent)">encerrado {_data(end.isoformat())}</text>')
    # eixo y: 0 e máx
    s.append(f'<text class="svg-axis" x="{padL-7}" y="{ybot+4:.1f}" text-anchor="end">0</text>')
    s.append(f'<text class="svg-axis" x="{padL-7}" y="{ytop+4:.1f}" text-anchor="end">{p["auth"]/1e6:.0f}M</text>')
    s.append(f'<text class="svg-axis" x="{padL}" y="{ybot+18:.1f}" text-anchor="middle">{_data(p["start"].isoformat())}</text>')
    s.append("</svg>")
    return "".join(s)


def _prog_exec_section(rec: pd.DataFrame, ticker: str) -> str:
    progs = _programs(rec, ticker)
    if not progs:
        return ""
    panels = []
    for i, p in enumerate(progs, 1):
        pm = f' · preço médio {_preco(p["preco_med"])}' if p.get("preco_med") else ""
        final = p.get("exec") or p.get("exec_real")
        if final:
            pct = 100 * final / p["auth"] if p["auth"] else 0
            res = f' · executou <b>{_qtd(final)}</b> de {_qtd(p["auth"])} ({pct:.0f}%)'
        else:
            res = ""
        if p.get("end"):
            fim = f'encerrado {_data(p["end"].isoformat())}'
        else:
            fim = f'em andamento · vence {_data(p["deadline"].isoformat())}'
        rsn = p.get("reason")
        if rsn:
            motivo = (f'<span class="motivo m-{rsn[2]}" title="{rsn[1]}">{rsn[0]}</span>')
        else:
            motivo = '<span class="motivo m-open">em andamento</span>'
        head = (f'<div class="prog-h"><span class="prog-n">Programa {i} {motivo}</span>'
                f'<span class="muted">início {_data(p["start"].isoformat())} · {fim} · '
                f'{p["prazo"]} meses{res}{pm}</span></div>'
                + (f'<div class="motivo-det">Encerramento por <b>{rsn[0]}</b> — {rsn[1]}.</div>' if rsn else ''))
        panels.append(f'<div class="card prog-card">{head}<div class="chart-box">{_prog_panel(p, i)}</div></div>')
    return f"""
  <h2>Execução por programa <span class="h-meta">executado × autorizado · motivo do encerramento</span></h2>
  <p class="lead">Programas são <b>sequenciais</b> (um de cada vez) e <b>não precisam atingir o máximo</b>.
    Cada um encerra por <b>uma de quatro vias</b>: bateu o <b>limite de ações</b>, bateu o <b>limite de valor (R$)</b>,
    chegou ao <b>fim do prazo</b>, ou foi <b>encerrado antecipadamente pelo Conselho</b> (nenhum teto atingido) — o
    badge ao lado de cada programa diz qual foi. A <b>linha verde sólida</b> é o <b>executado oficial</b>; a
    <b>curva verde</b> é a execução diária da tesouraria, que pode estar <b>parcial</b> no mês corrente. A
    <b>linha dourada</b> é o teto de ações, a <b>vertical vermelha</b> a <b>validade</b> nominal e a
    <b>vertical teal</b> o <b>encerramento de fato</b>.</p>
  <div class="prog-grid">{''.join(panels)}</div>"""


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


def _grp(ticker: str, especie) -> str:
    return ticker if _ascii(especie).startswith("aco") else "Outros"


def _cvm44_section(v: pd.DataFrame, ticker: str) -> tuple[str, dict]:
    import json
    v = v.copy()
    sign = v["direcao"].map({"compra": 1, "venda": -1}).fillna(0)
    net = float((v["volume"].fillna(0) * sign).sum())
    vol = float(v["volume"].fillna(0).sum())
    months = sorted(v["data_ref"].astype(str).str[:7].unique())

    v["_dm"] = v.get("data_mov").fillna(v["data_ref"]).astype(str)
    payload = json.dumps([
        dict(dm=r["_dm"][:10], ym=str(r["data_ref"])[:7], org=_org(r.get("orgao")),
             dir=r["direcao"],
             qty=None if _na(r.get("quantidade")) else float(r["quantidade"]),
             preco=None if _na(r.get("preco")) else float(r["preco"]),
             vol=None if _na(r.get("volume")) else float(r["volume"]),
             grp=_grp(ticker, r.get("especie")))
        for _, r in v.iterrows()], ensure_ascii=False)

    n_out = int((v["especie"].map(lambda e: not _ascii(e).startswith("aco"))).sum())
    body = f"""
  <h2>Movimentações CVM 44 <span class="h-meta">Res. 44 art. 11 · VLMO · {_mes(months[0])}–{_mes(months[-1])}</span></h2>
  <p class="lead">Compras e vendas declaradas por <b>controlador, administradores e tesouraria</b>
    (Resolução CVM 44, art. 11), desde o IPO. A VLMO traz a ação <b>{ticker}</b> e
    <b>outros valores mobiliários</b> ({n_out} registros) — use o filtro para separar.</p>
  <div class="filterbar">
    <span class="flbl">Valor mobiliário</span>
    <button class="fbtn active" data-g="todos">Todos</button>
    <button class="fbtn" data-g="{ticker}">{ticker} · ações</button>
    <button class="fbtn" data-g="Outros">Outros</button>
  </div>
  <div class="card chart-box" style="margin-top:12px"><div id="cvm-chart"></div></div>
  <div class="substats" id="cvm-stats"></div>
  <div class="card" style="margin-top:14px">
    <div class="scroll"><table class="tbl"><thead><tr><th>Negócio</th><th>Órgão</th>
      <th class="hide-sm">Papel</th><th>Operação</th><th class="num">Qtde</th>
      <th class="num hide-sm">Preço</th><th class="num">Valor</th></tr></thead>
      <tbody id="cvm-rows"></tbody></table></div>
  </div>
{_CVM_JS.replace("__CVMDATA__", payload)}"""
    return body, {"net": net, "vol": vol, "n": len(v)}


# JS do filtro CVM 44 (string normal, não f-string — recalcula gráfico/stats/tabela)
_CVM_JS = r"""<script>(()=>{
  const DATA = __CVMDATA__;
  const MES=['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'];
  const fmtN=n=>n==null||isNaN(n)?'—':Math.abs(n).toLocaleString('en-US');
  const fmtP=v=>v==null||isNaN(v)?'—':'R$ '+v.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
  const fmtD=s=>s&&s.length>=10?s.slice(8,10)+'/'+s.slice(5,7)+'/'+s.slice(0,4):'—';
  const fmtBRL=(v,sg)=>{if(v==null||isNaN(v))return '—';const a=Math.abs(v);let s=
    a>=1e9?'R$ '+(v/1e9).toFixed(2)+' bi':a>=1e6?'R$ '+(v/1e6).toFixed(1)+' mi':
    a>=1e3?'R$ '+Math.round(v/1e3).toLocaleString('en-US')+' mil':'R$ '+Math.round(v).toLocaleString('en-US');
    return (sg&&v>0?'+':'')+s;};
  function chart(rows){
    const bym={}; rows.forEach(r=>{const s=r.dir==='compra'?1:-1; bym[r.ym]=(bym[r.ym]||0)+s*(r.vol||0);});
    const months=Object.keys(bym).sort(), vals=months.map(m=>bym[m]/1e6), n=months.length;
    if(!n) return '<div class="lead" style="padding:14px">Sem movimentações neste filtro.</div>';
    const W=720,H=240,padL=8,padR=8,padT=20,padB=30,plotW=W-padL-padR,plotH=H-padT-padB,y0=padT+plotH/2;
    const maxabs=Math.max(1,...vals.map(Math.abs)),sc=(plotH/2-12)/maxabs,slot=plotW/n,bw=Math.min(40,slot*0.62),showV=n<=16;
    let s=`<svg viewBox="0 0 ${W} ${H}" role="img"><line class="svg-zero" x1="${padL}" y1="${y0}" x2="${W-padR}" y2="${y0}"/>`,py=null;
    for(let i=0;i<n;i++){const v=vals[i],xc=padL+slot*i+slot/2,h=Math.abs(v)*sc,y=v>=0?y0-h:y0;
      s+=`<rect x="${(xc-bw/2).toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(h,0.6).toFixed(1)}" rx="2" fill="${v>=0?'var(--buy)':'var(--sell)'}"/>`;
      if(showV){const vy=v>=0?y-5:y+h+12;s+=`<text class="svg-val" x="${xc.toFixed(1)}" y="${vy.toFixed(1)}" text-anchor="middle">${(v>0?'+':'')+v.toFixed(0)}</text>`;}
      const yr=months[i].slice(0,4); if(yr!==py){s+=`<line class="svg-zero" x1="${(xc-slot/2).toFixed(1)}" y1="${padT}" x2="${(xc-slot/2).toFixed(1)}" y2="${H-padB}" opacity="0.35"/><text class="svg-axis" x="${(xc-slot/2+3).toFixed(1)}" y="${H-10}">${yr}</text>`;py=yr;}}
    return s+`<text class="svg-bm" x="${padL}" y="${padT-7}">compra líq. (+) · R$ mi</text></svg>`;
  }
  function render(g){
    const rows=g==='todos'?DATA:DATA.filter(r=>r.grp===g);
    document.getElementById('cvm-chart').innerHTML=chart(rows);
    let net=0,vol=0; const byo={};
    rows.forEach(r=>{const s=r.dir==='compra'?1:-1;net+=s*(r.vol||0);vol+=(r.vol||0);byo[r.org]=(byo[r.org]||0)+s*(r.vol||0);});
    const orgs=Object.entries(byo).sort((a,b)=>Math.abs(b[1])-Math.abs(a[1])).map(([o,s])=>o+': <b>'+fmtBRL(s,true)+'</b>').join(' · ');
    document.getElementById('cvm-stats').innerHTML=`<b>${rows.length}</b> movimentos · líquido <b class="${net>=0?'pos':'neg'}">${fmtBRL(net,true)}</b> · volume <b>${fmtBRL(vol)}</b>${orgs?' · '+orgs:''}`;
    document.getElementById('cvm-rows').innerHTML=rows.slice().sort((a,b)=>(b.dm||'').localeCompare(a.dm||'')).map(r=>{
      const cls=r.dir==='compra'?'b-compra':'b-venda';
      return `<tr><td class="muted">${fmtD(r.dm)}</td><td>${r.org}</td><td class="muted hide-sm">${r.grp}</td>`+
        `<td><span class="badge ${cls}">${r.dir==='compra'?'COMPRA':'VENDA'}</span></td>`+
        `<td class="num">${fmtN(r.qty)}</td><td class="num hide-sm">${fmtP(r.preco)}</td><td class="num strong">${fmtBRL(r.vol)}</td></tr>`;
    }).join('')||'<tr><td colspan=7 class=muted>Sem movimentações neste filtro.</td></tr>';
    document.querySelectorAll('.fbtn').forEach(b=>b.classList.toggle('active',b.dataset.g===g));
  }
  document.querySelectorAll('.fbtn').forEach(b=>b.addEventListener('click',()=>render(b.dataset.g)));
  render('todos');
})();</script>"""


def render(ticker: str) -> str:
    info = companies.COMPANIES[ticker]
    rec = pd.read_parquet(BASE / "data" / "recompra.parquet")
    cvm = pd.read_parquet(BASE / "data" / "cvm44.parquet")
    rec = rec[rec["ticker"] == ticker]
    cvm = cvm[cvm["ticker"] == ticker]

    rec_body, rk = _recompra_section(rec)
    prog_body = _prog_exec_section(rec, ticker)
    cvm_body, ck = _cvm44_section(cvm, ticker)
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
  {prog_body}
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
