#!/usr/bin/env python3
"""Coleta diária de indexadores globais de matérias-primas e grava docs/data.json.

Fontes públicas:
  - FRED (St. Louis Fed, espelha o Pink Sheet do Banco Mundial): energia, metais, agrícolas. Exige FRED_API_KEY (gratuita).
  - Ipeadata: Brent diário (sem chave).
  - Frankfurter (BCE): câmbio USD/BRL, EUR/BRL, USD/CNY (sem chave).
  - BCB SGS: IPCA e IGP-M (sem chave).
Se uma série falhar, mantém a última versão salva e marca como "stale".
"""
import datetime as dt
import json
import os
import sys

import requests

OUT = "docs/data.json"
KEY = os.getenv("FRED_API_KEY")
TODAY = dt.date.today()
S = requests.Session()
S.headers["User-Agent"] = "commodities-dashboard/1.0"


def get(url, **params):
    r = S.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def ms(d):
    return int(dt.datetime.fromisoformat(d[:10]).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def fred(sid, years=5):
    if not KEY:
        raise RuntimeError("FRED_API_KEY ausente")
    j = get("https://api.stlouisfed.org/fred/series/observations", series_id=sid, api_key=KEY,
            file_type="json", observation_start=str(TODAY - dt.timedelta(days=365 * years)))
    return [[ms(o["date"]), float(o["value"])] for o in j["observations"] if o["value"] not in (".", "")]


def ipea(code, top=1300):
    j = get(f"https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='{code}')",
            **{"$orderby": "VALDATA desc", "$top": str(top)})
    return sorted([ms(x["VALDATA"]), float(x["VALVALOR"])] for x in j["value"] if x["VALVALOR"] is not None)


def fx(base, sym):
    j = get(f"https://api.frankfurter.dev/v1/{TODAY - dt.timedelta(days=730)}..{TODAY}", base=base, symbols=sym)
    return sorted([ms(d), r[sym]] for d, r in j["rates"].items())


def bcb(code, n=36):
    j = get(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados/ultimos/{n}", formato="json")
    return [[ms("-".join(reversed(x["data"].split("/")))), float(x["valor"])] for x in j]


# (id, nome, categoria, unidade, frequência, função de coleta)
F = lambda sid: (lambda: fred(sid))
JOBS = [
    <!DOCTYPE html>
<html lang="pt-BR" data-theme="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Indexadores globais de matérias-primas</title>
  <style>
    :root {
      --bg: #141311; --surface: #1d1c19; --surface-2: #24231f; --border: #32302b;
      --text: #f3f1ec; --muted: #a39e93; --accent: #0f766e; --accent-bright: #14b8a6;
      --accent-soft: rgba(20, 184, 166, 0.14); --up: #ef5350; --down: #22c55e; --warn: #eab308;
    }
    [data-theme="light"] {
      --bg: #f6f5f2; --surface: #ffffff; --surface-2: #efede8; --border: #dcd8ce;
      --text: #1c1b18; --muted: #666158; --accent: #0f766e; --accent-bright: #0d9488;
      --accent-soft: rgba(15, 118, 110, 0.10); --up: #dc2626; --down: #16a34a; --warn: #ca8a04;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg); color: var(--text); line-height: 1.45; padding-bottom: 48px;
    }
    .container { max-width: 1380px; margin: 0 auto; padding: 24px 20px; }
    header {
      display: flex; justify-content: space-between; align-items: flex-start; gap: 16px;
      padding-bottom: 18px; border-bottom: 1px solid var(--border); margin-bottom: 20px; flex-wrap: wrap;
    }
    h1 { font-family: Georgia, serif; font-size: 1.85rem; margin-bottom: 6px; }
    .subtitle { font-size: 0.88rem; color: var(--muted); display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .btn {
      background: var(--surface); color: var(--text); border: 1px solid var(--border);
      padding: 8px 14px; border-radius: 6px; font-size: 0.86rem; cursor: pointer;
    }
    .btn:hover { border-color: var(--accent-bright); }
    .btn-accent { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
    .tabs { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 22px; }
    .tab {
      background: var(--surface); color: var(--text); border: 1px solid var(--border);
      padding: 7px 14px; border-radius: 6px; font-size: 0.88rem; cursor: pointer;
    }
    .tab:hover { border-color: var(--accent-bright); }
    .tab.active { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
    .tab.insights-tab { border-color: var(--accent-bright); }
    .section-title { font-family: Georgia, serif; font-size: 1.3rem; margin: 24px 0 12px; }
    .section-title:first-child { margin-top: 0; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(265px, 1fr)); gap: 14px; }
    .card {
      background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
      padding: 15px 17px; cursor: pointer; transition: border-color 0.15s;
    }
    .card:hover { border-color: var(--muted); }
    .card.selected { border: 2px solid var(--accent-bright); padding: 14px 16px; }
    .card-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 4px; }
    .card-name { font-size: 0.98rem; font-weight: 700; }
    .card-meta { display: flex; align-items: center; gap: 8px; font-size: 0.76rem; color: var(--muted); margin-bottom: 12px; }
    .badge {
      font-size: 0.68rem; font-weight: 700; padding: 2px 6px; border-radius: 4px;
      background: var(--accent-soft); color: var(--accent-bright);
    }
    .badge.warn { background: rgba(234, 179, 8, 0.15); color: var(--warn); }
    .card-value-row { display: flex; align-items: baseline; gap: 7px; margin-bottom: 2px; }
    .card-value { font-size: 1.55rem; font-weight: 700; letter-spacing: -0.02em; }
    .card-unit { font-size: 0.8rem; color: var(--muted); }
    .card-date { font-size: 0.76rem; color: var(--muted); margin-bottom: 10px; }
    .card-stats { border-top: 1px solid var(--border); padding-top: 9px; display: flex; flex-direction: column; gap: 4px; font-size: 0.84rem; }
    .stat-row { display: flex; justify-content: space-between; }
    .stat-label { color: var(--muted); }
    .val-up { color: var(--up); font-weight: 600; }
    .val-down { color: var(--down); font-weight: 600; }
    .val-flat { color: var(--muted); font-weight: 600; }

    /* SVG Chart */
    .panel { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 18px 20px; margin-top: 24px; }
    .chart-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; }
    .chart-legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: 0.82rem; margin-bottom: 10px; }
    .legend-item { display: flex; align-items: center; gap: 6px; }
    .legend-dot { width: 10px; height: 10px; border-radius: 50%; }
    .svg-wrap { width: 100%; overflow-x: auto; }
    svg.chart-svg { width: 100%; height: 280px; display: block; }

    /* Insights */
    .insights-stack { display: flex; flex-direction: column; gap: 18px; }
    .summary-box {
      background: linear-gradient(135deg, var(--surface) 0%, var(--surface-2) 100%);
      border: 1px solid var(--border); border-left: 4px solid var(--accent-bright);
      border-radius: 10px; padding: 18px 20px;
    }
    .summary-box h2, .panel h2 { font-family: Georgia, serif; font-size: 1.2rem; margin-bottom: 8px; }
    .summary-list { list-style: none; display: flex; flex-direction: column; gap: 8px; font-size: 0.92rem; }
    .sem-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr)); gap: 14px; }
    .sem-col {
      background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
      padding: 15px 17px; display: flex; flex-direction: column; gap: 10px;
    }
    .sem-col.buy { border-top: 3px solid var(--down); }
    .sem-col.alert { border-top: 3px solid var(--up); }
    .sem-col.neutral { border-top: 3px solid var(--warn); }
    .sem-tip { font-size: 0.8rem; color: var(--muted); }
    .sem-items { display: flex; flex-direction: column; gap: 7px; max-height: 320px; overflow-y: auto; }
    .sem-item {
      background: var(--surface-2); border: 1px solid var(--border); border-radius: 7px;
      padding: 9px 11px; display: flex; justify-content: space-between; align-items: center; gap: 8px;
    }
    .table-wrap { overflow-x: auto; margin-top: 10px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.86rem; }
    th, td { padding: 9px 11px; border-bottom: 1px solid var(--border); text-align: left; white-space: nowrap; }
    th { color: var(--muted); font-size: 0.78rem; text-transform: uppercase; }
    .num { text-align: right; }
    .pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.74rem; font-weight: 600; }
    .pill-green { background: rgba(34, 197, 94, 0.14); color: var(--down); }
    .pill-red { background: rgba(239, 83, 80, 0.14); color: var(--up); }
    .pill-yellow { background: rgba(234, 179, 8, 0.15); color: var(--warn); }
    .controls-row { display: flex; flex-wrap: wrap; gap: 10px; margin: 10px 0; align-items: center; }
    select, input[type="number"] {
      background: var(--surface-2); color: var(--text); border: 1px solid var(--border);
      padding: 8px 12px; border-radius: 6px; font-size: 0.88rem;
    }
    textarea {
      width: 100%; min-height: 105px; background: var(--surface-2); color: var(--text);
      border: 1px solid var(--border); border-radius: 8px; padding: 12px; font-family: inherit; font-size: 0.9rem;
    }
    .hidden { display: none !important; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>Indexadores globais de matérias-primas</h1>
        <div class="subtitle" id="meta-line">Inicializando painel...</div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn" id="theme-toggle">Claro / Escuro</button>
      </div>
    </header>

    <nav class="tabs" id="tabs"></nav>

    <main id="cards-view">
      <div id="cards-container"></div>
      <section class="panel">
        <div class="chart-header">
          <div>
            <strong id="chart-title">Comparativo histórico</strong>
            <div style="font-size:0.8rem;color:var(--muted)" id="chart-subtitle">Clique nos cards acima para comparar (Base 100 quando há 2+ séries)</div>
          </div>
          <button class="btn" id="clear-sel" style="padding:5px 10px;font-size:0.8rem">Limpar seleção</button>
        </div>
        <div class="chart-legend" id="chart-legend"></div>
        <div class="svg-wrap"><svg class="chart-svg" id="chart-svg" viewBox="0 0 900 280" preserveAspectRatio="none"></svg></div>
      </section>
    </main>

    <main id="insights-view" class="insights-stack hidden"></main>
  </div>

  <script>
    // Catálogo completo dos 40 indicadores (usado como estrutura base + fallback se data.json não tiver o item)
    const CATALOG = [
      // Energia
      { id: "BRENT", name: "Petróleo Brent", cat: "Energia", unit: "US$/bbl", freq: "diária", base: 74.5, dPct: -0.4, mPct: -6.2 },
      { id: "DCOILWTICO", name: "Petróleo WTI", cat: "Energia", unit: "US$/bbl", freq: "diária", base: 70.8, dPct: -0.3, mPct: -5.8 },
      { id: "DHHNGSP", name: "Gás natural Henry Hub", cat: "Energia", unit: "US$/MMBtu", freq: "diária", base: 2.95, dPct: 1.2, mPct: 4.1 },
      { id: "PNGASEUUSDM", name: "Gás natural Europa", cat: "Energia", unit: "US$/MMBtu", freq: "mensal", base: 13.8, dPct: 6.4, mPct: 6.4 },
      // Metais
      { id: "PCOPPUSDM", name: "Cobre", cat: "Metais", unit: "US$/t", freq: "mensal", base: 9240, dPct: -2.4, mPct: -2.4 },
      { id: "PALUMUSDM", name: "Alumínio", cat: "Metais", unit: "US$/t", freq: "mensal", base: 2580, dPct: 3.1, mPct: 3.1 },
      { id: "PNICKUSDM", name: "Níquel", cat: "Metais", unit: "US$/t", freq: "mensal", base: 16100, dPct: -5.4, mPct: -5.4 },
      { id: "PZINCUSDM", name: "Zinco", cat: "Metais", unit: "US$/t", freq: "mensal", base: 3020, dPct: 1.9, mPct: 1.9 },
      { id: "PLEADUSDM", name: "Chumbo", cat: "Metais", unit: "US$/t", freq: "mensal", base: 2040, dPct: -1.2, mPct: -1.2 },
      { id: "PTINUSDM", name: "Estanho", cat: "Metais", unit: "US$/t", freq: "mensal", base: 31200, dPct: 0.8, mPct: 0.8 },
      { id: "PIORECRUSDM", name: "Minério de ferro", cat: "Metais", unit: "US$/t", freq: "mensal", base: 103.5, dPct: -6.1, mPct: -6.1 },
      // Câmbio
      { id: "USDBRL", name: "Dólar (USD/BRL)", cat: "Câmbio", unit: "R$", freq: "diária", base: 5.75, dPct: 0.2, mPct: 2.1, liveFx: ["USD","BRL"] },
      { id: "EURBRL", name: "Euro (EUR/BRL)", cat: "Câmbio", unit: "R$", freq: "diária", base: 6.12, dPct: 0.1, mPct: 1.4, liveFx: ["EUR","BRL"] },
      { id: "USDCNY", name: "Dólar/Yuan (USD/CNY)", cat: "Câmbio", unit: "CNY", freq: "diária", base: 7.22, dPct: 0.05, mPct: 0.8, liveFx: ["USD","CNY"] },
      { id: "DTWEXBGS", name: "Índice Dólar Global", cat: "Câmbio", unit: "pts", freq: "diária", base: 125.4, dPct: 0.1, mPct: 1.5 },
      // Inflação BR
      { id: "IPCA", name: "IPCA (mês)", cat: "Inflação BR", unit: "%", freq: "mensal", base: 0.44, dPct: 0.0, mPct: 0.44, bcb: 433 },
      { id: "IPCA12M", name: "IPCA (acum. 12m)", cat: "Inflação BR", unit: "%", freq: "mensal", base: 4.76, dPct: 0.0, mPct: 4.76, bcb: 13522 },
      { id: "IGPM", name: "IGP-M (mês)", cat: "Inflação BR", unit: "%", freq: "mensal", base: 0.62, dPct: 0.0, mPct: 0.62, bcb: 189 },
      { id: "IPAM", name: "IPA-M (Produtor BR)", cat: "Inflação BR", unit: "%", freq: "mensal", base: 0.78, dPct: 0.0, mPct: 0.78, bcb: 225 },
      { id: "INPC", name: "INPC (mês)", cat: "Inflação BR", unit: "%", freq: "mensal", base: 0.48, dPct: 0.0, mPct: 0.48, bcb: 188 },
      // Inflação EUA
      { id: "CPIAUCSL", name: "CPI EUA (Geral)", cat: "Inflação EUA", unit: "pts", freq: "mensal", base: 315.4, dPct: 0.24, mPct: 0.24 },
      { id: "CPILFESL", name: "Core CPI EUA (Núcleo)", cat: "Inflação EUA", unit: "pts", freq: "mensal", base: 321.1, dPct: 0.28, mPct: 0.28 },
      { id: "PPIACO", name: "PPI EUA (Produtor)", cat: "Inflação EUA", unit: "pts", freq: "mensal", base: 254.2, dPct: 0.18, mPct: 0.18 },
      { id: "PCEPI", name: "PCE EUA (Índice Fed)", cat: "Inflação EUA", unit: "pts", freq: "mensal", base: 124.3, dPct: 0.21, mPct: 0.21 },
      // Juros
      { id: "SELIC", name: "Meta Selic (BR)", cat: "Juros", unit: "% a.a.", freq: "diária", base: 11.25, dPct: 0.0, mPct: 0.0, bcb: 432 },
      { id: "DFF", name: "Fed Funds (Juros EUA)", cat: "Juros", unit: "% a.a.", freq: "diária", base: 4.58, dPct: 0.0, mPct: -5.2 },
      // Embalagens & Químicos
      { id: "WPU066", name: "Resinas Plásticas (PPI)", cat: "Embalagens & Quím.", unit: "pts", freq: "mensal", base: 289.4, dPct: -1.9, mPct: -1.9 },
      { id: "WPU0914", name: "Papelão / Paperboard (PPI)", cat: "Embalagens & Quím.", unit: "pts", freq: "mensal", base: 326.8, dPct: 2.4, mPct: 2.4 },
      { id: "WPU061", name: "Químicos Industriais (PPI)", cat: "Embalagens & Quím.", unit: "pts", freq: "mensal", base: 312.0, dPct: -0.8, mPct: -0.8 },
      // Logística
      { id: "DDFUELUSGULF", name: "Diesel Golfo EUA (Paridade)", cat: "Logística", unit: "US$/gal", freq: "diária", base: 2.18, dPct: -0.6, mPct: -5.5 },
      { id: "PCU483111483111", name: "Frete Marítimo (PPI)", cat: "Logística", unit: "pts", freq: "mensal", base: 174.5, dPct: 6.1, mPct: 6.1 }
    ];
]


def main():
    old = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            old = {s["id"]: s for s in json.load(f).get("series", [])}
    series, errors = [], []
    for sid, name, cat, unit, freq, fn in JOBS:
        try:
            pts = fn()
            if not pts:
                raise ValueError("série vazia")
            series.append(dict(id=sid, name=name, cat=cat, unit=unit, freq=freq, stale=False, points=pts[-520:]))
        except Exception as e:  # uma fonte fora do ar não derruba as demais
            errors.append(f"{sid}: {e}")
            if sid in old:
                series.append({**old[sid], "stale": True})
    print(f"{len(series)}/{len(JOBS)} séries OK")
    for e in errors:
        print("ERRO", e, file=sys.stderr)
    if not any(not s["stale"] for s in series):
        sys.exit("Nenhuma série atualizada; nada foi gravado.")
    os.makedirs("docs", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "errors": errors,
                   "series": series}, f, separators=(",", ":"), ensure_ascii=False)


if __name__ == "__main__":
    main()
