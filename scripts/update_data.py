#!/usr/bin/env python3
"""Coleta diária de indexadores globais de matérias-primas, macro, juros e logística e grava docs/data.json."""
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
    j = get(
        "https://api.stlouisfed.org/fred/series/observations",
        series_id=sid,
        api_key=KEY,
        file_type="json",
        observation_start=str(TODAY - dt.timedelta(days=365 * years)),
    )
    return [[ms(o["date"]), float(o["value"])] for o in j["observations"] if o["value"] not in (".", "")]


def ipea(code, top=1300):
    j = get(
        f"https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='{code}')",
        **{"$orderby": "VALDATA desc", "$top": str(top)},
    )
    return sorted([ms(x["VALDATA"]), float(x["VALVALOR"])] for x in j["value"] if x["VALVALOR"] is not None)


def fx(base, sym):
    j = get(f"https://api.frankfurter.dev/v1/{TODAY - dt.timedelta(days=730)}..{TODAY}", base=base, symbols=sym)
    return sorted([ms(d), r[sym]] for d, r in j["rates"].items())


def bcb(code, n=36):
    j = get(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados/ultimos/{n}", formato="json")
    return [[ms("-".join(reversed(x["data"].split("/")))), float(x["valor"])] for x in j]


F = lambda sid: (lambda: fred(sid))
JOBS = [
    # Energia
    ("BRENT", "Petróleo Brent", "Energia", "US$/bbl", "diária", lambda: ipea("EIA366_PBRENT366")),
    ("DCOILWTICO", "Petróleo WTI", "Energia", "US$/bbl", "diária", F("DCOILWTICO")),
    # Metais
    ("PCOPPUSDM", "Cobre", "Metais", "US$/t", "mensal", F("PCOPPUSDM")),
    ("PALUMUSDM", "Alumínio", "Metais", "US$/t", "mensal", F("PALUMUSDM")),
    ("PNICKUSDM", "Níquel", "Metais", "US$/t", "mensal", F("PNICKUSDM")),
    ("PZINCUSDM", "Zinco", "Metais", "US$/t", "mensal", F("PZINCUSDM")),
    ("PLEADUSDM", "Chumbo", "Metais", "US$/t", "mensal", F("PLEADUSDM")),
    ("PTINUSDM", "Estanho", "Metais", "US$/t", "mensal", F("PTINUSDM")),
    ("PIORECRUSDM", "Minério de ferro", "Metais", "US$/t", "mensal", F("PIORECRUSDM")),
   # Câmbio
    ("USDBRL", "Dólar (USD/BRL)", "Câmbio", "R$", "diária", lambda: fx("USD", "BRL")),
    ("EURBRL", "Euro (EUR/BRL)", "Câmbio", "R$", "diária", lambda: fx("EUR", "BRL")),
    ("USDCNY", "Dólar/Yuan (USD/CNY)", "Câmbio", "CNY", "diária", lambda: fx("USD", "CNY")),
    ("DTWEXBGS", "Índice Dólar Global", "Câmbio", "pts", "diária", F("DTWEXBGS")),

    # Inflação Brasil (BCB SGS)
    ("IPCA", "IPCA (mês)", "Inflação BR", "%", "mensal", lambda: bcb(433)),
    ("IPCA12M", "IPCA (acum. 12m)", "Inflação BR", "%", "mensal", lambda: bcb(13522)),
    ("IGPM", "IGP-M (mês)", "Inflação BR", "%", "mensal", lambda: bcb(189)),
    ("IPAM", "IPA-M (Produtor BR)", "Inflação BR", "%", "mensal", lambda: bcb(225)),
    ("INPC", "INPC (mês)", "Inflação BR", "%", "mensal", lambda: bcb(188)),

    # Inflação EUA (FRED)
    ("CPIAUCSL", "CPI EUA (Geral)", "Inflação EUA", "pts", "mensal", F("CPIAUCSL")),
    ("CPILFESL", "Core CPI EUA (Núcleo)", "Inflação EUA", "pts", "mensal", F("CPILFESL")),
    ("PPIACO", "PPI EUA (Produtor)", "Inflação EUA", "pts", "mensal", F("PPIACO")),
    ("PCEPI", "PCE EUA (Índice Fed)", "Inflação EUA", "pts", "mensal", F("PCEPI")),

    # Juros
    ("SELIC", "Meta Selic (BR)", "Juros", "% a.a.", "diária", lambda: bcb(432, n=365)),
    ("DFF", "Fed Funds (Juros EUA)", "Juros", "% a.a.", "diária", F("DFF")),

    # Embalagens & Químicos (Proxies PPI EUA)
    ("WPU066", "Resinas Plásticas (PPI)", "Embalagens & Quím.", "pts", "mensal", F("WPU066")),
    ("WPU0914", "Papelão / Paperboard (PPI)", "Embalagens & Quím.", "pts", "mensal", F("WPU0914")),
    ("WPU061", "Químicos Industriais (PPI)", "Embalagens & Quím.", "pts", "mensal", F("WPU061")),

    # Logística
    ("DDFUELUSGULF", "Diesel Golfo EUA (Paridade)", "Logística", "US$/gal", "diária", F("DDFUELUSGULF")),
    ("PCU483111483111", "Frete Marítimo (PPI)", "Logística", "pts", "mensal", F("PCU483111483111")),
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
        except Exception as e:
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
        json.dump(
            {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "errors": errors, "series": series},
            f,
            separators=(",", ":"),
            ensure_ascii=False,
        )


if __name__ == "__main__":
    main()
