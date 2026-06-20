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
                          exec_value=None, doc_aprov=(r.get("link") or ""), doc_encer=""))
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
        seen.add(k); execs.append((d, q, v, e.get("link") or ""))
    for i, p in enumerate(progs):
        hi = progs[i + 1]["start"] if i + 1 < len(progs) else dt.date(2100, 1, 1)
        cand = [(d, q, v, lk) for d, q, v, lk in execs if p["start"] < d <= hi]
        if cand:
            d, q, v, lk = max(cand, key=lambda t: t[0])
            p["exec_date"], p["exec"], p["exec_value"], p["doc_encer"] = d, q, v, lk
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
        # executado de EXIBIÇÃO: oficial do encerramento se houver; senão o diário
        # validado da tesouraria (caso de empresas sem qtd no comunicado, ex. PRIO)
        p["exec_disp"] = p.get("exec") or p.get("exec_real")
        ev = p.get("exec_value")
        if ev is None and p.get("exec_real") and p.get("preco_med"):
            ev = p["exec_real"] * p["preco_med"]
        p["exec_value_disp"] = ev
        p["exec_fonte"] = "oficial" if p.get("exec") else ("tesouraria" if p.get("exec_real") else None)
        p["reason"] = _closure_reason(p)
    return progs


def _closure_reason(p: dict):
    """Por que o programa encerrou. Um programa só acaba por uma de quatro vias:
    limite de ações, limite de valor (R$), fim do prazo, ou decisão antecipada do
    Conselho (nenhum teto atingido). Retorna (rótulo, detalhe, classe) ou None se
    ainda em andamento."""
    if not p.get("end"):
        return None
    exq, exv = p.get("exec_disp") or 0, p.get("exec_value_disp") or 0
    sh = exq / p["auth"] if p.get("auth") else 0
    val = exv / p["valor_auth"] if p.get("valor_auth") else 0
    if sh >= 0.995:
        return ("limite de ações", f"executou {_qtd(exq)} de {_qtd(p['auth'])} (100%)", "lim")
    if val >= 0.995:
        return ("limite de valor", f"gastou R$ {exv/1e6:,.0f} mi de R$ {p['valor_auth']/1e6:,.0f} mi", "lim")
    if p["end"] >= p["deadline"] - dt.timedelta(days=7):
        return ("fim do prazo", f"venceu em {_data(p['deadline'].isoformat())} ({p['prazo']} meses)", "prazo")
    return ("decisão do Conselho", f"encerrado antes do prazo (em {_data(p['end'].isoformat())}, "
            f"a {sh*100:.0f}% das ações e {val*100:.0f}% do valor)", "disc")


_MES_PT = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
           "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def _detect_splits(ticker: str, d: pd.DataFrame) -> list:
    """Detecta desdobramentos/grupamentos: um SALTO overnight forte no preço cru
    (COTAHIST não ajusta) que COINCIDE com um 'Desdobramento/bonificação' no CVM 44.
    Retorna [(data_split, ratio)] com ratio = preço_antes / preço_depois."""
    try:
        cv = pd.read_parquet(BASE / "data" / "cvm44.parquet")
    except Exception:
        return []
    cv = cv[(cv["ticker"] == ticker)
            & cv["tipo_mov"].fillna("").str.contains("desdobr|bonifica|grupa", case=False)]
    dd = set(pd.to_datetime(cv["data_mov"], errors="coerce").dt.date.dropna())
    if not dd:
        return []
    d = d.sort_values("data").reset_index(drop=True)
    splits = []
    for i in range(1, len(d)):
        r = d["preco"].iloc[i - 1] / d["preco"].iloc[i]
        if (r > 1.8 or r < 0.55) and any(abs((x - d["data"].iloc[i]).days) <= 5 for x in dd):
            splits.append((d["data"].iloc[i], float(r)))
    return splits


def _ticker_splits(ticker: str) -> list:
    """Splits detectados para o ticker (lista [(data, ratio)]), a partir do preço cru."""
    f = BASE / "data" / f"precos_{ticker}.csv"
    if not f.exists():
        return []
    d = pd.read_csv(f, header=None, names=["data", "preco"])
    d["data"] = pd.to_datetime(d["data"], errors="coerce").dt.date
    return _detect_splits(ticker, d.dropna())


def _split_factor(splits: list, date) -> float:
    """Fator p/ retroajustar um preço da data à escala atual = produto dos ratios
    dos splits POSTERIORES à data. preço_ajustado = preço_cru / fator."""
    f = 1.0
    for sd, ratio in splits:
        if date and date < sd:
            f *= ratio
    return f


def _market_prices(ticker: str):
    """Preço diário de fechamento (COTAHIST) em data/precos_<ticker>.csv, se houver.
    RETROAJUSTA por splits (back-adjust à escala atual) — senão o histórico pré-split
    aparece inflado (ex.: PRIO a R$170 em 2019 = ~R$3 hoje após 2 desdobramentos)."""
    f = BASE / "data" / f"precos_{ticker}.csv"
    if not f.exists():
        return None
    d = pd.read_csv(f, header=None, names=["data", "preco"])
    d["data"] = pd.to_datetime(d["data"], errors="coerce").dt.date
    d = d.dropna().sort_values("data").reset_index(drop=True)
    for sd, ratio in _detect_splits(ticker, d):
        d.loc[d["data"] < sd, "preco"] /= ratio   # preços antes do split caem à escala atual
    return d


