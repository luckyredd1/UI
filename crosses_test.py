"""Dieselbe Regel, neunzehn Symbole, die noch NIE angefasst wurden.

WARUM DAS DER RICHTIGE NAECHSTE SCHRITT IST
-------------------------------------------
QT + SMC steht im Pruefteil bei +0,3523R auf 45 Trades. Fuer ein Urteil
braeuchte es bei dieser Streuung rund 147. Die fehlen, und aus der
Vergangenheit sind sie nicht zu holen: Yahoo gibt fuer Stundenkerzen 730
Tage her, mehr nicht.

Es gibt aber eine zweite Richtung, in der Daten ungesehen sein koennen -
nicht die Zeit, sondern das INSTRUMENT. Die neunzehn Waehrungskreuze ohne
USD wurden in diesem Projekt nie getestet. Sie sind am 02.09.2026 bewusst
aus der Handelsliste geflogen. Fuer sie ist damit die GANZE Historie
ungesehen, nicht nur die hinteren 35 Prozent.

Wenn die Regel etwas Echtes misst, muss sie auch dort auftauchen. Tut sie
es nicht, war das positive Ergebnis eine Eigenschaft der sieben
USD-Paare - und die hatten wir uns nicht ausgesucht, weil sie besonders
waren, sondern weil Yahoo sie sauber liefert.

WICHTIG: DIE SPREADS SIND ABSICHTLICH ZU HOCH ANGESETZT
-------------------------------------------------------
Kreuze kosten mehr als Majors. Gemessen wurde hier nichts, also wird
geschaetzt - und zwar nach oben, das Zwei- bis Vierfache der Majors. Ein
zu hoher Spread kann nur ein echtes Ergebnis kaputtmachen, nie ein
schlechtes schoenrechnen. Bei einer Sache, die man gerne bestaetigt haette,
ist das die richtige Richtung zu irren.

DIE KONTROLLGRUPPEN
-------------------
QT + SMC          Quartale um 6, 12, 18 Stunden verschoben
QT + ICT London   die Killzone um -3, +3, +6 Stunden verschoben

Beim zweiten war die Kontrolle im letzten Lauf WERTLOS: verschobene
Quartale erzeugten 3, 0 und 0 Trades, weil dann kein Raid mehr zwischen
Q1-Ende und Q3 liegt. Nicht die echte Lage war besser - die Scheinlagen
konnten gar nicht antreten. Deshalb wird hier stattdessen die Killzone
verschoben und die Quartale bleiben echt.

  python crosses_test.py
  python crosses_test.py --tf M15
"""
from __future__ import annotations

import argparse
import math
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import backtest      # noqa: E402
import datafeed      # noqa: E402
from pairs_test import QT, MAX_COST_HANDICAP_PP  # noqa: E402

# --- Die neunzehn Kreuze, nur fuer diesen Test ----------------------------
# Sie werden zur Laufzeit in datafeed eingehaengt, NICHT in die Datei
# geschrieben. Der Bot handelt sie weiterhin nicht.
KREUZE = {
    "EURGBP": 0.00020, "EURJPY": 0.00018, "GBPJPY": 0.00035,
    "AUDJPY": 0.00025, "CADJPY": 0.00030, "CHFJPY": 0.00035,
    "NZDJPY": 0.00035, "EURAUD": 0.00030, "EURCAD": 0.00030,
    "EURCHF": 0.00020, "GBPAUD": 0.00045, "GBPCAD": 0.00045,
    "GBPCHF": 0.00040, "AUDCAD": 0.00030, "AUDCHF": 0.00035,
    "AUDNZD": 0.00035, "NZDCAD": 0.00040, "NZDCHF": 0.00045,
    "CADCHF": 0.00035,
}
for _s, _c in KREUZE.items():
    datafeed.FOREX[_s] = _s + "=X"
    datafeed.PAPER_SPREAD_FRAC[_s] = _c

BASIS = dict(QT, entry_quarter="Q3")

