"""Tema do dossiê: paleta, CSS e <head> autossuficiente (SVG inline, sem CDN de JS)."""

CSS = r"""
:root{
  --bg:#0B1015; --panel:#121A21; --panel2:#18242D; --line:#22323C;
  --paper:#E8E6DD; --muted:#8A9AA4; --faint:#5B6B74;
  --buy:#46B98A; --sell:#E0714C; --accent:#3FA7B5; --gold:#D7B45A;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--paper);
  font-family:'Inter',system-ui,sans-serif;line-height:1.45;-webkit-font-smoothing:antialiased}
.wrap{max-width:1080px;margin:0 auto;padding:38px 26px 64px}
a{color:var(--accent);text-decoration:none;border-bottom:1px solid transparent}
a:hover{border-bottom-color:var(--accent)}

.kicker{font:600 11px/1 'Inter',sans-serif;letter-spacing:.22em;text-transform:uppercase;color:var(--accent);margin-bottom:13px}
h1{font-family:'Fraunces',serif;font-weight:560;font-size:clamp(28px,5vw,46px);line-height:1.03;letter-spacing:-.01em;margin:0 0 10px}
h1 .tk{color:var(--accent);font-style:italic}
.sub{color:var(--muted);font-size:14px;display:flex;flex-wrap:wrap;gap:7px 18px;align-items:center}
.sub b{color:var(--paper);font-weight:500}
.chip{font:600 10px/1 'IBM Plex Mono',monospace;letter-spacing:.13em;text-transform:uppercase;padding:5px 9px;border:1px solid var(--line);border-radius:3px;color:var(--muted)}

h2{font-family:'Fraunces',serif;font-weight:560;font-size:21px;margin:38px 0 16px;display:flex;align-items:baseline;gap:12px}
h2 .h-meta{font:500 11px 'IBM Plex Mono',monospace;color:var(--faint);letter-spacing:.04em;text-transform:none}

/* kpis */
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:0;margin:26px 0 8px;border:1px solid var(--line);border-radius:9px;overflow:hidden;background:var(--panel)}
.kpi{padding:18px 20px;border-right:1px solid var(--line)} .kpi:last-child{border-right:0}
.kpi .lbl{font:600 10px/1 'Inter',sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--faint);margin-bottom:10px}
.kpi .val{font:600 23px 'IBM Plex Mono',monospace}
.kpi .val.pos{color:var(--buy)} .kpi .val.neg{color:var(--sell)} .kpi .val.acc{color:var(--accent)}
.kpi .foot{font-size:12px;color:var(--muted);margin-top:7px}

/* cartão / tabela */
.card{background:var(--panel);border:1px solid var(--line);border-radius:9px;overflow:hidden}
.chart-box{padding:16px 18px 8px}
.chart-box svg{width:100%;height:auto;display:block}
.svg-zero{stroke:var(--faint);stroke-width:1}
.svg-tkr{fill:var(--paper);font-family:'IBM Plex Mono',monospace;font-size:11px;font-weight:600}
.svg-val{fill:var(--muted);font-family:'IBM Plex Mono',monospace;font-size:10px}
.svg-axis{fill:var(--faint);font-family:'IBM Plex Mono',monospace;font-size:10px}
.svg-bm{fill:var(--muted);font-family:'IBM Plex Mono',monospace;font-size:10px}

.tbl{width:100%;border-collapse:collapse;font-family:'IBM Plex Mono',monospace;font-size:12.5px}
.tbl th{font:600 10px/1 'Inter',sans-serif;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);
  text-align:left;padding:13px 16px;border-bottom:1px solid var(--line);background:var(--panel)}
.tbl td{padding:10px 16px;border-bottom:1px solid rgba(34,50,60,.55);color:var(--paper)}
.tbl tr:last-child td{border-bottom:0}
.tbl tr:hover td{background:var(--panel2)}
.scroll{max-height:540px;overflow-y:auto}
.scroll .tbl th{position:sticky;top:0;z-index:1}
.pos{color:var(--buy)} .neg{color:var(--sell)}

/* filtro de valor mobiliário */
.filterbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:6px 0 0}
.filterbar .flbl{font:600 10px/1 'Inter',sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--faint);margin-right:4px}
.fbtn{appearance:none;cursor:pointer;background:var(--panel);color:var(--muted);
  border:1px solid var(--line);border-radius:6px;padding:7px 13px;
  font:600 12px 'IBM Plex Mono',monospace;letter-spacing:.02em;transition:.13s}
.fbtn:hover{color:var(--paper);border-color:var(--accent)}
.fbtn.active{color:var(--bg);background:var(--accent);border-color:var(--accent)}
.substats{font:500 12.5px 'IBM Plex Mono',monospace;color:var(--muted);margin:12px 2px 0}
.substats b{color:var(--paper);font-weight:600}

/* execução por programa */
.prog-grid{display:flex;flex-direction:column;gap:14px;margin-top:14px}
.prog-card{padding:0}
.prog-h{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap;padding:13px 18px 0}
.prog-n{font:600 13px 'IBM Plex Mono',monospace;color:var(--accent);display:inline-flex;align-items:center;gap:9px}
.prog-h .muted{font:500 11.5px 'IBM Plex Mono',monospace}
.motivo{font:600 9.5px 'Inter',sans-serif;letter-spacing:.06em;text-transform:uppercase;padding:3px 8px;border-radius:3px;white-space:nowrap;cursor:default}
.motivo.m-lim{color:var(--accent);background:rgba(63,167,181,.14);border:1px solid rgba(63,167,181,.35)}
.motivo.m-prazo{color:var(--sell);background:rgba(224,113,76,.13);border:1px solid rgba(224,113,76,.32)}
.motivo.m-disc{color:var(--gold);background:rgba(215,180,90,.14);border:1px solid rgba(215,180,90,.34)}
.motivo.m-open{color:var(--muted);border:1px solid var(--line)}
.motivo-det{font:500 11.5px 'IBM Plex Mono',monospace;color:var(--muted);padding:6px 18px 0}
.motivo-det b{color:var(--paper);font-weight:600}
.tbl .num{text-align:right}
.tbl .ctr{text-align:center}
.tbl .strong{font-weight:600}
.muted{color:var(--muted)} .faint{color:var(--faint)}

.badge{font:600 9.5px 'Inter',sans-serif;letter-spacing:.07em;text-transform:uppercase;padding:3px 8px;border-radius:3px;white-space:nowrap}
.b-compra{color:var(--buy);background:rgba(70,185,138,.13)}
.b-venda{color:var(--sell);background:rgba(224,113,76,.13)}
.b-aprovacao{color:var(--accent);background:rgba(63,167,181,.13)}
.b-execucao{color:var(--gold);background:rgba(215,180,90,.14)}
.b-encerramento,.b-cancelamento{color:var(--muted);border:1px solid var(--line)}

.lead{color:var(--muted);font-size:13.5px;max-width:760px;margin:8px 0 0}
.lead b{color:var(--paper);font-weight:500}
footer{margin-top:42px;color:var(--faint);font-size:11.5px;font-family:'IBM Plex Mono',monospace;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;border-top:1px solid var(--line);padding-top:16px}

@media (max-width:760px){
  .kpis{grid-template-columns:repeat(2,1fr)} .kpi:nth-child(2){border-right:0}
  .tbl .hide-sm{display:none}
}
"""


def head(title: str) -> str:
    return f"""<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,560;9..144,620&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{CSS}</style></head>"""
