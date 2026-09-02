"""Alle Kombinationen durchsuchen - aber ehrlich.

DAS PROBLEM
-----------
Wer genug Varianten durchprobiert, findet immer eine, die gut aussieht.
Bei 360 Kombinationen und reinem Rauschen zeigt der beste Kandidat im
Schnitt +0,44R - viermal mehr als jeder realistische echte Vorteil.
Den Besten herauszupicken und zu behalten ist deshalb wertlos.

DIE LOESUNG
-----------
Die Daten werden ZEITLICH geteilt:

    [========== Suche (65%) ==========][=== Pruefung (35%) ===]

Gesucht wird nur im vorderen Teil. Der hintere wird waehrend der Suche
NICHT ANGEFASST. Am Ende wird GENAU EIN Gewinner - der beste aus der
Suche - einmal auf dem hinteren Teil geprueft. Dieses eine Ergebnis ist
die Antwort, egal wie es ausfaellt.

Weil nur ein einziger Kandidat auf ungesehenen Daten geprueft wird, gilt
dort die normale Schwelle und nicht die Bonferroni-Huerde. Das ist der
ganze Trick: die Suche darf beliebig gross sein, solange die Pruefung
einmalig ist.

  python combo_search.py                  volle Suche
  python combo_search.py --bars 3000      weniger Daten, schneller
  python combo_search.py --min-trades 30  Mindestzahl je Kandidat
"""
from __future__ import annotations

import argparse
import itertools
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import backtest      # noqa: E402
import datafeed      # noqa: E402

MAX_COST_HANDICAP_PP = 100.0 / 30.0
SPLIT = 0.65                      # Anteil fuer die Suche

# --- Der Suchraum ----------------------------------------------------------
# Pool und Familie haengen zusammen: QT arbeitet per Definition mit der
# Q1-Spanne, die Session-Familie mit Sitzungsspannen, MTF mit Swings vom
# hoeheren Zeitrahmen.
POOLS = [
    ("qt_q1",      {"family": "qt"}),
    ("sess_asia",  {"family": "session", "pool": "asia_range",
                    "sweep_lookback": 48}),
    ("sess_london", {"family": "session", "pool": "london_rng",
                     "sweep_lookback": 48}),
    ("mtf_h1",     {"family": "mtf", "htf_mult": 4, "htf_pool_lookback": 30,
                    "htf_swing_n": 2, "htf_atr_len": 14,
                    "htf_min_penetration_atr": 0.2, "htf_sweep_valid_bars": 6,
                    "stop_mode": "ltf", "ifvg_max_age": 60,
                    "equal_level_tol_atr": 0.15,
                    "equal_level_min_separation": 4}),
    ("mtf_h4",     {"family": "mtf", "htf_mult": 16, "htf_pool_lookback": 30,
                    "htf_swing_n": 2, "htf_atr_len": 14,
                    "htf_min_penetration_atr": 0.2, "htf_sweep_valid_bars": 6,
                    "stop_mode": "ltf", "ifvg_max_age": 60,
                    "equal_level_tol_atr": 0.15,
                    "equal_level_min_separation": 4}),
]
ZEITEN = [("keins", {}),
          ("q3", {"entry_quarter": "Q3"}),
          ("london_kz", {"sweep_window": "london_kz"}),
          ("ny_am_kz", {"sweep_window": "ny_am_kz"})]
MSS = [("ohne", {"require_mss": False}), ("mit", {"require_mss": True})]
ZONEN = [("fvg", {"entry_zone": "fvg"}), ("ifvg", {"entry_zone": "ifvg"}),
         ("beides", {"entry_zone": "both"})]
ZIELE = [("2R", {"rr": 2.0}), ("3R", {"rr": 3.0}), ("4R", {"rr": 4.0})]

BASIS = {"atr_len": 14, "min_bars": 200, "swing_n": 2,
         "stop_buffer_atr": 0.15, "min_stop_atr": 0.3, "max_stop_atr": 6.0,
         "min_fvg_atr": 0.10, "min_raid_atr": 0.15,
         "min_sweep_penetration_atr": 0.15, "utc_offset": 0,
         "target_mode": "rr"}


def passt(pool_name, zeit_name, mss_name):
    """Nicht jede Kombination ergibt Sinn."""
    fam = dict(POOLS)[pool_name].get("family")
    if zeit_name == "q3" and fam != "qt":
        return False                      # Quartale gibt es nur bei QT
    if zeit_name in ("london_kz", "ny_am_kz") and fam != "session":
        return False                      # Killzones nur bei der Session-Familie
    if mss_name == "ohne" and fam in ("session", "mtf"):
        return False                      # dort ist der MSS fest eingebaut
    return True


def bauen():
    out = []
    for (pn, pp), (zn, zp), (mn, mp), (en, ep), (rn, rp) in itertools.product(
            POOLS, ZEITEN, MSS, ZONEN, ZIELE):
        if not passt(pn, zn, mn):
            continue
        p = dict(BASIS); p.update(pp); p.update(zp); p.update(mp)
        p.update(ep); p.update(rp)
        out.append((f"{pn}|{zn}|mss-{mn}|{en}|{rn}", p))
    return out