def _reconcile_note(p: dict, ticker: str) -> str:
    """PADRÃO de validação de encerramento: quando o diário rastreado fica abaixo
    do executado oficial (faltam formulários de tesouraria ainda não publicados),
    calcula o preço IMPLÍCITO das ações que faltam e confronta com o preço de
    mercado do período restante. Se o implícito cai na faixa negociada, o número
    oficial é consistente — e deixamos registrada a expectativa do que o formulário
    pendente deve mostrar. Retorna '' quando o diário já fecha com o oficial."""
    ex, dr = p.get("exec"), p.get("exec_real")
    if not (ex and dr) or not p.get("exec_value") or (ex - dr) <= 0.02 * p["auth"]:
        return ""
    miss = ex - dr
    dval = dr * (p.get("preco_med") or 0)
    implied = (p["exec_value"] - dval) / miss
    last_buy = max((d for d, _ in p.get("cum", [])), default=p["start"])
    end = p.get("end") or p["deadline"]
    off_avg = p["exec_value"] / ex

    mkt, consist = "", ""
    mk = _market_prices(ticker)
    if mk is not None:
        w = mk[(mk["data"] > last_buy) & (mk["data"] <= end)]
        if len(w):
            lo, hi, av = float(w["preco"].min()), float(w["preco"].max()), float(w["preco"].mean())
            ok = lo <= implied <= hi
            near = " (perto da mínima do período)" if implied <= lo + 0.25 * (hi - lo) else ""
            mkt = (f' No período restante a <b>{ticker}</b> negociou <b>R$ {lo:,.2f}–{hi:,.2f}</b> '
                   f'(média R$ {av:,.2f}); o preço implícito{near} <b>cabe nessa faixa</b>')
            consist = " — número oficial <b>consistente</b>." if ok else " — <b>fora da faixa; revisar</b>."

    venc = f"{_MES_PT[end.month]}/{end.year}"
    return (f'<div class="recon-note"><div class="rn-tag">Execução a confirmar · validação por preço</div>'
            f'Rastreamos <b>{_qtd(dr)}</b> ações ({_preco(p.get("preco_med"))} méd) nos formulários mensais já '
            f'publicados; o encerramento oficial reporta <b>{_qtd(ex)}</b> ({_preco(off_avg)} méd). As '
            f'<b>{_qtd(miss)}</b> ações que faltam implicam compra a <b>~{_preco(implied)}</b>.{mkt}{consist} '
            f'<b>Expectativa:</b> quando o formulário de tesouraria de {venc} for publicado (~dia 10 do mês '
            f'seguinte), devemos ver ~{_qtd(miss)} ações compradas a ~{_preco(implied)}.</div>')


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
        buy_pts = [(x(d), y(c)) for d, c in cum]
        xe = buy_pts[-1][0]
        daily_end = cum[-1][1]
        # As ações compradas ficam EM TESOURARIA até o programa encerrar, então o
        # acumulado NÃO cai depois da última compra: segue plano até o fim. Só
        # estendo se o diário está COMPLETO; se ainda é parcial (faltam formulários
        # não publicados), parar na última compra evita uma reta plana enganosa.
        complete = (not p.get("exec")) or abs((p.get("exec") or 0) - daily_end) <= 0.02 * p["auth"]
        line_pts = [(padL, ybot)] + buy_pts
        if complete:
            end_x = x(min(p.get("end") or p["deadline"], p["deadline"]))
            if end_x > xe:
                line_pts.append((end_x, buy_pts[-1][1]))
        xlast = line_pts[-1][0]
        poly = " ".join(f"{px:.1f},{py:.1f}" for px, py in line_pts)
        s.append(f'<polygon points="{padL},{ybot} {poly} {xlast:.1f},{ybot}" fill="rgba(70,185,138,.16)"/>')
        s.append(f'<polyline points="{poly}" fill="none" stroke="var(--buy)" stroke-width="2"/>')
        for px, py in buy_pts:
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
        note = _reconcile_note(p, ticker)
        panels.append(f'<div class="card prog-card">{head}<div class="chart-box">{_prog_panel(p, i)}</div>{note}</div>')
    return f"""
  <h2>Execução por programa <span class="h-meta">executado × autorizado · motivo do encerramento</span></h2>
  <p class="lead">Programas são <b>sequenciais</b> (um de cada vez) e <b>não precisam atingir o máximo</b>.
    Cada um encerra por <b>uma de quatro vias</b>: bateu o <b>limite de ações</b>, bateu o <b>limite de valor (R$)</b>,
    chegou ao <b>fim do prazo</b>, ou foi <b>encerrado antecipadamente pelo Conselho</b> (nenhum teto atingido) — o
    badge ao lado de cada programa diz qual foi. A <b>linha verde sólida</b> é o <b>executado oficial</b>; a
    <b>curva verde</b> é a execução diária da tesouraria (segue <b>plana</b> depois da última compra, pois as ações
    ficam em tesouraria até o programa encerrar) e pode estar <b>parcial</b> no mês corrente. A
    <b>linha dourada</b> é o teto de ações, a <b>vertical vermelha</b> a <b>validade</b> nominal e a
    <b>vertical teal</b> o <b>encerramento de fato</b>.</p>
  <div class="prog-grid">{''.join(reversed(panels))}</div>"""


def _doclink(url: str, rotulo: str) -> str:
    return (f'<a href="{url}" target="_blank" rel="noopener">{rotulo} ↗</a>'
            if url else f'<span class="faint">{rotulo} —</span>')


