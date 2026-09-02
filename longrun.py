"""Alles nochmal - aber über zwei Jahre statt zwei Monate.

WARUM STUNDEN STATT 15 MINUTEN
------------------------------
Yahoo gibt für Minutenauflösung nur 60 Tage her, für Stundenauflösung
dagegen 730. Das ist zwölfmal mehr Historie. Dazu kommt: der Stop-Abstand
wächst etwa mit der Wurzel der Zeit, also sind die Kosten in R auf H1 rund
halb so gross wie auf M15.

Beides zusammen ist genau der Grund, warum die letzte Auswertung nichts
entscheiden konnte: 26 Tage Prüfzeitraum ergaben 2 bis 25 Trades je
Paarung. Für einen Vorteil von +0,10R bräuchte es rund 865.

WAS HIER LÄUFT
--------------
Dieselben sieben Paarungen wie in pairs_test.py, dieselbe Zeitteilung,
dieselben Schwellen - nur auf H1 über zwei Jahre. Zusätzlich als Vergleich
dieselben Paarungen auf M15, damit man den Unterschied sieht.

  python longrun.py                 H1 ueber zwei Jahre
  python longrun.py --tf M15        zum Vergleich
  python longrun.py --bars 8000     weniger Daten, schneller
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
from pairs_test import PAARE, SPLIT, MAX_COST_HANDICAP_PP  # noqa: E402

MIN_URTEIL = 20


def laden(tf, bars):
    series = {}
    n = len(datafeed.ALL_SYMBOLS)
    for i, sym in enumerate(datafeed.ALL_SYMBOLS, 1):
        print(f"  [{i}/{n}] {sym:<9}", end="\r", flush=True)
        try:
            cs = datafeed.fetch(sym, tf, bars)
            if len(cs) >= 800:
                series[sym] = cs
        except Exception as e:
            print(f"  {sym:<9} FEHLER {str(e)[:40]}")
    print(" " * 60, end="\r")
    return series


def bewerten(params, series, teil):
    rs, je_sym = [], {}
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
        k = 0
        for t in res.get("trades_list", []):
            risk = t.get("risk") or 0
            if risk <= 0:
                continue
            c = datafeed.paper_spread(sym, t["entry"]) / risk
            if c <= MAX_COST_HANDICAP_PP / 100.0 * (p["rr"] + 1.0):
                rs.append(t["r"]); k += 1
        if k:
            je_sym[sym] = k
    n = len(rs)
    if not n:
        return None
    m = sum(rs) / n
    var = sum((x - m) ** 2 for x in rs) / (n - 1) if n > 1 else 0.0
    se = math.sqrt(var / n) if n > 1 else 0.0
    return {"n": n, "mean": m, "se": se, "syms": len(je_sym),
            "win": sum(1 for x in rs if x > 0) / n * 100}


def z(v):
    return f"{'-':>7}{'-':>9}{'-':>11}{'-':>9}" if not v else \
        f"{v['n']:>7}{v['win']:>8.1f}%{v['mean']:>+11.4f}{v['se']:>9.4f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="H1", choices=["M15", "H1"])
    ap.add_argument("--bars", type=int, default=17000)
    a = ap.parse_args()

    from statistics import NormalDist
    schwelle = NormalDist().inv_cdf(1 - 0.05 / len(PAARE))
    print(f"\nZeitrahmen {a.tf}, bis zu {a.bars:,} Balken je Symbol")
    print(f"{len(PAARE)} Paarungen, Schwelle |z| > {schwelle:.2f}\n")

    # Der Plattencache haelt H1 rund eine Stunde. Fuer diesen Lauf wollen wir
    # aber garantiert die volle Historie und nicht einen alten Ausschnitt, der
    # noch mit der 60-Tage-Grenze geholt wurde. Also einmal frisch.
    datafeed.CACHE_TTL[a.tf] = 0

    print(f"Lade Daten fuer {len(datafeed.ALL_SYMBOLS)} Symbole ...")
    t0 = time.time()
    series = laden(a.tf, a.bars)
    print(f"{len(series)} Symbole in {time.time()-t0:.0f}s\n")
    if not series:
        raise SystemExit("Keine Daten.")

    laengen = sorted((len(c), s) for s, c in series.items())
    bsp = series[laengen[-1][1]]
    cut = int(len(bsp) * SPLIT)
    tage = (len(bsp) * {"M15": 15, "H1": 60}[a.tf]) / (60 * 24)
    print(f"Laengster Verlauf: {laengen[-1][1]} mit {len(bsp):,} Balken "
          f"= rund {tage:,.0f} Tage")
    print(f"  Suche:    {bsp[0].ts[:10]} bis {bsp[cut-1].ts[:10]}")
    print(f"  Pruefung: {bsp[cut].ts[:10]} bis {bsp[-1].ts[:10]}")
    print(f"Kuerzester: {laengen[0][1]} mit {laengen[0][0]:,} Balken\n")

    erg = []
    for name, was, params in PAARE:
        params = dict(params)
        if "htf_mult" in params:
            # In PAARE steht der Faktor fuer M15 (16 x 15min = H4). Auf H1
            # muss er mitwandern, sonst waere der hoehere Zeitrahmen 16 Stunden.
            params["htf_mult"] = {"M15": 16, "H1": 4}[a.tf]
        erg.append((name, bewerten(params, series, "is"),
                    bewerten(params, series, "oos")))
        print(f"  {name:<32} fertig", end="\r", flush=True)
    print(" " * 60, end="\r")

    print("=" * 94)
    print(f"SUCHTEIL ({a.tf})  - nur zur Ansicht")
    print("=" * 94)
    print(f"{'Paarung':<30}{'Trades':>7}{'Treffer':>9}{'R/Trade':>11}{'Stdf.':>9}")
    print("-" * 94)
    for name, i_, _o in erg:
        print(f"{name:<30}{z(i_)}")

    print("\n" + "=" * 94)
    print(f"PRUEFTEIL ({a.tf}) - ungesehene Daten. DAS ist die Antwort.")
    print("=" * 94)
    print(f"{'Paarung':<30}{'Trades':>7}{'Treffer':>9}{'R/Trade':>11}{'Stdf.':>9}"
          f"{'z':>7}  Urteil")
    print("-" * 94)
    for name, _i, o_ in erg:
        if not o_ or o_["se"] <= 0 or o_["n"] < MIN_URTEIL:
            print(f"{name:<30}{z(o_)}{'-':>7}  "
                  f"nur {o_['n'] if o_ else 0} Trades - kein Urteil")
            continue
        zz = o_["mean"] / o_["se"]
        u = ("TRAEGT" if zz > schwelle else
             "klar negativ" if zz < -schwelle else
             "nicht von null zu trennen")
        print(f"{name:<30}{z(o_)}{zz:>7.2f}  {u}")

    print("\n" + "=" * 94)
    print("ABSTAND SUCHE -> PRUEFUNG")
    print("=" * 94)
    print(f"{'Paarung':<30}{'Suche':>11}{'Pruefung':>12}{'Differenz':>12}")
    print("-" * 94)
    d = []
    for name, i_, o_ in erg:
        if i_ and o_:
            x = o_["mean"] - i_["mean"]; d.append(x)
            print(f"{name:<30}{i_['mean']:>+11.4f}{o_['mean']:>+12.4f}{x:>+12.4f}")
    if d:
        print("-" * 94)
        print(f"{'Mittelwert':<30}{'':>23}{sum(d)/len(d):>+12.4f}")

    ns = [o["n"] for _n, _i, o in erg if o]
    print("\n" + "=" * 94)
    print("REICHT DIE DATENMENGE JETZT?")
    print("=" * 94)
    if ns:
        print(f"  Pruef-Trades je Paarung: {min(ns)} bis {max(ns)}, "
              f"im Mittel {sum(ns)/len(ns):.0f}")
    print(f"  Noetig fuer einen Vorteil von +0,10R bei Schwelle {schwelle:.2f}: "
          f"rund {(1.2/(0.10/schwelle))**2:,.0f} Trades")
    print(f"  Noetig fuer +0,20R: rund {(1.2/(0.20/schwelle))**2:,.0f}")
    print("=" * 94 + "\n")


if __name__ == "__main__":
    main()