def bewerten(kombis, series, teil, min_trades):
    """teil = 'is' (Suche) oder 'oos' (Pruefung)."""
    erg = {}
    for name, params in kombis:
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
                grenze = MAX_COST_HANDICAP_PP / 100.0 * (p["rr"] + 1.0)
                if c <= grenze:
                    rs.append(t["r"])
        n = len(rs)
        if n < min_trades:
            continue
        m = sum(rs) / n
        var = sum((x - m) ** 2 for x in rs) / (n - 1) if n > 1 else 0.0
        se = math.sqrt(var / n) if n > 1 else 0.0
        erg[name] = {"n": n, "mean": m, "se": se,
                     "win": sum(1 for x in rs if x > 0) / n * 100}
    return erg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", type=int, default=5000)
    ap.add_argument("--min-trades", type=int, default=25)
    a = ap.parse_args()

    kombis = bauen()
    print(f"\nSuchraum: {len(kombis)} sinnvolle Kombinationen")
    print(f"Aufteilung: {SPLIT*100:.0f}% Suche, {(1-SPLIT)*100:.0f}% Pruefung "
          f"(zeitlich getrennt, Pruefteil wird bei der Suche nicht angefasst)\n")

    print(f"Lade Daten fuer {len(datafeed.ALL_SYMBOLS)} Symbole ...")
    series = {}
    for sym in datafeed.ALL_SYMBOLS:
        try:
            cs = datafeed.fetch(sym, "M15", a.bars)
            if len(cs) >= 800:
                series[sym] = cs
        except Exception:
            pass
    print(f"{len(series)} Symbole geladen\n")
    if not series:
        raise SystemExit("Keine Daten.")

    bsp = list(series.values())[0]
    cut = int(len(bsp) * SPLIT)
    print(f"Suche:    {bsp[0].ts[:10]} bis {bsp[cut-1].ts[:10]}")
    print(f"Pruefung: {bsp[cut].ts[:10]} bis {bsp[-1].ts[:10]}\n")

    t0 = time.time()
    print("Durchsuche den vorderen Teil ...")
    is_erg = bewerten(kombis, series, "is", a.min_trades)
    print(f"{len(is_erg)} Kombinationen mit genug Trades "
          f"({time.time()-t0:.0f}s)\n")
    if not is_erg:
        raise SystemExit("Keine Kombination erreicht die Mindestzahl.")

    rang = sorted(is_erg.items(), key=lambda kv: -kv[1]["mean"])
    print("=" * 78)
    print("BESTE 12 IN DER SUCHE  (das sind NOCH KEINE Ergebnisse)")
    print("=" * 78)
    print(f"{'Kombination':<44}{'Trades':>7}{'Treffer':>9}{'R/Trade':>11}")
    print("-" * 78)
    for name, v in rang[:12]:
        print(f"{name:<44}{v['n']:>7}{v['win']:>8.1f}%{v['mean']:>+11.4f}")
    print("-" * 78)
    besser = [v for _, v in rang if v["mean"] > 0]
    print(f"{len(besser)} von {len(is_erg)} Kombinationen sind in der Suche positiv.")
    print("Bei reinem Rauschen waere etwa die Haelfte positiv - diese Zahl")
    print("allein sagt also nichts.")

    gewinner, gv = rang[0]
    print("\n" + "=" * 78)
    print("DIE PRUEFUNG - genau EIN Kandidat, auf ungesehenen Daten")
    print("=" * 78)
    print(f"Gewinner der Suche: {gewinner}")
    print(f"  in der Suche:  {gv['n']} Trades, {gv['win']:.1f}% Treffer, "
          f"{gv['mean']:+.4f}R")

    params = dict(kombis)[gewinner]
    oos = bewerten([(gewinner, params)], series, "oos", 1)
    if gewinner not in oos:
        print("\n  Im Pruefzeitraum keine Trades - keine Aussage moeglich.")
        return
    o = oos[gewinner]
    lo, hi = o["mean"] - 2 * o["se"], o["mean"] + 2 * o["se"]
    print(f"  in der PRUEFUNG: {o['n']} Trades, {o['win']:.1f}% Treffer, "
          f"{o['mean']:+.4f}R")
    print(f"  Bereich (zwei Standardfehler): {lo:+.4f} bis {hi:+.4f}")

    print("\n" + "=" * 78)
    print("URTEIL")
    print("=" * 78)
    print(f"  Suche  {gv['mean']:+.4f}R   ->   Pruefung  {o['mean']:+.4f}R"
          f"   (Differenz {o['mean']-gv['mean']:+.4f})")
    if lo > 0:
        print("\n  POSITIV auf ungesehenen Daten. Das ist der erste Befund")
        print("  dieser Art. Naechster Schritt waere Vorwaertstest mit echtem")
        print("  Geldeinsatz auf Papier - nicht sofort glauben, aber ernst nehmen.")
    elif hi < 0:
        print("\n  NEGATIV auf ungesehenen Daten. Der Suchgewinner traegt nicht.")
    else:
        print("\n  Von null nicht unterscheidbar. Der Suchgewinner ist damit")
        print("  wahrscheinlich das, wonach er aussieht: der glueckliche Beste")
        print("  aus vielen Versuchen.")
    print("=" * 78 + "\n")


if __name__ == "__main__":
    main()