def _recompra_section(rec: pd.DataFrame, ticker: str) -> tuple[str, dict]:
    progs = _programs(rec, ticker)
    n_prog = len(progs)
    total_exec = sum((p.get("exec_disp") or 0) for p in progs if p.get("end"))
    abertos = [(i, p) for i, p in enumerate(progs, 1) if not p.get("end")]
    fechados = [(i, p) for i, p in enumerate(progs, 1) if p.get("end")]

    def lim(p):
        v = f' · até <b>{_vol(p["valor_auth"])}</b>' if p.get("valor_auth") else ""
        return f'até <b>{_qtd(p["auth"])}</b> ações{v}'

    # --- programa ABERTO: card em destaque ---
    open_html = ""
    for i, p in abertos:
        ex = p.get("exec") or p.get("exec_real")
        exec_txt = (f'{_qtd(ex)} ações' + (f' · {_vol(p["exec_value"])}' if p.get("exec_value") else "")
                    ) if ex else "ainda sem execução reportada"
        open_html += f"""
  <div class="open-prog">
    <div class="op-head"><span class="op-tag">Programa {i}</span>
      <span class="motivo m-open">em andamento</span></div>
    <div class="op-grid">
      <div class="opc"><div class="opl">Início</div><div class="opv">{_data(p["start"].isoformat())}</div></div>
      <div class="opc"><div class="opl">Vencimento</div><div class="opv">{_data(p["deadline"].isoformat())}</div></div>
      <div class="opc"><div class="opl">Prazo</div><div class="opv">{p["prazo"]} meses</div></div>
      <div class="opc"><div class="opl">Limite de ações</div><div class="opv">{_qtd(p["auth"])}</div></div>
      <div class="opc"><div class="opl">Limite de valor</div><div class="opv">{_vol(p["valor_auth"]) or "—"}</div></div>
      <div class="opc"><div class="opl">Executado</div><div class="opv">{exec_txt}</div></div>
    </div>
    <div class="op-foot">{_doclink(p.get("doc_aprov"), "aprovação")}</div>
  </div>"""

    # --- programas ENCERRADOS: uma linha resumida cada ---
    rows = []
    for i, p in sorted(fechados, key=lambda t: t[1]["start"], reverse=True):
        ex = p.get("exec_disp") or 0
        pct = 100 * ex / p["auth"] if p["auth"] else 0
        rsn = p.get("reason")
        motivo = f'<span class="motivo m-{rsn[2]}">{rsn[0]}</span>' if rsn else "—"
        evd = p.get("exec_value_disp")
        preco_off = (evd / ex) if (evd and ex) else None
        fonte = ' <span class="faint">(tesouraria)</span>' if p.get("exec_fonte") == "tesouraria" else ""
        execu = (f'{_qtd(ex)} <span class="faint">({pct:.0f}%)</span>{fonte}'
                 + (f'<br><span class="ag-sub">{_vol(evd)} · {_preco(preco_off)} méd</span>'
                    if evd else ""))
        docs = f'{_doclink(p.get("doc_aprov"), "aprov")} · {_doclink(p.get("doc_encer"), "encerr")}'
        rows.append(
            f'<tr><td class="strong">Programa {i}</td>'
            f'<td class="muted">{_data(p["start"].isoformat())} → {_data(p["end"].isoformat())}</td>'
            f'<td>{lim(p)}</td>'
            f'<td class="num strong">{execu}</td>'
            f'<td>{motivo}</td>'
            f'<td class="ctr nowrap">{docs}</td></tr>')

    # --- cancelamentos de ações em tesouraria (redução de capital) ---
    canc = ""
    if "qtd_cancelada" in rec.columns:
        cr = rec[(rec["tipo"] == "cancelamento") & rec["qtd_cancelada"].notna()]
        cr = cr.sort_values("data_entrega").drop_duplicates("qtd_cancelada")
        if len(cr):
            itens = " · ".join(
                f'<b>{_qtd(c["qtd_cancelada"])}</b> ações em {_data(str(c["data_entrega"])[:10])} '
                f'{_doclink(c.get("link"), "doc")}' for _, c in cr.iterrows())
            tot = cr["qtd_cancelada"].sum()
            canc = (f'<div class="recon-note" style="border-left-color:var(--sell);background:rgba(224,113,76,.07)">'
                    f'<div class="rn-tag" style="color:var(--sell)">Cancelamento de ações em tesouraria</div>'
                    f'A companhia <b>cancelou</b> (redução de capital, não é venda) {itens}. '
                    f'Some {_qtd(tot)} ações que saíram da tesouraria sem ir ao mercado.</div>')

    body = f"""
  <h2>Recompra de ações <span class="h-meta">programas &amp; execução</span></h2>
  <p class="lead">Programas de recompra autorizados pelo Conselho — datas, limites (ações e valor),
    prazo e os documentos. O programa <b>em andamento</b> aparece em destaque; os encerrados,
    resumidos com o <b>quanto foi efetivamente recomprado</b> e o motivo do encerramento.</p>
  {open_html}
  <div class="card" style="margin-top:14px">
    <table class="tbl"><thead><tr><th>Programa</th><th>Período</th><th>Limites</th>
      <th class="num">Executado</th><th>Encerrou por</th><th class="ctr">Documentos</th></tr></thead>
      <tbody>{''.join(rows) or '<tr><td colspan=6 class=muted>Sem programas encerrados.</td></tr>'}</tbody></table>
  </div>
  {canc}"""
    return body, {"n_prog": n_prog, "total_exec": total_exec}


def _grp(ticker: str, especie) -> str:
    return ticker if _ascii(especie).startswith("aco") else "Outros"


