"""Warum sind die Stops so eng, und was kostet das?

Kein Optimierer. Dieses Skript sucht NICHT die Schwelle mit der besten
Rendite - das waere auf 27 Trades reines Kurvenanpassen. Es zeigt nur, was
mechanisch feststeht: wie viel vom Risiko der Spread frisst, und wie eng die
Stops im Verhaeltnis zur Schwankungsbreite (ATR) gesetzt werden.

Aus diesen Zahlen leiten wir die Regel ab - nicht aus der Rendite.

  python diag_stops.py                 Buch automatisch finden
  python diag_stops.py --url ADRESSE   vom Handy holen
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import datafeed  # noqa: E402


def load_book(path=None, url=None):
    if url:
        req = urllib.request.Request(url, headers={"User-Agent": "diag"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode()), url
    for p in [path, os.path.join(HERE, "paper_book.json"),
              os.path.join(os.path.dirname(HERE), "paper_book.json")]:
        if p and os.path.exists(p):
            return json.load(open(p, encoding="utf-8")), p
    src = os.path.join(HERE, "paper_source.txt")
    if os.path.exists(src):
        for line in open(src, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#"):
                return load_book(url=line)
    raise SystemExit("Kein paper_book.json gefunden.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book"); ap.add_argument("--url")
    a = ap.parse_args()
    book, src = load_book(a.book, a.url)
    trades = [t for t in (book.get("closed") or []) if t.get("entry") and t.get("stop")]
    trades += [t for t in (book.get("open") or []) if t.get("entry") and t.get("stop")]
    print(f"\nQuelle: {src}\nTrades mit Stop: {len(trades)}\n")
    if not trades:
        raise SystemExit("Nichts auszuwerten.")

    print("=" * 74)
    print("WAS DER SPREAD VOM RISIKO FRISST")
    print("=" * 74)
    print(f"{'Symbol':<10}{'Stop%':>8}{'Spread%':>9}{'Kosten in R':>13}{'Gegenwert/Konto':>17}")
    print("-" * 74)
    rows = []
    for t in sorted(trades, key=lambda x: abs(float(x["entry"]) - float(x["stop"])) / float(x["entry"])):
        sym = t.get("symbol", "")
        entry = float(t["entry"]); stop = float(t["stop"])
        dist = abs(entry - stop)
        if dist <= 0:
            continue
        stop_pct = dist / entry * 100
        sf = float(t.get("spread_frac") or datafeed.PAPER_SPREAD_FRAC.get(sym, 0.0002))
        # ein voller Umschlag: halber Spread rein, halber raus
        cost_r = (sf * entry) / dist
        notional_x = (1.0 / stop_pct) if stop_pct else 0     # bei 1% Risiko
        rows.append((sym, stop_pct, sf * 100, cost_r, notional_x))
        print(f"{sym:<10}{stop_pct:>7.2f}%{sf*100:>8.3f}%{cost_r:>12.3f}R{notional_x:>16.2f}x")

    print("-" * 74)
    n = len(rows)
    avg_cost = sum(r[3] for r in rows) / n
    tight = [r for r in rows if r[1] < 0.5]
    print(f"Durchschnittliche Spreadkosten: {avg_cost:.3f}R pro Trade")
    print(f"Trades mit Stop unter 0,5%: {len(tight)} von {n} "
          f"({len(tight)/n*100:.0f}%)")
    if tight:
        print(f"  deren Spreadkosten: {sum(r[3] for r in tight)/len(tight):.3f}R "
              f"pro Trade")
        print(f"  deren Gegenwert:    {sum(r[4] for r in tight)/len(tight):.2f}x Konto "
              f"(bei 1% Risiko)")
    wide = [r for r in rows if r[1] >= 0.5]
    if wide:
        print(f"Trades ab 0,5% Stop: {len(wide)}")
        print(f"  deren Spreadkosten: {sum(r[3] for r in wide)/len(wide):.3f}R pro Trade")

    print("\n" + "=" * 74)
    print("WAS EINE KOSTENGRENZE ENTFERNEN WUERDE")
    print("=" * 74)
    print("Regel: Trade nur, wenn der Spread hoechstens X vom Risiko frisst.")
    print(f"{'Grenze':>10}{'bleibt':>10}{'faellt weg':>13}{'Kosten danach':>16}")
    print("-" * 74)
    for lim in [0.20, 0.15, 0.10, 0.07, 0.05, 0.03]:
        keep = [r for r in rows if r[3] <= lim]
        if keep:
            print(f"{lim:>9.2f}R{len(keep):>10}{n-len(keep):>13}"
                  f"{sum(r[3] for r in keep)/len(keep):>15.3f}R")
        else:
            print(f"{lim:>9.2f}R{0:>10}{n:>13}{'-':>16}")
    print("=" * 74)
    print("\nDie Grenze waehlen wir nach der Mechanik, NICHT nach der Rendite:")
    print("bei 2R-Ziel und 33% noetiger Trefferquote sind 0.10R Kosten bereits")
    print("ein Drittel des Spielraums, den die Strategie ueberhaupt hat.\n")


if __name__ == "__main__":
    main()
