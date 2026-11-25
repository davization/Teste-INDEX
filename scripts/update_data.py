#!/usr/bin/env python3
"""Coleta diária de indexadores globais de matérias-primas e grava docs/data.json.

Fontes públicas:
  - FRED (St. Louis Fed, espelha o Pink Sheet do Banco Mundial): energia, metais, agrícolas. Exige FRED_API_KEY (gratuita).
  - Ipeadata: Brent diário (sem chave).
  - Frankfurter (BCE): câmbio USD/BRL, EUR/BRL, USD/CNY (sem chave).
  - BCB SGS: IPCA e IGP-M (sem chave).
  - Comex Stat (MDIC): preço médio, volume, frete e concentração de origem das importações por NCM (sem chave).
Se uma série falhar, mantém a última versão salva e marca como "stale".
"""
import datetime as dt
import json
import os
import sys
import time

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
    # Energia
    ("BRENT", "Petróleo Brent", "Energia", "US$/bbl", "diária", lambda: ipea("EIA366_PBRENT366")),
    ("DCOILWTICO", "Petróleo WTI", "Energia", "US$/bbl", "diária", F("DCOILWTICO")),
    ("DHHNGSP", "Gás natural Henry Hub", "Energia", "US$/MMBtu", "diária", F("DHHNGSP")),
    ("PNGASEUUSDM", "Gás natural Europa", "Energia", "US$/MMBtu", "mensal", F("PNGASEUUSDM")),
    ("PCOALAUUSDM", "Carvão (Austrália)", "Energia", "US$/t", "mensal", F("PCOALAUUSDM")),
    ("PURANUSDM", "Urânio", "Energia", "US$/lb", "mensal", F("PURANUSDM")),
    # Metais
    ("PCOPPUSDM", "Cobre", "Metais", "US$/t", "mensal", F("PCOPPUSDM")),
    ("PALUMUSDM", "Alumínio", "Metais", "US$/t", "mensal", F("PALUMUSDM")),
    ("PNICKUSDM", "Níquel", "Metais", "US$/t", "mensal", F("PNICKUSDM")),
    ("PZINCUSDM", "Zinco", "Metais", "US$/t", "mensal", F("PZINCUSDM")),
    ("PLEADUSDM", "Chumbo", "Metais", "US$/t", "mensal", F("PLEADUSDM")),
    ("PTINUSDM", "Estanho", "Metais", "US$/t", "mensal", F("PTINUSDM")),
    ("PIORECRUSDM", "Minério de ferro", "Metais", "US$/t", "mensal", F("PIORECRUSDM")),
    # Agrícolas e fibras
    ("PWHEAMTUSDM", "Trigo", "Agrícolas", "US$/t", "mensal", F("PWHEAMTUSDM")),
    ("PMAIZMTUSDM", "Milho", "Agrícolas", "US$/t", "mensal", F("PMAIZMTUSDM")),
    ("PSOYBUSDM", "Soja", "Agrícolas", "US$/t", "mensal", F("PSOYBUSDM")),
    ("PRICENPQUSDM", "Arroz", "Agrícolas", "US$/t", "mensal", F("PRICENPQUSDM")),
    ("PSUGAISAUSDM", "Açúcar", "Agrícolas", "US¢/lb", "mensal", F("PSUGAISAUSDM")),
    ("PCOFFOTMUSDM", "Café arábica", "Agrícolas", "US¢/lb", "mensal", F("PCOFFOTMUSDM")),
    ("PCOTTINDUSDM", "Algodão", "Agrícolas", "US¢/lb", "mensal", F("PCOTTINDUSDM")),
    ("PRUBBUSDM", "Borracha", "Agrícolas", "US¢/lb", "mensal", F("PRUBBUSDM")),
    ("PPOILUSDM", "Óleo de palma", "Agrícolas", "US$/t", "mensal", F("PPOILUSDM")),
    # Câmbio e inflação
    ("USDBRL", "Dólar (USD/BRL)", "Câmbio", "R$", "diária", lambda: fx("USD", "BRL")),
    ("EURBRL", "Euro (EUR/BRL)", "Câmbio", "R$", "diária", lambda: fx("EUR", "BRL")),
    ("USDCNY", "Dólar/Yuan (USD/CNY)", "Câmbio", "CNY", "diária", lambda: fx("USD", "CNY")),
    ("IPCA", "IPCA (mês)", "Inflação BR", "%", "mensal", lambda: bcb(433)),
    ("IGPM", "IGP-M (mês)", "Inflação BR", "%", "mensal", lambda: bcb(189)),
]