# (Ueberschrift, echte Parameter, [(Etikett, Scheinparameter), ...])
TESTS = [
    ("QT + SMC",
     dict(BASIS, raid_window="Q2"),
     [(f"Schein Quartale +{h}h", dict(BASIS, raid_window="Q2", qt_shift_h=h))
      for h in (6, 12, 18)]),
    ("QT + ICT (London)",
     dict(BASIS, raid_window="london_kz"),
     [("Schein Zone 04-07", dict(BASIS, raid_window=(4, 7))),
      ("Schein Zone 10-13", dict(BASIS, raid_window=(10, 13))),
      ("Schein Zone 13-16", dict(BASIS, raid_window=(13, 16)))]),
]


def trades(params, series):
    """Ganze Historie - fuer diese Symbole ist alles ungesehen."""
    out = {}
    for sym, cs in series.items():
        p = dict(params)
        p["rr"] = datafeed.rr_for(sym, float(p.get("rr", 2.0)))
        p["spread_price"] = datafeed.paper_spread(sym, cs[-1].close)
        try:
            res = backtest.run(cs, p)
        except Exception:
            continue
        rs = []
        for t in res.get("trades_list", []):
            risk = t.get("risk") or 0
            if risk <= 0:
                continue
            c = datafeed.paper_spread(sym, t["entry"]) / risk
            if c <= MAX_COST_HANDICAP_PP / 100.0 * (p["rr"] + 1.0):
                rs.append(t["r"])
        if rs:
            out[sym] = rs
    return out


def stats(rs):
    n = len(rs)
    if not n:
        return None
    m = sum(rs) / n
    var = sum((x - m) ** 2 for x in rs) / (n - 1) if n > 1 else 0.0
    sd = math.sqrt(var)
    return {"n": n, "mean": m, "sd": sd, "se": sd / math.sqrt(n),
            "win": sum(1 for x in rs if x > 0) / n * 100}


def bootstrap(rs, runs=10000, seed=12345):
    if len(rs) < 5:
        return None
    rnd = random.Random(seed)
    n = len(rs)
    mi = [sum(rs[rnd.randrange(n)] for _ in range(n)) / n for _ in range(runs)]
    mi.sort()
    return (mi[int(0.025 * runs)], mi[int(0.975 * runs)],
            sum(1 for x in mi if x <= 0) / runs)


