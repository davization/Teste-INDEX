#!/usr/bin/env python3
"""Gera docs/brief.json: o "Resumo do dia" exibido no topo do dashboard.

- Os números vêm de cálculos em código (nunca do modelo).
- Se existir ANTHROPIC_API_KEY, o Claude redige o texto a partir desses fatos.
  Todo número do texto é conferido contra os fatos; se algo não bater, usa o texto automático.
- Sem chave (ou em qualquer falha), gera um resumo automático por regras. O dashboard nunca fica sem resumo.
"""
import datetime as dt
import json
import os
import re
import sys

import requests

DATA, OUT = "docs/data.json", "docs/brief.json"
KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = os.getenv("BRIEF_MODEL", "claude-haiku-5-5")
DAY = 864e5

SYSTEM = """Você escreve o resumo diário de um dashboard de inteligência de mercado para o setor de compras (matérias-primas, lubrificantes e derivados).
Regras:
- Use SOMENTE os fatos fornecidos. Copie os números exatamente como estão (mesmo formato e casas decimais). Não calcule, não arredonde, não converta.
- Não explique causas (guerra, clima, política etc.) e não faça previsões: descreva apenas o que os dados mostram.
- Séries mensais, inclusive as do Comex, têm defasagem: avise isso quando citá-las.
- Português do Brasil, tom objetivo, 120 a 170 palavras, 3 parágrafos curtos, sem listas e sem títulos:
  (1) o que mais subiu ou caiu; (2) onde os preços estão caros ou baratos frente ao histórico de 5 anos e riscos como concentração de origem;
  (3) implicação prática para negociação e compras (argumento de reajuste, janela de compra), sem recomendar contrato específico.
- Se houver séries desatualizadas, mencione em uma frase."""


def br(v, d=2, sign=False):
    s = f"{v:{'+' if sign else ''},.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(a, b):
    return (a - b) / abs(b) * 100 if b else None


def entries(series):
    rows = []
    for s in series:
        p = s["points"]
        if s.get("stale") or len(p) < 2:
            continue
        t, v = p[-1]

        def ref(days):
            tg = t - days * DAY
            r = min(p, key=lambda x: abs(x[0] - tg))
            return r[1] if r[0] != t and abs(r[0] - tg) < 45 * DAY else None

        e = dict(name=s["name"], unit=s["unit"], v=v, date=dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).strftime("%d/%m/%Y"), pp=s["unit"] == "%")
        if not e["pp"]:
            e["d"] = pct(v, p[-2][1])
            e["m"] = pct(v, ref(30)) if ref(30) else None
            e["y"] = pct(v, ref(365)) if ref(365) else None
            e["pctl"] = round(sum(1 for x in p if x[1] <= v) / len(p) * 100)
        rows.append(e)
    return rows


def line(e):
    d = 3 if e["v"] < 10 else 2 if e["v"] < 1000 else 0
    parts = [f"{e['name']}: {br(e['v'], d)} {e['unit']} ({e['date']})"]
    for k, lab in (("d", "último período"), ("m", "30 dias"), ("y", "12 meses")):
        if e.get(k) is not None:
            parts.append(f"{lab} {br(e[k], 1, True)}%")
    if e.get("pctl") is not None:
        parts.append(f"percentil 5 anos {e['pctl']}")
    return "- " + "; ".join(parts)


def build(data):
    E = entries(data["series"])
    mov = [e for e in E if not e["pp"] and e.get("m") is not None]
    ups = [e for e in sorted(mov, key=lambda e: -e["m"])[:6] if e["m"] > 0]
    downs = [e for e in sorted(mov, key=lambda e: e["m"])[:6] if e["m"] < 0]
    ext = [e for e in E if e.get("pctl") is not None and (e["pctl"] >= 90 or e["pctl"] <= 10)][:6]
    infl = [e for e in E if e["pp"]]
    notes = [s["note"] for s in data["series"] if s.get("note") and not s.get("stale")]
    stale = [s["name"] for s in data["series"] if s.get("stale")]
    sec = lambda t, L: f"{t}:\n" + "\n".join(L) if L else ""
    facts = "\n\n".join(x for x in [
        sec("MAIORES ALTAS (30 dias)", [line(e) for e in ups]),
        sec("MAIORES QUEDAS (30 dias)", [line(e) for e in downs]),
        sec("NÍVEIS EXTREMOS NO HISTÓRICO (percentil >= 90 ou <= 10)", [line(e) for e in ext]),
        sec("INFLAÇÃO (taxa mensal)", [f"- {e['name']}: {br(e['v'])}% ({e['date']})" for e in infl]),
        sec("CONCENTRAÇÃO DE ORIGEM (Comex Stat, dado mensal)", [f"- {n}" for n in notes[:5]]),
        f"SÉRIES DESATUALIZADAS: {len(stale)}" + (": " + ", ".join(stale[:5]) if stale else ""),
    ] if x)
    return E, ups, downs, ext, stale, facts


def fallback(ups, downs, ext, stale):
    p = []
    a = ", ".join(f"{e['name']} ({br(e['m'], 1, True)}%)" for e in ups[:3])
    b = ", ".join(f"{e['name']} ({br(e['m'], 1, True)}%)" for e in downs[:3])
    p.append("Variação em 30 dias (ou último período, nas séries mensais). " + (f"Maiores altas: {a}. " if a else "") + (f"Maiores quedas: {b}." if b else ""))
    hi = ", ".join(f"{e['name']} (P{e['pctl']})" for e in ext if e["pctl"] >= 90)
    lo = ", ".join(f"{e['name']} (P{e['pctl']})" for e in ext if e["pctl"] <= 10)
    p.append("Posição frente ao histórico de 5 anos. " + (f"Em patamar alto: {hi}. " if hi else "") + (f"Em patamar baixo: {lo}." if lo else "") if (hi or lo) else "Nenhuma série em nível extremo frente ao histórico de 5 anos.")
    if stale:
        p.append(f"{len(stale)} série(s) estão desatualizadas e ficaram de fora deste resumo.")
    return "\n\n".join(p)


def grounded(text, facts):
    for tok in re.findall(r"\d[\d.,]*\d|\d", text):
        tok = tok.rstrip(".,")
        if tok in facts or (tok.isdigit() and (int(tok) <= 12 or 2020 <= int(tok) <= 2030)):
            continue
        return tok
    return None


def ask(facts):
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=90,
                      headers={"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                      json={"model": MODEL, "max_tokens": 600, "system": SYSTEM,
                            "messages": [{"role": "user", "content": f"Fatos de hoje ({dt.date.today():%d/%m/%Y}):\n\n{facts}"}]})
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json()["content"]).strip()


def main():
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
    _, ups, downs, ext, stale, facts = build(data)
    text, mode = None, "automatico"
    if KEY:
        try:
            t = ask(facts)
            bad = grounded(t, facts)
            if t and not bad:
                text, mode = t, "ia"
            else:
                print(f"AVISO: texto da IA descartado (número fora dos fatos: {bad}).", file=sys.stderr)
        except Exception as e:
            print(f"AVISO: falha ao chamar a IA ({e}); usando resumo automático.", file=sys.stderr)
    else:
        print("Sem ANTHROPIC_API_KEY; usando resumo automático.")
    if not text:
        text = fallback(ups, downs, ext, stale)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "mode": mode,
                   "model": MODEL if mode == "ia" else None, "text": text}, f, ensure_ascii=False)
    print(f"Resumo gravado (modo {mode}).")


if __name__ == "__main__":
    main()
