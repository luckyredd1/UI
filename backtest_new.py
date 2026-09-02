"""Backtest des NEUEN Aufbaus: 22 Symbole, 5 vorab festgelegte Kandidaten,
Kostengrenze als Nachteil von 3,33 Prozentpunkten.

WAS DIESER TEST KANN UND WAS NICHT
----------------------------------
Er kann die Strategie WIDERLEGEN, nicht bestaetigen. Der Unterschied zu den
89 Hypothesen davor: dort wurde aus vielen Varianten die beste behalten, und
bei genug Varianten sieht immer eine gut aus. Hier steht alles vorher fest -
es gibt nichts auszuwaehlen. Ein klar negatives Ergebnis ueber viele Trades
ist damit aussagekraeftig, ein positives nicht.

Operative Fragen beantwortet er dagegen zuverlaessig:
  - wie viele Trades pro Woche sind zu erwarten?
  - was entfernt die Kostengrenze tatsaechlich?
  - welche Symbole liefern ueberhaupt Signale?

  python backtest_new.py                  60 Tage, alle Kandidaten
  python backtest_new.py --bars 3000      weniger Daten, schneller
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import backtest      # noqa: E402
import datafeed      # noqa: E402
from forward import CANDIDATES  # noqa: E402

# Quarterly Theory laeuft NUR im Test mit. forward.py und damit der
# Live-Bot bleiben unveraendert, bis dieser Test etwas gezeigt hat.
QT_BASE = {"family": "qt", "rr": 2.0, "atr_len": 14, "min_bars": 200,
           "min_raid_atr": 0.15, "min_fvg_atr": 0.10,
           "stop_buffer_atr": 0.15, "min_stop_atr": 0.3, "max_stop_atr": 6.0}
QT_CANDIDATES = [
    ("qt_q3", "M15", dict(QT_BASE), "Quarterly Theory: Raid in Q2, Einstieg in Q3"),
    ("qt_any", "M15", dict(QT_BASE, entry_quarter=None),
     "KONTROLLE: gleicher Aufbau, Einstieg in jedem Quartal"),
    # Die Kombination: QT-Zeitstruktur plus den Bestaetigungsschritt aus
    # SMC/ICT. qt_q3 handelt jeden Raid; qt_mss verlangt zusaetzlich einen
    # Strukturbruch, bevor eingestiegen wird.
    ("qt_mss", "M15", dict(QT_BASE, require_mss=True, swing_n=2),
     "QT + SMC: Raid in Q2, Strukturbruch, dann Einstieg in Q3"),
    ("qt_mss_any", "M15", dict(QT_BASE, require_mss=True, swing_n=2,
                               entry_quarter=None),
     "KONTROLLE zu qt_mss: gleicher Aufbau ohne Quartalsbedingung"),
]
ALLE_KANDIDATEN = list(CANDIDATES) + QT_CANDIDATES

MAX_COST_HANDICAP_PP = 100.0 / 30.0


def fetch_all(bars, verbose=True):
    series = {}
    for i, sym in enumerate(datafeed.ALL_SYMBOLS, 1):
        if verbose:
            print(f"  [{i}/{len(datafeed.ALL_SYMBOLS)}] {sym:<9}", end="\r", flush=True)
        try:
            cs = datafeed.fetch(sym, "M15", bars)
            if len(cs) >= 320:
                series[sym] = cs
        except Exception as e:
            if verbose:
                print(f"  {sym:<9} FEHLER: {str(e)[:50]}")
    if verbose:
        print(" " * 60, end="\r")
    return series


def summarise(rows, titel):
    n = len(rows)
    if not n:
        print(f"{titel:<28}{0:>8}{'-':>10}{'-':>13}{'-':>12}")
        return None
    rs = [r["r"] for r in rows]
    mean = sum(rs) / n
    var = sum((x - mean) ** 2 for x in rs) / (n - 1) if n > 1 else 0.0
    se = math.sqrt(var / n) if n > 1 else 0.0
    wins = sum(1 for x in rs if x > 0)
    print(f"{titel:<28}{n:>8}{wins/n*100:>9.1f}%{mean:>+13.4f}{se:>12.4f}")
    return {"n": n, "mean": mean, "se": se, "sum": sum(rs)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", type=int, default=5000)
    a = ap.parse_args()

    print(f"\nLade M15-Daten fuer {len(datafeed.ALL_SYMBOLS)} Symbole ...")
    t0 = time.time()
    series = fetch_all(a.bars)
    print(f"{len(series)} Symbole geladen in {time.time()-t0:.0f}s\n")
    if not series:
        raise SystemExit("Keine Daten. Internetzugang pruefen.")

    span = {s: (c[0].ts[:10], c[-1].ts[:10], len(c)) for s, c in series.items()}
    ex = list(span.items())[0]
    print(f"Zeitraum Beispiel {ex[0]}: {ex[1][0]} bis {ex[1][1]} ({ex[1][2]} Balken)\n")

    alle, gefiltert = [], []
    for cid, _tf, params, _why in ALLE_KANDIDATEN:
        for sym, candles in series.items():
            p = dict(params)
            p["utc_offset"] = 0
            p["rr"] = datafeed.rr_for(sym, float(p.get("rr", 2.0)))
            p["spread_price"] = datafeed.paper_spread(sym, candles[-1].close)
            try:
                res = backtest.run(candles, p)
            except Exception:
                continue
            for t in res.get("trades_list", []):
                risk = t.get("risk") or 0
                if risk <= 0:
                    continue
                cost_r = datafeed.paper_spread(sym, t["entry"]) / risk
                rr_used = datafeed.rr_for(sym)
                cost_limit = MAX_COST_HANDICAP_PP / 100.0 * (rr_used + 1.0)
                rec = {"cand": cid, "symbol": sym, "group": datafeed.group_of(sym),
                       "r": t["r"], "cost_r": cost_r,
                       "stop_pct": risk / t["entry"] * 100 if t["entry"] else 0}
                rec["ok"] = cost_r <= cost_limit
                alle.append(rec)
                if rec["ok"]:
                    gefiltert.append(rec)

    if not alle:
        raise SystemExit("Keine Trades erzeugt.")

    print("=" * 74)
    print("WIRKUNG DER KOSTENGRENZE (3,33 Prozentpunkte Nachteil)")
    print("=" * 74)
    print(f"{'':<28}{'Trades':>8}{'Treffer':>10}{'R/Trade':>13}{'Standardf.':>12}")
    print("-" * 74)
    ohne = summarise(alle, "ohne Grenze (alle)")
    mit = summarise(gefiltert, "mit Kostengrenze")
    entfernt = [r for r in alle if not r["ok"]]
    summarise(entfernt, "  davon entfernt")
    print("-" * 74)
    if ohne and mit:
        print(f"Die Grenze entfernt {len(entfernt)} von {len(alle)} Trades "
              f"({len(entfernt)/len(alle)*100:.0f}%)")
        k_alle = sum(r["cost_r"] for r in alle) / len(alle)
        k_mit = (sum(r["cost_r"] for r in gefiltert) / len(gefiltert)) if gefiltert else 0
        print(f"Durchschnittskosten: {k_alle:.3f}R  ->  {k_mit:.3f}R")
        print("(noetige Trefferquote haengt vom Ziel ab: 2R bei Forex/ETF, "
              "4R bei Krypto)")

    for titel, rows in [("JE KANDIDAT (nach Kostengrenze)", gefiltert)]:
        print("\n" + "=" * 74)
        print(titel)
        print("=" * 74)
        print(f"{'':<28}{'Trades':>8}{'Treffer':>10}{'R/Trade':>13}{'Standardf.':>12}")
        print("-" * 74)
        for cid, _t, _p, _w in ALLE_KANDIDATEN:
            summarise([r for r in rows if r["cand"] == cid], cid)

    print("\n" + "=" * 74)
    print("JE GRUPPE (nach Kostengrenze)")
    print("=" * 74)
    print(f"{'':<28}{'Trades':>8}{'Treffer':>10}{'R/Trade':>13}{'Standardf.':>12}")
    print("-" * 74)
    for g in sorted({r["group"] for r in gefiltert}):
        summarise([r for r in gefiltert if r["group"] == g], g)

    # --- Was passiert, wenn man Teile weglaesst? -------------------------
    print("\n" + "=" * 74)
    print("HERKUNFT DER TRADES (Kandidat x Gruppe, nach Kostengrenze)")
    print("=" * 74)
    groups = sorted({r["group"] for r in gefiltert})
    print(f"{'':<18}" + "".join(f"{g:>12}" for g in groups) + f"{'Summe':>9}")
    print("-" * 74)
    for cid, _t, _p, _w in ALLE_KANDIDATEN:
        zeile = [len([r for r in gefiltert if r["cand"] == cid and r["group"] == g])
                 for g in groups]
        print(f"{cid:<18}" + "".join(f"{n:>12}" for n in zeile)
              + f"{sum(zeile):>9}")

    print("\n" + "=" * 74)
    print("VERGLEICH: WAS BLEIBT, WENN MAN WEGLAESST")
    print("=" * 74)
    print(f"{'':<34}{'Trades':>8}{'Treffer':>10}{'R/Trade':>13}{'Standardf.':>12}")
    print("-" * 74)
    varianten = [
        ("alles (Ausgangslage)", lambda r: True),
        ("ohne Krypto", lambda r: r["group"] != "CRYPTO"),
        ("ohne sess_london_asia", lambda r: r["cand"] != "sess_london_asia"),
        ("ohne beide", lambda r: r["group"] != "CRYPTO"
                                 and r["cand"] != "sess_london_asia"),
        ("nur qt_q3", lambda r: r["cand"] == "qt_q3"),
        ("nur qt_any (Kontrolle)", lambda r: r["cand"] == "qt_any"),
    ]
    ergebnisse = {}
    for name, f in varianten:
        ergebnisse[name] = summarise([r for r in gefiltert if f(r)], name)
    print("-" * 74)
    print("ACHTUNG: Diese Auswahl erfolgt NACH dem Blick auf die Zahlen.")
    print("Dass die uebrigbleibende Menge besser aussieht, ist teilweise")
    print("zwangslaeufig - man entfernt ja das Schlechteste. Aussagekraft hat")
    print("nur, dass beide Ausschluesse vorher begruendet waren: Krypto ueber")
    print("die angemeldete Bedingung, sess_london_asia ueber seinen eigenen")
    print("Bereich, der komplett unter null liegt.")

    print("\n" + "=" * 74)
    print("URTEIL")
    print("=" * 74)
    if mit:
        lo, hi = mit["mean"] - 2 * mit["se"], mit["mean"] + 2 * mit["se"]
        print(f"R pro Trade nach Kostengrenze: {mit['mean']:+.4f}")
        print(f"  Bereich (zwei Standardfehler): {lo:+.4f} bis {hi:+.4f}")
        if hi < 0:
            print("\n  KLAR NEGATIV. Das ist eine Widerlegung - der Test kann das,")
            print("  weil nichts nachtraeglich ausgewaehlt wurde.")
        elif lo > 0:
            print("\n  Positiv, aber das bestaetigt nichts. Es ist dieselbe")
            print("  Kurshistorie wie bei den 89 Hypothesen davor. Nur ein")
            print("  Vorwaertstest auf ungesehenen Daten zaehlt.")
        else:
            print("\n  Von null nicht unterscheidbar. Keine Aussage moeglich -")
            print("  weder dafuer noch dagegen.")
    print("=" * 74 + "\n")


if __name__ == "__main__":
    main()
