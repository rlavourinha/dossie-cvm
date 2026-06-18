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