# ---------------------------------------------------------------------------
# Comex Stat (MDIC): importações brasileiras por NCM. Edite a lista abaixo
# com os NCMs (8 dígitos) que você realmente compra.
# ---------------------------------------------------------------------------
COMEX_URL = "https://api-comexstat.mdic.gov.br/general?language=pt"
COMEX_NCMS = {
    "27101931": "Óleos lubrificantes sem aditivos (básicos)",
    "27101932": "Óleos lubrificantes com aditivos (acabados)",
    "38112100": "Aditivos p/ lubrificantes (c/ óleo de petróleo)",
    "38112900": "Aditivos p/ lubrificantes (outros)",
    "39012029": "Polietileno alta densidade (PEAD)",
}
COMEX_CAT = "Comex · Importações BR"
KNOWN = {"year", "monthNumber", "metricFOB", "metricKG", "metricFreight", "metricInsurance", "metricCIF", "metricStatistic"}


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def comex_post(body):
    verify = True
    for _ in range(5):
        try:
            r = S.post(COMEX_URL, json=body, timeout=120, verify=verify)
        except requests.exceptions.SSLError:
            if not verify:
                raise
            # A cadeia de certificados ICP-Brasil nem sempre é reconhecida. Dados públicos, sem credenciais.
            print("AVISO: certificado do Comex Stat não reconhecido; repetindo sem verificação.", file=sys.stderr)
            verify = False
            continue
        if r.status_code == 429 or "limite de solicita" in r.text.lower():
            time.sleep(12)  # a API limita o ritmo de chamadas
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("limite de tentativas no Comex Stat")


def comex_call(ncm, details):
    body = {"flow": "import", "monthDetail": True,
            "period": {"from": (TODAY - dt.timedelta(days=365 * 5)).strftime("%Y-%m"), "to": TODAY.strftime("%Y-%m")},
            "filters": [{"filter": "ncm", "values": [int(ncm)]}], "details": details}
    err = None
    for metrics in (["metricFOB", "metricKG", "metricFreight", "metricInsurance"], ["metricFOB", "metricKG"]):
        try:
            return comex_post({**body, "metrics": metrics})["data"]["list"]
        except Exception as e:  # se as métricas de frete não existirem, tenta só FOB e peso
            err = e
        time.sleep(3)
    raise err


def _month(r):
    return ms(f"{r['year']}-{int(r['monthNumber']):02d}-01")


def comex_series(ncm, name):
    tot = {}
    for r in comex_call(ncm, []):
        t = tot.setdefault(_month(r), {"fob": 0.0, "kg": 0.0, "fr": 0.0})
        t["fob"] += _num(r.get("metricFOB"))
        t["kg"] += _num(r.get("metricKG"))
        t["fr"] += _num(r.get("metricFreight")) + _num(r.get("metricInsurance"))
    months = [m for m in sorted(tot) if tot[m]["kg"] > 0][-60:]
    if not months:
        raise ValueError("sem importações no período")
    base = dict(cat=COMEX_CAT, freq="mensal (defasagem ~1 mês)", stale=False)
    out = [
        dict(base, id=f"CX_{ncm}_PRECO", name=f"{name} · preço médio FOB", unit="US$/t",
             points=[[m, tot[m]["fob"] / tot[m]["kg"] * 1000] for m in months]),
        dict(base, id=f"CX_{ncm}_VOL", name=f"{name} · volume importado", unit="t",
             points=[[m, tot[m]["kg"] / 1000] for m in months]),
    ]
    if any(tot[m]["fr"] > 0 and tot[m]["fob"] > 0 for m in months):
        out.append(dict(base, id=f"CX_{ncm}_FRETE", name=f"{name} · frete+seguro", unit="% do FOB",
                        points=[[m, tot[m]["fr"] / tot[m]["fob"] * 100] for m in months if tot[m]["fob"] > 0]))
    time.sleep(3)
    by = {}
    for r in comex_call(ncm, ["country"]):
        key = next((k for k in r if k not in KNOWN), None)
        if key:
            d = by.setdefault(_month(r), {})
            d[r[key]] = d.get(r[key], 0.0) + _num(r.get("metricFOB"))
    hhi, note = [], None
    for m in sorted(by):
        total = sum(by[m].values())
        if total > 0:
            hhi.append([m, sum((v / total * 100) ** 2 for v in by[m].values())])
    if hhi:
        last = by[hhi[-1][0]]
        top = max(last, key=last.get)
        when = dt.datetime.fromtimestamp(hhi[-1][0] / 1000, dt.timezone.utc).strftime("%m/%Y")
        note = f"Principal origem em {when}: {top} ({last[top] / sum(last.values()) * 100:.0f}% do valor FOB)"
        out.append(dict(base, id=f"CX_{ncm}_HHI", name=f"{name} · concentração de origem", unit="pontos (HHI)",
                        points=hhi[-60:], note=note))
    return out


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
    for ncm, nome in COMEX_NCMS.items():
        try:
            series.extend(comex_series(ncm, nome))
        except Exception as e:  # uma falha no Comex não derruba o resto
            errors.append(f"Comex {ncm}: {e}")
            series.extend({**o, "stale": True} for sid, o in old.items() if sid.startswith(f"CX_{ncm}_"))
        time.sleep(3)
    print(f"{len(series)} séries gravadas")
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