_CVM_GRP = [("Controlador", "#D7B45A"), ("Conselho", "#3FA7B5"), ("Diretor", "#9B8CFF")]


def _signmi(v: float) -> str:
    a = abs(v)
    s = f"R$ {a/1000:,.2f} bi" if a >= 1000 else f"R$ {a:,.0f} mi"
    return ("+" if v > 0 else "−" if v < 0 else "") + s


def _ticks(lo: float, hi: float, n: int = 5):
    span = (hi - lo) or 1
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    step = min([1, 2, 2.5, 5, 10], key=lambda m: abs(m * mag - raw)) * mag
    t = math.ceil(lo / step) * step
    out = []
    while t <= hi + 1e-9:
        out.append(t); t += step
    return out


def _cvm_avista(v: pd.DataFrame) -> pd.DataFrame:
    """Só negócios À VISTA de ações (mercado) — exclui empréstimo de ações,
    bonificação, plano de remuneração e posse, que poluem o fluxo."""
    a = v[v["especie"].map(lambda e: _ascii(e).startswith("aco"))
          & v["tipo_mov"].fillna("").str.contains("vista|termo", case=False)].copy()
    a["grp"] = a["orgao"].map(lambda o: "Controlador" if "Controlador" in str(o)
                              else "Diretor" if "Diretor" in str(o)
                              else "Conselho" if "Conselho" in str(o) else "Outro")
    a["dt"] = pd.to_datetime(a.get("data_mov").fillna(a["data_ref"]), errors="coerce").dt.date
    a["sv"] = a["volume"].fillna(0) * a["direcao"].map({"compra": 1, "venda": -1}).fillna(0)
    return a.dropna(subset=["dt"]).sort_values("dt")


def _cvm_cum_svg(a: pd.DataFrame) -> str:
    W, H, padL, padR, padT, padB = 960, 300, 56, 16, 20, 36
    xr, yb, yt = W - padR, H - padB, padT
    d0, d1 = a["dt"].min(), a["dt"].max()
    span = max((d1 - d0).days, 1)
    series, vals = {}, [0.0]
    for g, _ in _CVM_GRP:
        sub = a[a["grp"] == g]
        cum, pts = 0.0, [(d0, 0.0)]
        for d, sv in zip(sub["dt"], sub["sv"]):
            pts.append((d, cum)); cum += sv / 1e6; pts.append((d, cum))
        pts.append((d1, cum))
        series[g] = pts; vals += [p[1] for p in pts]
    ymin, ymax = min(vals), max(vals)
    p = (ymax - ymin) * 0.08 or 1; ymin -= p; ymax += p
    x = lambda d: padL + (d - d0).days / span * (xr - padL)
    y = lambda val: yb - (val - ymin) / (ymax - ymin) * (yb - yt)
    s = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Posição líquida acumulada">']
    for t in _ticks(ymin, ymax):
        lbl = f"{t/1000:,.1f}bi" if abs(t) >= 1000 else f"{t:,.0f}"
        s.append(f'<line x1="{padL}" y1="{y(t):.1f}" x2="{xr}" y2="{y(t):.1f}" stroke="var(--line)" stroke-width="1" opacity="{0.7 if t==0 else 0.4}"/>')
        s.append(f'<text class="svg-axis" x="{padL-7}" y="{y(t)+3:.1f}" text-anchor="end">{lbl}</text>')
    for yr in range(d0.year + 1, d1.year + 1):
        xa = x(dt.date(yr, 1, 1))
        s.append(f'<line x1="{xa:.1f}" y1="{yt}" x2="{xa:.1f}" y2="{yb}" stroke="var(--line)" stroke-width="1" opacity=".3"/>')
        s.append(f'<text class="svg-axis" x="{xa:.1f}" y="{yb+16:.1f}" text-anchor="middle">{yr}</text>')
    for g, color in _CVM_GRP:
        pts = " ".join(f"{x(d):.1f},{y(val):.1f}" for d, val in series[g])
        s.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"/>')
        d, val = series[g][-1]
        s.append(f'<circle cx="{x(d):.1f}" cy="{y(val):.1f}" r="3" fill="{color}"/>')
    s.append(f'<text class="svg-bm" x="{padL}" y="{padT-7}">posição líquida acumulada · R$ mi (à vista)</text></svg>')
    return "".join(s)