def robust(rs):
    """Was bleibt, wenn man den groessten Gewinner und die zwei groessten
    Gewinner streicht? Ein Ergebnis, das an zwei Trades haengt, ist keins."""
    if len(rs) < 10:
        return None
    s = sorted(rs, reverse=True)
    return (sum(s[1:]) / len(s[1:]), sum(s[2:]) / len(s[2:]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="H1", choices=["M15", "H1"])
    ap.add_argument("--bars", type=int, default=17000)
    a = ap.parse_args()

    from statistics import NormalDist
    # Zwei Regeln, jede einmal auf ungesehenen Symbolen geprueft.
    schwelle = NormalDist().inv_cdf(1 - 0.05 / 2)

    print(f"\nZeitrahmen {a.tf}. {len(KREUZE)} Waehrungskreuze, die in diesem")
    print("Projekt noch nie getestet wurden - GANZE Historie ist ungesehen.")
    print(f"Zwei Regeln, Schwelle nach Korrektur |z| > {schwelle:.2f}\n")

    print(f"Lade {len(KREUZE)} Symbole ...")
    t0 = time.time()
    series = {}
    for i, sym in enumerate(sorted(KREUZE), 1):
        print(f"  [{i}/{len(KREUZE)}] {sym}   ", end="\r", flush=True)
        try:
            cs = datafeed.fetch(sym, a.tf, a.bars)
            if len(cs) >= 800:
                series[sym] = cs
        except Exception as e:
            print(f"  {sym} FEHLER {str(e)[:40]}")
    print(" " * 60, end="\r")
    print(f"{len(series)} Symbole in {time.time()-t0:.0f}s")
    if not series:
        raise SystemExit("Keine Daten.")
    bsp = max(series.values(), key=len)
    print(f"Zeitraum: {bsp[0].ts[:10]} bis {bsp[-1].ts[:10]}\n")

    for titel, echt_p, scheine in TESTS:
        print("=" * 88)
        print(f"{titel}   -   {len(series)} ungesehene Kreuze, {a.tf}")
        print("=" * 88)
        je_sym = trades(echt_p, series)
        rs = [r for v in je_sym.values() for r in v]
        s = stats(rs)
        if not s:
            print("Keine Trades.\n")
            continue

        print(f"{'Lage':<22}{'Trades':>8}{'Treffer':>9}{'R/Trade':>11}"
              f"{'Stdf.':>9}{'z':>8}")
        print("-" * 88)
        zz = s["mean"] / s["se"] if s["se"] else 0.0
        print(f"{'ECHT':<22}{s['n']:>8}{s['win']:>8.1f}%{s['mean']:>+11.4f}"
              f"{s['se']:>9.4f}{zz:>8.2f}")
        schein_m = []
        for etikett, sp in scheine:
            r2 = [r for v in trades(sp, series).values() for r in v]
            s2 = stats(r2)
            if not s2:
                print(f"{etikett:<22}{0:>8}   (keine Trades - Kontrolle wertlos)")
                continue
            schein_m.append(s2["mean"])
            print(f"{etikett:<22}{s2['n']:>8}{s2['win']:>8.1f}%"
                  f"{s2['mean']:>+11.4f}{s2['se']:>9.4f}")
        print("-" * 88)

        b = bootstrap(rs)
        if b:
            print(f"Bootstrap 95%: {b[0]:+.4f} bis {b[1]:+.4f}   "
                  f"(Ziehungen <= 0: {b[2]*100:.1f}%)")
        rb = robust(rs)
        if rb:
            print(f"Ohne den groessten Gewinner: {rb[0]:+.4f}R   "
                  f"ohne die zwei groessten: {rb[1]:+.4f}R")
        if schein_m:
            besser = sum(1 for m in schein_m if m >= s["mean"])
            print(f"Scheinlagen im Mittel: {sum(schein_m)/len(schein_m):+.4f}R"
                  f"   davon >= echt: {besser} von {len(schein_m)}")

        print("\nURTEIL")
        if abs(zz) < schwelle:
            print(f"  |z| = {abs(zz):.2f} < {schwelle:.2f} - kein Nachweis.")
        elif zz > 0:
            print(f"  z = {zz:.2f} - POSITIV auf ungesehenen Symbolen.")
            print("  Das ist der erste Befund dieser Art im ganzen Projekt.")
            print("  Naechster Schritt: Vorwaertstest auf Papier, kein Geld.")
        else:
            print(f"  z = {zz:.2f} - klar negativ. Die Regel traegt nicht.")

        top = sorted(((sum(v), k, len(v)) for k, v in je_sym.items()),
                     reverse=True)
        ges = sum(t[0] for t in top)
        if len(top) >= 3 and ges:
            d3 = sum(t[0] for t in top[:3])
            print(f"  Die drei besten von {len(top)} Symbolen liefern "
                  f"{d3:+.1f}R von {ges:+.1f}R ({d3/ges*100:.0f}%)")
        print()

    print("=" * 88)
    print("WIE DAS ZU LESEN IST")
    print("=" * 88)
    print("Diese Symbole wurden nie zur Auswahl benutzt. Ein positives")
    print("Ergebnis hier ist deshalb deutlich mehr wert als das auf den")
    print("sieben USD-Paaren - dort steckte die Auswahl von sieben Paarungen")
    print("und vier Quartalslagen drin. Es bleibt trotzdem Vergangenheit.")
    print("=" * 88 + "\n")


if __name__ == "__main__":
    main()
