"""Die zwei QT-Paarungen genauer ansehen - bevor irgendjemand sie glaubt.

WARUM UEBERHAUPT
----------------
Im Zwei-Jahres-Lauf standen zwei Paarungen im Pruefteil positiv:

    QT + SMC            45 Trades   +0,3524R   z = 1,36
    QT + ICT (London)   37 Trades   +0,4946R   z = 1,68

Keine hat die Schwelle von 2,45 erreicht. Bei sieben Versuchen ist ein
groesster z-Wert um 1,8 auch in reinem Rauschen der Normalfall - 1,68 ist
also genau das, was man ohne jeden Vorteil erwarten wuerde. Das hier ist
kein Bestaetigungslauf, sondern der Versuch, die beiden zu WIDERLEGEN.

DREI PRUEFUNGEN
---------------
1. SCHEINLAGEN. Die ganze Quartalseinteilung wird um 6, 12 und 18 Stunden
   verschoben. Mechanik identisch, Handelszahl aehnlich - nur die Uhrzeiten
   sind falsch. Wenn die echte Lage nicht deutlich heraussticht, misst die
   Strategie nicht die Quartalsstruktur, sondern irgendeinen Zeitfilter.
   Das ist die schaerfste der drei.

2. BOOTSTRAP statt z. Gewinner bringen +2R (Krypto +4R), Verlierer -1R. Die
   Verteilung ist damit stark rechtsschief, und der Standardfehler unterstellt
   eine Glockenkurve. Bei 37 Werten ist das eine schlechte Naeherung. Der
   Bootstrap zieht stattdessen 10.000 mal neu aus den echten Werten.

3. HERKUNFT. Wenn die positive Zahl aus zwei Symbolen kommt, ist sie kein
   Vorteil der Strategie, sondern eine Eigenschaft dieser zwei Symbole.

  python qt_check.py
  python qt_check.py --tf M15
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
from pairs_test import QT, SPLIT, MAX_COST_HANDICAP_PP  # noqa: E402

SHIFTS = [0, 6, 12, 18]

KANDIDATEN = [
    ("QT + SMC", dict(QT, entry_quarter="Q3", raid_window="Q2")),
    ("QT + ICT (London)", dict(QT, entry_quarter="Q3",
                               raid_window="london_kz")),
]


def trades(params, series, teil="oos"):
    """Alle Trades einer Parametrierung, je Symbol zurueckgegeben."""
    out = {}
    for sym, candles in series.items():
        cut = int(len(candles) * SPLIT)
        cs = candles[:cut] if teil == "is" else candles[cut:]
        if len(cs) < 400:
            continue
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
    return {"n": n, "mean": m, "sd": sd, "se": sd / math.sqrt(n) if n else 0.0,
            "win": sum(1 for x in rs if x > 0) / n * 100}


def bootstrap(rs, runs=10000, seed=12345):
    """Perzentil-Bootstrap. Kein Glockenkurven-Gedaechtnis noetig."""
    if len(rs) < 5:
        return None
    rnd = random.Random(seed)
    n = len(rs)
    mittel = []
    for _ in range(runs):
        mittel.append(sum(rs[rnd.randrange(n)] for _ in range(n)) / n)
    mittel.sort()
    return (mittel[int(0.025 * runs)], mittel[int(0.975 * runs)],
            sum(1 for x in mittel if x <= 0) / runs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="H1", choices=["M15", "H1"])
    ap.add_argument("--bars", type=int, default=17000)
    a = ap.parse_args()

    # Der Cache wurde beim langen Lauf frisch gefuellt - den nehmen wir,
    # statt sechs Minuten lang dieselben Kurse noch einmal zu holen.
    datafeed.CACHE_TTL[a.tf] = 86400

    print(f"\nZeitrahmen {a.tf}, nur der PRUEFTEIL "
          f"(die hinteren {(1-SPLIT)*100:.0f}%)\n")
    print(f"Lade Daten fuer {len(datafeed.ALL_SYMBOLS)} Symbole ...")
    t0 = time.time()
    series = {}
    for sym in datafeed.ALL_SYMBOLS:
        try:
            cs = datafeed.fetch(sym, a.tf, a.bars)
            if len(cs) >= 800:
                series[sym] = cs
        except Exception:
            pass
    print(f"{len(series)} Symbole in {time.time()-t0:.0f}s\n")
    if not series:
        raise SystemExit("Keine Daten.")

    for name, params in KANDIDATEN:
        print("=" * 88)
        print(f"{name}   ({a.tf}, Pruefteil)")
        print("=" * 88)

        # --- 1. Scheinlagen ------------------------------------------------
        print("\n1. ECHTE LAGE GEGEN DREI SCHEINLAGEN")
        print(f"{'Quartalslage':<22}{'Trades':>8}{'Treffer':>9}"
              f"{'R/Trade':>11}{'Stdf.':>9}   Bootstrap 95%")
        print("-" * 88)
        zeilen = []
        for sh in SHIFTS:
            je_sym = trades(dict(params, qt_shift_h=sh), series)
            rs = [r for v in je_sym.values() for r in v]
            s = stats(rs)
            b = bootstrap(rs)
            etikett = "ECHT (0h)" if sh == 0 else f"Schein (+{sh}h)"
            if not s:
                print(f"{etikett:<22}{0:>8}")
                continue
            ci = f"  {b[0]:+.3f} bis {b[1]:+.3f}" if b else "  zu wenige"
            print(f"{etikett:<22}{s['n']:>8}{s['win']:>8.1f}%"
                  f"{s['mean']:>+11.4f}{s['se']:>9.4f}{ci}")
            zeilen.append((sh, s, b, je_sym, rs))

        if zeilen:
            echt = next((z for z in zeilen if z[0] == 0), None)
            schein = [z for z in zeilen if z[0] != 0]
            print("-" * 88)
            if echt and schein:
                besser = sum(1 for z in schein if z[1]["mean"] >= echt[1]["mean"])
                sm = sum(z[1]["mean"] for z in schein) / len(schein)
                print(f"Scheinlagen im Mittel: {sm:+.4f}R   "
                      f"echte Lage: {echt[1]['mean']:+.4f}R")
                if besser == 0:
                    print("Die echte Lage ist die beste von vieren. Das ist der")
                    print("guenstigste Ausgang - beweist aber nichts: bei vier")
                    print("Versuchen ist einer zwangslaeufig der beste, und mit")
                    print("Wahrscheinlichkeit 1/4 ist es der echte durch Zufall.")
                else:
                    print(f"{besser} von 3 Scheinlagen sind gleich gut oder besser.")
                    print("Damit misst die Strategie NICHT die Quartalsstruktur.")
                    print("Was auch immer die positive Zahl erzeugt - die")
                    print("Uhrzeiten von Quarterly Theory sind es nicht.")

            # --- 2. Bootstrap-Urteil der echten Lage -----------------------
            if echt and echt[2]:
                lo, hi, p0 = echt[2]
                print("\n2. BOOTSTRAP DER ECHTEN LAGE")
                print(f"   Mittelwert {echt[1]['mean']:+.4f}R, "
                      f"95%-Bereich {lo:+.4f} bis {hi:+.4f}")
                print(f"   Anteil der Ziehungen bei oder unter null: {p0*100:.1f}%")
                if lo > 0:
                    print("   Der Bereich liegt komplett ueber null.")
                else:
                    print("   Null liegt im Bereich. Kein Nachweis.")

                # --- 3. Herkunft -------------------------------------------
                print("\n3. WOHER DIE TRADES KOMMEN (echte Lage)")
                print(f"   {'Symbol':<10}{'Gruppe':<10}{'Trades':>8}"
                      f"{'Treffer':>9}{'R/Trade':>11}")
                print("   " + "-" * 48)
                je = echt[3]
                for sym in sorted(je, key=lambda s: -sum(je[s])):
                    s2 = stats(je[sym])
                    print(f"   {sym:<10}{datafeed.group_of(sym):<10}"
                          f"{s2['n']:>8}{s2['win']:>8.1f}%{s2['mean']:>+11.4f}")
                print("   " + "-" * 48)
                paare = sorted(((sum(v), k) for k, v in je.items()),
                               reverse=True)
                ges = sum(p for p, _ in paare)
                if len(paare) >= 2 and ges != 0:
                    top2 = sum(p for p, _ in paare[:2])
                    print(f"   Die zwei besten Symbole liefern {top2:+.1f}R von "
                          f"{ges:+.1f}R gesamt ({top2/ges*100:.0f}%)")
                    print(f"   Symbole insgesamt: {len(paare)}")

                # --- 4. Wie viele Trades fehlen? ---------------------------
                sd, m = echt[1]["sd"], echt[1]["mean"]
                print("\n4. WIE VIELE PRUEF-TRADES WAEREN NOETIG")
                from statistics import NormalDist
                zs = NormalDist().inv_cdf(1 - 0.05 / 7)
                if m > 0:
                    noetig = (sd * zs / m) ** 2
                    print(f"   Bei genau diesem Vorteil ({m:+.3f}R) und dieser")
                    print(f"   Streuung ({sd:.2f}): rund {noetig:,.0f}. "
                          f"Vorhanden: {echt[1]['n']}")
                noetig10 = (sd * zs / 0.10) ** 2
                print(f"   Fuer einen Vorteil von +0,10R: rund {noetig10:,.0f}")
        print()

    print("=" * 88)
    print("WAS DIESER LAUF ENTSCHEIDEN KANN")
    print("=" * 88)
    print("Er kann WIDERLEGEN: schlagen die Scheinlagen die echte Lage, ist")
    print("Quarterly Theory als Zeitstruktur erledigt. Er kann NICHT")
    print("bestaetigen - dafuer braucht es Daten, die es noch nicht gibt,")
    print("naemlich die Zukunft. Faellt er guenstig aus, ist der naechste")
    print("Schritt ein Vorwaertstest auf Papier, kein Geld.")
    print("=" * 88 + "\n")


if __name__ == "__main__":
    main()