def _cvm_year_svg(a: pd.DataFrame) -> str:
    W, H, padL, padR, padT, padB = 960, 290, 56, 16, 22, 34
    xr, yb, yt = W - padR, H - padB, padT
    years = sorted({d.year for d in a["dt"]})
    net = {(yr, g): 0.0 for yr in years for g, _ in _CVM_GRP}
    keys = {g for g, _ in _CVM_GRP}
    for d, g, sv in zip(a["dt"], a["grp"], a["sv"]):
        if g in keys:
            net[(d.year, g)] += sv / 1e6
    vals = [v for v in net.values()] + [0.0]
    ymin, ymax = min(vals), max(vals)
    p = (ymax - ymin) * 0.1 or 1; ymin -= p * 0.3; ymax += p
    slot = (xr - padL) / len(years)
    bw = min(26, slot / (len(_CVM_GRP) + 1.5))
    y = lambda val: yb - (val - ymin) / (ymax - ymin) * (yb - yt)
    s = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Fluxo líquido por ano">']
    for t in _ticks(ymin, ymax):
        lbl = f"{t/1000:,.1f}bi" if abs(t) >= 1000 else f"{t:,.0f}"
        s.append(f'<line x1="{padL}" y1="{y(t):.1f}" x2="{xr}" y2="{y(t):.1f}" stroke="var(--line)" stroke-width="1" opacity="{0.7 if t==0 else 0.4}"/>')
        s.append(f'<text class="svg-axis" x="{padL-7}" y="{y(t)+3:.1f}" text-anchor="end">{lbl}</text>')
    y0 = y(0)
    for i, yr in enumerate(years):
        cx = padL + slot * i + slot / 2
        s.append(f'<text class="svg-axis" x="{cx:.1f}" y="{yb+16:.1f}" text-anchor="middle">{yr}</text>')
        actives = [(g, c) for g, c in _CVM_GRP if abs(net[(yr, g)]) > 0.01]
        m = len(actives)
        for j, (g, color) in enumerate(actives):
            v = net[(yr, g)]
            bx = cx + (j - (m - 1) / 2) * (bw + 2) - bw / 2
            by = y(v) if v >= 0 else y0
            h = max(abs(y(v) - y0), 1)
            s.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="2" fill="{color}"/>')
            if abs(v) >= 0.08 * (ymax - ymin):
                ty = by - 4 if v >= 0 else by + h + 11
                s.append(f'<text class="svg-val" x="{bx+bw/2:.1f}" y="{ty:.1f}" text-anchor="middle">{v/1000:,.1f}bi</text>' if abs(v) >= 1000
                         else f'<text class="svg-val" x="{bx+bw/2:.1f}" y="{ty:.1f}" text-anchor="middle">{v:,.0f}</text>')
    s.append(f'<text class="svg-bm" x="{padL}" y="{padT-8}">fluxo líquido por ano · R$ mi · ▲ compra ▼ venda</text></svg>')
    return "".join(s)


