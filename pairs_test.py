"""Die Frameworks paarweise kreuzen - jede Paarung einzeln geprüft.

Nicht das grosse Raster, sondern gezielte Zweierkombinationen:

    SMC allein            Struktur + Luecke, ohne Zeitbedingung  (Grundlinie)
    ICT-Session + SMC     Sitzungsspanne, Raid in der Killzone, Strukturbruch
    QT + SMC              Q1-Spanne, Raid in Q2, Strukturbruch
    QT + ICT              Q1-Spanne, aber Raid in der ICT-Killzone
    ICT-MTF + SMC         Swing vom hoeheren Zeitrahmen, Strukturbruch

Jede Paarung wird auf dem Suchteil UND auf dem Pruefteil gerechnet. Die
Zahl aus dem Pruefteil ist die Antwort - der Suchteil steht nur daneben,
damit man sieht, wie weit die beiden auseinanderlaufen.

WICHTIG ZUR SCHWELLE
--------------------
Hier werden mehrere Paarungen auf ungesehenen Daten geprueft, nicht nur
eine. Damit gilt wieder eine Korrektur: bei 7 Paarungen liegt die ehrliche
Schwelle bei |z| > 2,69 statt 1,96. Wer aus sieben Versuchen den besten
nimmt, findet auch in reinem Rauschen einen guten.

  python pairs_test.py
  python pairs_test.py --bars 3000
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

MAX_COST_HANDICAP_PP = 100.0 / 30.0
SPLIT = 0.65

SMC = {"atr_len": 14, "min_bars": 200, "swing_n": 2, "stop_buffer_atr": 0.15,
       "min_stop_atr": 0.3, "max_stop_atr": 6.0, "min_fvg_atr": 0.10,
       "entry_zone": "both", "utc_offset": 0, "rr": 2.0}
SESS = dict(SMC, family="session", sweep_lookback=48,
            min_sweep_penetration_atr=0.15, target_mode="rr")
QT = dict(SMC, family="qt", min_raid_atr=0.15, require_mss=True)
MTF = dict(SMC, family="mtf", htf_pool_lookback=30, htf_swing_n=2,
           htf_atr_len=14, htf_min_penetration_atr=0.2,
           htf_sweep_valid_bars=6, stop_mode="ltf", ifvg_max_age=60,
           equal_level_tol_atr=0.15, equal_level_min_separation=4)

# Jede Paarung: Name, Was steckt drin, Parameter
PAARE = [
    ("SMC allein (Grundlinie)",
     "Asien-Spanne, Raid jederzeit, Strukturbruch, FVG",
     dict(SESS, pool="asia_range", sweep_window=None)),

    ("ICT-Session + SMC (London)",
     "Asien-Spanne, Raid in der London-Killzone, Strukturbruch",
     dict(SESS, pool="asia_range", sweep_window="london_kz")),

    ("ICT-Session + SMC (NY)",
     "London-Spanne, Raid in der NY-AM-Killzone, Strukturbruch",
     dict(SESS, pool="london_rng", sweep_window="ny_am_kz")),

    ("QT + SMC",
     "Q1-Spanne, Raid in Q2, Strukturbruch, Einstieg in Q3",
     dict(QT, entry_quarter="Q3", raid_window="Q2")),

    ("QT + ICT (London)",
     "Q1-Spanne, aber Raid in der London-Killzone statt Q2",
     dict(QT, entry_quarter="Q3", raid_window="london_kz")),

    ("QT + ICT (NY)",
     "Q1-Spanne, Raid in der NY-AM-Killzone",
     dict(QT, entry_quarter="Q3", raid_window="ny_am_kz")),

    ("ICT-MTF + SMC",
     "H4-Swing als Ziel, Strukturbruch, FVG auf M15",
     dict(MTF, htf_mult=16, skip_hours=[22, 23, 0, 1, 2, 3, 4, 5])),
]


def bewerten(params, series, teil, min_trades=1):
    rs = []
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
        for t in res.get("trades_list", []):
            risk = t.get("risk") or 0
            if risk <= 0:
                continue
            c = datafeed.paper_spread(sym, t["entry"]) / risk
            if c <= MAX_COST_HANDICAP_PP / 100.0 * (p["rr"] + 1.0):
                rs.append(t["r"])
    n = len(rs)
    if n < min_trades:
        return None
    m = sum(rs) / n
    var = sum((x - m) ** 2 for x in rs) / (n - 1) if n > 1 else 0.0
    se = math.sqrt(var / n) if n > 1 else 0.0
    return {"n": n, "mean": m, "se": se,
            "win": sum(1 for x in rs if x > 0) / n * 100}


def zeile(v):
    if not v:
        return f"{'-':>7}{'-':>9}{'-':>11}{'-':>9}"
    return f"{v['n']:>7}{v['win']:>8.1f}%{v['mean']:>+11.4f}{v['se']:>9.4f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", type=int, default=5000)
    a = ap.parse_args()

    from statistics import NormalDist
    schwelle = NormalDist().inv_cdf(1 - 0.05 / len(PAARE))

    print(f"\n{len(PAARE)} Paarungen. Ehrliche Schwelle nach Korrektur: "
          f"|z| > {schwelle:.2f}\n")
    print(f"Lade Daten fuer {len(datafeed.ALL_SYMBOLS)} Symbole ...")
    series = {}
    for sym in datafeed.ALL_SYMBOLS:
        try:
            cs = datafeed.fetch(sym, "M15", a.bars)
            if len(cs) >= 800:
                series[sym] = cs
        except Exception:
            pass
    print(f"{len(series)} Symbole geladen")
    if not series:
        raise SystemExit("Keine Daten.")
    bsp = list(series.values())[0]
    cut = int(len(bsp) * SPLIT)
    print(f"Suche:    {bsp[0].ts[:10]} bis {bsp[cut-1].ts[:10]}")
    print(f"Pruefung: {bsp[cut].ts[:10]} bis {bsp[-1].ts[:10]}\n")

    t0 = time.time()
    ergebnisse = []
    for name, was, params in PAARE:
        i_ = bewerten(params, series, "is")
        o_ = bewerten(params, series, "oos")
        ergebnisse.append((name, was, i_, o_))
        print(f"  {name:<30} fertig", end="\r", flush=True)
    print(" " * 60, end="\r")
    print(f"gerechnet in {time.time()-t0:.0f}s\n")

    print("=" * 92)
    print("SUCHTEIL  (nur zur Ansicht - hier wurde nichts ausgewaehlt)")
    print("=" * 92)
    print(f"{'Paarung':<30}{'Trades':>7}{'Treffer':>9}{'R/Trade':>11}{'Stdf.':>9}")
    print("-" * 92)
    for name, _w, i_, _o in ergebnisse:
        print(f"{name:<30}{zeile(i_)}")

    print("\n" + "=" * 92)
    print("PRUEFTEIL - ungesehene Daten. DAS ist die Antwort.")
    print("=" * 92)
    print(f"{'Paarung':<30}{'Trades':>7}{'Treffer':>9}{'R/Trade':>11}{'Stdf.':>9}"
          f"{'z':>7}  Urteil")
    print("-" * 92)
    MIN_URTEIL = 20        # darunter ist jedes Urteil Zufall
    for name, _w, i_, o_ in ergebnisse:
        if not o_ or o_["se"] <= 0 or o_["n"] < MIN_URTEIL:
            n_ = o_["n"] if o_ else 0
            print(f"{name:<30}{zeile(o_)}{'-':>7}  "
                  f"nur {n_} Trades - kein Urteil moeglich")
            continue
        z = o_["mean"] / o_["se"]
        if z > schwelle:
            u = "TRAEGT"
        elif z < -schwelle:
            u = "klar negativ"
        else:
            u = "nicht von null zu trennen"
        print(f"{name:<30}{zeile(o_)}{z:>7.2f}  {u}")

    print("\n" + "=" * 92)
    print("ABSTAND ZWISCHEN SUCHE UND PRUEFUNG")
    print("=" * 92)
    print(f"{'Paarung':<30}{'Suche':>11}{'Pruefung':>12}{'Differenz':>12}")
    print("-" * 92)
    diffs = []
    for name, _w, i_, o_ in ergebnisse:
        if i_ and o_:
            d = o_["mean"] - i_["mean"]
            diffs.append(d)
            print(f"{name:<30}{i_['mean']:>+11.4f}{o_['mean']:>+12.4f}{d:>+12.4f}")
    if diffs:
        print("-" * 92)
        print(f"{'Mittelwert der Differenzen':<30}{'':>11}{'':>12}"
              f"{sum(diffs)/len(diffs):>+12.4f}")
        print("\nEin durchgehend negativer Abstand heisst: was im Suchteil gut")
        print("aussah, war Anpassung an die Vergangenheit und nicht mehr.")
    print("=" * 92 + "\n")


if __name__ == "__main__":
    main()