def _cvm_flow_block(v: pd.DataFrame) -> str:
    a = _cvm_avista(v)
    if a.empty:
        return ""
    cap = " · ".join(
        f'<span class="cvm-net"><span class="tim-dot" style="background:{c}"></span>{g} '
        f'<b>{_signmi(a[a["grp"]==g]["sv"].sum()/1e6)}</b></span>' for g, c in _CVM_GRP)
    return f"""
  <p class="substats" style="margin:14px 2px 4px">Fluxo à vista (mercado), líquido desde o IPO:
    {cap} · <span class="muted">{len(a)} negócios</span></p>
  <div class="card"><div class="chart-box">{_cvm_cum_svg(a)}</div></div>
  <div class="card" style="margin-top:12px"><div class="chart-box">{_cvm_year_svg(a)}</div>
    <div class="tim-leg">{''.join(f'<div class="tim-row" style="gap:8px"><span class="tim-dot" style="background:{c}"></span><span class="tim-g">{g}</span></div>' for g,c in _CVM_GRP)}</div></div>"""


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
  <p class="lead">Compras e vendas <b>à vista</b> de <b>{ticker}</b> declaradas por <b>controlador,
    administradores e tesouraria</b> (Res. CVM 44, art. 11), desde o IPO — exclui empréstimo de ações,
    bonificação e plano de remuneração, que não são negócios de mercado. Acima, o fluxo agregado;
    abaixo, o <b>filtro</b> separa ações × outros valores mobiliários na tabela detalhada.</p>
  {_cvm_flow_block(v)}
  <div class="filterbar" style="margin-top:22px">
    <span class="flbl">Valor mobiliário</span>
    <button class="fbtn active" data-g="todos">Todos</button>
    <button class="fbtn" data-g="{ticker}">{ticker} · ações</button>
    <button class="fbtn" data-g="Outros">Outros</button>
  </div>
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
  function render(g){
    const rows=g==='todos'?DATA:DATA.filter(r=>r.grp===g);
    let vol=0; rows.forEach(r=>{vol+=(r.vol||0);});
    document.getElementById('cvm-stats').innerHTML=`Tabela: <b>${rows.length}</b> movimentos · volume bruto <b>${fmtBRL(vol)}</b> <span class="faint">(inclui empréstimo, bonificação e plano)</span>`;
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


def _vol(v):
    """R$ em bi/mi, formato internacional."""
    if not v:
        return None
    if abs(v) >= 1e9:
        return f"R$ {v/1e9:,.2f} bi"
    if abs(v) >= 1e6:
        return f"R$ {v/1e6:,.0f} mi"
    return f"R$ {v/1e3:,.0f} mil"


def _win_anchors(hoje: dt.date) -> list[tuple]:
    """(rótulo, data inicial) das janelas: último mês, 6m, YTD, 12m."""
    def back(months):
        m, y = hoje.month - months, hoje.year
        while m <= 0:
            m += 12; y -= 1
        return dt.date(y, m, min(hoje.day, 28))
    return [("Último mês", back(1)), ("6 meses", back(6)),
            (f"{hoje.year} · YTD", dt.date(hoje.year, 1, 1)), ("12 meses", back(12))]


def _indicators_section(cvm: pd.DataFrame, ticker: str) -> str:
    """Placar de abertura: compras/vendas (R$) por agente em 4 janelas. Insiders
    (Controlador/Diretores/Conselho) vêm do CVM 44 à vista; a Tesouraria vem da
    recompra diária validada. Só transações de mercado (à vista/termo) — empréstimo
    de ações, bonificação, plano de remuneração e posse não entram."""
    hoje = dt.date.today()
    wins = _win_anchors(hoje)
    c = cvm.copy()
    c["dm"] = pd.to_datetime(c["data_mov"], errors="coerce").dt.date
    c["vol2"] = c["quantidade"].fillna(0) * c["preco"].fillna(0)
    av = c[c["tipo_mov"].fillna("").str.contains("vista|termo", case=False)]

    def org(o):
        if "Controlador" in str(o): return "Controlador"
        if "Diretor" in str(o): return "Diretores"
        if "Conselho" in str(o): return "Conselho"
        return None
    av = av.assign(ag=av["orgao"].map(org))
    daily = _daily_buys(ticker)  # (date, qty, preco)

    def insider(ag, d0, dirn):
        sub = av[(av["ag"] == ag) & (av["dm"] >= d0) & (av["direcao"] == dirn)]
        return float(sub["vol2"].sum()), float(sub["quantidade"].sum())

    def tesouraria(d0):
        b = [(q, pr) for d, q, pr in daily if d >= d0]
        return sum(q * pr for q, pr in b), sum(q for q, pr in b)

    def cell(cv, cq, vv, vq):
        parts = []
        if cv:
            parts.append(f'<span class="ind-c" title="{cq:,.0f} ações">▲ {_vol(cv)}</span>')
        if vv:
            parts.append(f'<span class="ind-v" title="{vq:,.0f} ações">▼ {_vol(vv)}</span>')
        return "<br>".join(parts) or '<span class="faint">—</span>'

    rows = []
    # Tesouraria (só compras: recompra)
    tds = "".join(f'<td class="num">{cell(*tesouraria(d0), 0, 0)}</td>' for _, d0 in wins)
    rows.append(f'<tr><td class="strong">Tesouraria<br><span class="ag-sub">recompra</span></td>{tds}</tr>')
    for ag, sub in [("Controlador", "acionista controlador"), ("Diretores", "diretoria"),
                    ("Conselho", "conselho de adm.")]:
        tds = ""
        for _, d0 in wins:
            cv, cq = insider(ag, d0, "compra")
            vv, vq = insider(ag, d0, "venda")
            tds += f'<td class="num">{cell(cv, cq, vv, vq)}</td>'
        rows.append(f'<tr><td class="strong">{ag}<br><span class="ag-sub">{sub}</span></td>{tds}</tr>')
    ths = "".join(f"<th class='num'>{lbl}</th>" for lbl, _ in wins)
    return f"""
  <h2>Movimentações recentes <span class="h-meta">compras ▲ e vendas ▼ · volume R$ · à vista</span></h2>
  <p class="lead">Quanto cada agente <b>comprou</b> (▲) e <b>vendeu</b> (▼) em ações da companhia, em quatro janelas
    até {_data(hoje.isoformat())}. <b>Tesouraria</b> = recompra (execução diária validada); <b>Controlador, Diretores
    e Conselho</b> = negócios à vista no CVM 44 (Res. 44). Só transações de mercado — passe o mouse para ver as ações.</p>
  <div class="card"><table class="tbl ind-tbl">
    <thead><tr><th>Agente</th>{ths}</tr></thead>
    <tbody>{''.join(rows)}</tbody></table></div>"""


_GRUPOS_TIMING = [
    ("Tesouraria", "#46B98A"), ("Controlador", "#D7B45A"),
    ("Diretores", "#E0714C"), ("Conselho", "#3FA7B5"),
]


def _buy_groups(ticker: str):
    """Compras (data, preço, qtd) por grupo, só de AÇÕES. Tesouraria vem da
    recompra diária; Controlador/Diretores/Conselho do CVM 44 à vista. Retorna
    {grupo: {pts, qtd, vol, avg, pct, d0, d1}} + os preços de mercado (px)."""
    px = _market_prices(ticker)
    rd = pd.read_parquet(BASE / "data" / "recompra_diaria.parquet")
    cv = pd.read_parquet(BASE / "data" / "cvm44.parquet")
    if "ticker" in rd:
        rd = rd[rd["ticker"] == ticker]
    cv = cv[cv["ticker"] == ticker]

    # preço RETROAJUSTADO por split (mesma escala da linha de preço), senão as
    # compras pré-split (ex. insiders da PRIO em 2020-21) ficam fora da curva.
    splits = _ticker_splits(ticker)

    def _mk(dates, precos, qts):
        out = []
        for d, p, q in zip(dates, precos, qts):
            if not (p and p > 0):
                continue
            do = _date_obj(str(d)[:10])
            if do:
                out.append((do, float(p) / _split_factor(splits, do), float(q)))
        return out

    raw = {}
    t = rd[rd["operacao"] == "compra"]
    raw["Tesouraria"] = _mk(t["data"], t["preco"], t["quantidade"])
    av = cv[cv["tipo_mov"].fillna("").str.contains("vista|termo", case=False)
            & (cv["direcao"] == "compra")
            & cv["especie"].map(lambda e: _ascii(e).startswith("aco"))]
    for g in ("Controlador", "Diretores", "Conselho"):
        s = av[av["orgao"].map(lambda o: g in str(o))]
        raw[g] = _mk(s["data_mov"], s["preco"], s["quantidade"])

    out = {}
    for g, pts in raw.items():
        pts = [x for x in pts if x[0]]
        if not pts:
            continue
        qtd = sum(q for _, _, q in pts)
        vol = sum(p * q for _, p, q in pts)
        avg = vol / qtd if qtd else 0
        d0, d1 = min(d for d, _, _ in pts), max(d for d, _, _ in pts)
        pct = None
        if px is not None:
            w = px[(px["data"] >= d0) & (px["data"] <= d1)]
            if len(w) > 5:
                pct = 100 * float((w["preco"] < avg).mean())
        out[g] = dict(pts=pts, qtd=qtd, vol=vol, avg=avg, pct=pct, d0=d0, d1=d1)
    return out, px


def _timing_section(ticker: str) -> str:
    groups, px = _buy_groups(ticker)
    if px is None or not groups:
        return ""
    W, H = 960, 400
    padL, padR, padT, padB = 46, 18, 18, 34
    xr, yb, yt = W - padR, H - padB, padT
    prows = px.sort_values("data")
    d0, d1 = prows["data"].iloc[0], prows["data"].iloc[-1]
    span = max((d1 - d0).days, 1)
    pmin, pmax = float(prows["preco"].min()), float(prows["preco"].max())
    ymin = math.floor(pmin / 10) * 10
    ymax = math.ceil(pmax / 10) * 10
    x = lambda d: padL + (d - d0).days / span * (xr - padL)
    y = lambda p: yb - (p - ymin) / (ymax - ymin) * (yb - yt)
    maxvol = max((max((p * q for _, p, q in g["pts"]), default=0) for g in groups.values()), default=1) or 1

    s = [f'<svg id="tim-svg" class="zoomable" viewBox="0 0 {W} {H}" role="img" aria-label="Compras por grupo vs preço">']
    # grade de preço (horizontais)
    step = 10
    pl = ymin
    while pl <= ymax:
        s.append(f'<line x1="{padL}" y1="{y(pl):.1f}" x2="{xr}" y2="{y(pl):.1f}" stroke="var(--line)" stroke-width="1" opacity=".5"/>')
        s.append(f'<text class="svg-axis" x="{padL-7}" y="{y(pl)+3:.1f}" text-anchor="end">{pl:.0f}</text>')
        pl += step
    # marcadores de ano
    for yr in range(d0.year + 1, d1.year + 1):
        xa = x(dt.date(yr, 1, 1))
        s.append(f'<line x1="{xa:.1f}" y1="{yt}" x2="{xa:.1f}" y2="{yb}" stroke="var(--line)" stroke-width="1" opacity=".35"/>')
        s.append(f'<text class="svg-axis" x="{xa:.1f}" y="{yb+16:.1f}" text-anchor="middle">{yr}</text>')
    # linha de preço
    pts = " ".join(f"{x(d):.1f},{y(p):.1f}" for d, p in zip(prows["data"], prows["preco"]))
    s.append(f'<polyline points="{pts}" fill="none" stroke="var(--faint)" stroke-width="1.3" opacity=".8"/>')
    # linhas tracejadas do preço médio (grupos com mais de uma compra)
    for g, color in _GRUPOS_TIMING:
        gd = groups.get(g)
        if gd and len(gd["pts"]) > 2 and ymin <= gd["avg"] <= ymax:
            s.append(f'<line x1="{padL}" y1="{y(gd["avg"]):.1f}" x2="{xr}" y2="{y(gd["avg"]):.1f}" stroke="{color}" stroke-width="1.1" stroke-dasharray="5 4" opacity=".7"/>')
    # bolhas de compra
    for g, color in _GRUPOS_TIMING:
        gd = groups.get(g)
        if not gd:
            continue
        for d, p, q in sorted(gd["pts"], key=lambda t: -t[1] * t[2]):
            r = 3 + 12 * math.sqrt((p * q) / maxvol)
            s.append(f'<circle cx="{x(d):.1f}" cy="{y(p):.1f}" r="{r:.1f}" fill="{color}" fill-opacity=".42" stroke="{color}" stroke-width="1"/>')
    s.append("</svg>")

    # legenda + estatística
    leg = []
    for g, color in _GRUPOS_TIMING:
        gd = groups.get(g)
        if not gd:
            continue
        if gd["pct"] is not None:
            barato = 100 - gd["pct"]
            tom = "tom-baixa" if gd["pct"] <= 40 else "tom-alta" if gd["pct"] >= 55 else "tom-neutro"
            stat = f'mais barato que <b>{barato:.0f}%</b> dos pregões'
            tag = '<span class="tim-tag {0}">{1}</span>'.format(
                tom, "compra na baixa" if gd["pct"] <= 40 else "compra constante" if gd["pct"] >= 55 else "neutro")
        else:
            stat, tag = "evento isolado", ""
        leg.append(
            f'<div class="tim-row"><span class="tim-dot" style="background:{color}"></span>'
            f'<span class="tim-g">{g}</span>'
            f'<span class="tim-st">{_qtd(gd["qtd"])} ações · {_vol(gd["vol"])} · médio <b>{_preco(gd["avg"])}</b> · {stat}</span>{tag}</div>')

    return f"""
  <h2>Timing de compra × preço <span class="h-meta">quem compra na baixa</span></h2>
  <p class="lead">Cada <b>bolha</b> é uma compra de ações, posicionada no <b>preço pago</b> e na data, com o
    <b>tamanho proporcional ao volume</b> (R$); a linha cinza é o preço da {ticker}. As tracejadas marcam o
    <b>preço médio</b> de cada grupo. Quanto mais baixo na curva e mais à esquerda dos picos, mais o grupo
    <b>aproveita as quedas</b>. O percentil mostra em quantos pregões da janela o papel esteve <i>mais barato</i>
    que o preço médio pago.</p>
  <div class="card"><div class="chart-box">{''.join(s)}
    <div class="zoom-ctrl">
      <button type="button" data-z="out" aria-label="menos zoom">−</button>
      <button type="button" data-z="in" aria-label="mais zoom">+</button>
      <button type="button" data-z="reset" aria-label="resetar zoom">⟲</button>
    </div>
    <div class="zoom-hint">zoom: <b>+ / −</b> ou scroll · arraste para mover</div></div>
    <div class="tim-leg">{''.join(leg)}</div></div>
{_ZOOM_JS.replace("__ID__", "tim-svg")}"""


_ZOOM_JS = r"""<script>(()=>{
  const svg=document.getElementById('__ID__'); if(!svg) return;
  const b=svg.viewBox.baseVal, O={x:b.x,y:b.y,w:b.width,h:b.height}, V={...O};
  const apply=()=>svg.setAttribute('viewBox',`${V.x} ${V.y} ${V.w} ${V.h}`);
  const clamp=()=>{V.w=Math.min(V.w,O.w);V.h=Math.min(V.h,O.h);
    V.x=Math.max(O.x,Math.min(V.x,O.x+O.w-V.w));V.y=Math.max(O.y,Math.min(V.y,O.y+O.h-V.h));};
  function zoom(f,cx,cy){const nw=V.w*f,nh=V.h*f;
    V.x=cx-(cx-V.x)*(nw/V.w); V.y=cy-(cy-V.y)*(nh/V.h); V.w=nw; V.h=nh; clamp(); apply();}
  const reset=()=>{Object.assign(V,O); apply();};
  const at=e=>{const r=svg.getBoundingClientRect();
    return [V.x+(e.clientX-r.left)/r.width*V.w, V.y+(e.clientY-r.top)/r.height*V.h];};
  svg.addEventListener('wheel',e=>{e.preventDefault(); zoom(e.deltaY<0?0.84:1/0.84, ...at(e));},{passive:false});
  let d=null;
  svg.addEventListener('pointerdown',e=>{d={x:e.clientX,y:e.clientY,vx:V.x,vy:V.y};
    svg.setPointerCapture(e.pointerId); svg.style.cursor='grabbing';});
  svg.addEventListener('pointermove',e=>{if(!d)return;const r=svg.getBoundingClientRect();
    V.x=d.vx-(e.clientX-d.x)/r.width*V.w; V.y=d.vy-(e.clientY-d.y)/r.height*V.h; clamp(); apply();});
  const up=()=>{d=null; svg.style.cursor='';};
  svg.addEventListener('pointerup',up); svg.addEventListener('pointercancel',up);
  svg.addEventListener('dblclick',()=>reset());
  const box=svg.closest('.chart-box');
  box && box.querySelectorAll('[data-z]').forEach(btn=>btn.addEventListener('click',()=>{
    const k=btn.dataset.z, cx=V.x+V.w/2, cy=V.y+V.h/2;
    if(k==='reset') reset(); else zoom(k==='in'?0.7:1/0.7, cx, cy);
  }));
})();</script>"""


def _treasury_saldo(ticker: str):
    import json
    f = BASE / "data" / "tesouraria.json"
    if not f.exists():
        return None
    d = json.loads(f.read_text(encoding="utf-8")).get(ticker)
    return d if d and d.get("saldo") else None


def _company_nav(current: str) -> str:
    if len(companies.COMPANIES) < 2:
        return ""
    chips = "".join(
        f'<a class="navchip{" on" if tk == current else ""}" href="{tk.lower()}.html">'
        f'{tk} <span class="nc-nome">{i["nome"]}</span></a>'
        for tk, i in companies.COMPANIES.items())
    return f'<nav class="company-nav"><span class="cn-lbl">Empresas</span>{chips}</nav>'


def render(ticker: str) -> str:
    info = companies.COMPANIES[ticker]
    rec = pd.read_parquet(BASE / "data" / "recompra.parquet")
    cvm = pd.read_parquet(BASE / "data" / "cvm44.parquet")
    rec = rec[rec["ticker"] == ticker]
    cvm = cvm[cvm["ticker"] == ticker]

    rec_body, rk = _recompra_section(rec, ticker)
    prog_body = _prog_exec_section(rec, ticker)
    cvm_body, ck = _cvm44_section(cvm, ticker)
    ind_body = _indicators_section(cvm, ticker)
    tim_body = _timing_section(ticker)
    gerado = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    ts = _treasury_saldo(ticker)
    _tes_html = (f'<span>Tesouraria <b>{_qtd(ts["saldo"])}</b> ações '
                 f'<span class="faint">({_mes(ts["data_ref"])})</span></span>·' if ts else "")

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
    {_company_nav(ticker)}
    <h1>{info['nome']} · <span class="tk">{ticker}</span></h1>
    <div class="sub"><span>{info['setor']}</span>·
      <span>CNPJ <b>{info['cnpj']}</b></span>·{_tes_html}
      <span>Gerado em <b>{gerado}</b></span><span class="chip">v1 · {ticker}</span></div>
  </header>
  {kpis}
  {ind_body}
  {rec_body}
  {prog_body}
  {cvm_body}
  {tim_body}
  <footer><span>dossiê CVM · recompra + CVM 44 (art. 11)</span><span>fonte: comunicados IPE &amp; VLMO da CVM · {gerado}</span></footer>
</div></body></html>"""


def main():
    for tk in companies.COMPANIES:
        html = render(tk)
        (OUT / f"{tk.lower()}.html").write_text(html, encoding="utf-8")
        print(f"[dossie] {tk.lower()}.html  ({tk})")
    # index = empresa em foco
    (OUT / "index.html").write_text(render(companies.FOCO), encoding="utf-8")
    print(f"[dossie] index.html  (foco: {companies.FOCO})")


if __name__ == "__main__":
    main()
