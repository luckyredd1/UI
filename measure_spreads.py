"""Echte Spreads messen statt schaetzen.

Bisher sind die Werte in datafeed.PAPER_SPREAD_FRAC von mir geschaetzt. Die
ganze 0,10R-Kostengrenze steht und faellt damit - also messen wir sie.

  Forex/Gold : Dukascopy-Tickdaten. Echte Geld- und Briefkurse, kostenlos,
               ohne Konto. Die Dateien liegen unter datafeed.dukascopy.com
               und werden hier direkt geladen (LZMA, 20 Byte je Tick).
  Krypto     : Binance-Orderbuch (bookTicker). Echte Boersenpreise.

  python measure_spreads.py                  letzte 3 Handelstage
  python measure_spreads.py --hours 12       mehr Ticks, dauert laenger
  python measure_spreads.py --only EURUSD,GBPUSD

Am Ende steht ein fertiger Block, den du in datafeed.py einsetzen kannst.
Reines Standard-Python.
"""
from __future__ import annotations

import argparse
import json
import lzma
import os
import struct
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DUKA = "https://datafeed.dukascopy.com/datafeed/{sym}/{y}/{m:02d}/{d:02d}/{h:02d}h_ticks.bi5"

# Wie viele Nachkommastellen Dukascopy fuer das Instrument benutzt.
DECIMALS = {"USDJPY": 3, "EURJPY": 3, "GBPJPY": 3, "AUDJPY": 3, "CADJPY": 3,
            "CHFJPY": 3, "NZDJPY": 3, "XAUUSD": 3, "XAGUSD": 3}
DEFAULT_DECIMALS = 5

FX = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
      "XAUUSD"]
CRYPTO = {"BTCUSD": "BTCUSDT", "ETHUSD": "ETHUSDT", "SOLUSD": "SOLUSDT",
          "XRPUSD": "XRPUSDT", "BNBUSD": "BNBUSDT", "ADAUSD": "ADAUSDT",
          "DOGEUSD": "DOGEUSDT", "LINKUSD": "LINKUSDT", "AVAXUSD": "AVAXUSDT",
          "LTCUSD": "LTCUSDT"}


def get(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0", "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def unpack_bi5(blob, decimals):
    """Ein .bi5 auspacken. 20 Byte je Tick: ms, ask, bid, askvol, bidvol."""
    if not blob:
        return []
    raw = None
    for fmt in (lzma.FORMAT_AUTO, lzma.FORMAT_ALONE):
        try:
            raw = lzma.LZMADecompressor(fmt).decompress(blob)
            break
        except Exception:
            continue
    if raw is None:
        return []
    scale = 10.0 ** decimals
    out = []
    for i in range(0, len(raw) - 19, 20):
        _ms, ask, bid, _av, _bv = struct.unpack(">IIIff", raw[i:i + 20])
        if ask and bid:
            out.append((ask / scale, bid / scale))
    return out


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return None
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def measure_fx(sym, hours):
    """Spread als Anteil vom Kurs, Median ueber die geladenen Stunden."""
    dec = DECIMALS.get(sym, DEFAULT_DECIMALS)
    fracs, ticks, got, tried = [], 0, 0, 0
    t = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    t -= timedelta(hours=2)                      # ganz frische Stunden fehlen oft
    while got < hours and tried < hours * 6:
        tried += 1
        t -= timedelta(hours=1)
        if t.weekday() == 5 or (t.weekday() == 6 and t.hour < 21):
            continue                              # Wochenende: kein Handel
        url = DUKA.format(sym=sym, y=t.year, m=t.month - 1, d=t.day, h=t.hour)
        try:
            blob = get(url)
        except urllib.error.HTTPError:
            continue
        except Exception:
            continue
        rows = unpack_bi5(blob, dec)
        if not rows:
            continue
        got += 1
        for ask, bid in rows:
            mid = (ask + bid) / 2
            if mid > 0 and ask >= bid:
                fracs.append((ask - bid) / mid)
        ticks += len(rows)
    return median(fracs), ticks, got


def measure_crypto(sym, pair):
    """Bestes Geld/Brief aus dem Binance-Orderbuch."""
    for host in ("https://data-api.binance.vision", "https://api.binance.com"):
        try:
            j = json.loads(get(f"{host}/api/v3/ticker/bookTicker?symbol={pair}",
                               timeout=15).decode())
            bid, ask = float(j["bidPrice"]), float(j["askPrice"])
            mid = (bid + ask) / 2
            if mid > 0:
                return (ask - bid) / mid
        except Exception:
            continue
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=6,
                    help="Handelsstunden je Forex-Symbol")
    ap.add_argument("--only", help="Komma-Liste, sonst alle")
    a = ap.parse_args()
    only = {s.strip().upper() for s in a.only.split(",")} if a.only else None

    try:
        import datafeed
        old = dict(datafeed.PAPER_SPREAD_FRAC)
    except Exception:
        old = {}

    print(f"\nMesse echte Spreads. Forex ueber {a.hours} Handelsstunden "
          f"(Dukascopy), Krypto aus dem Binance-Orderbuch.\n")
    print(f"{'Symbol':<10}{'geschaetzt':>12}{'gemessen':>12}{'Faktor':>9}"
          f"{'Ticks':>10}  Quelle")
    print("-" * 68)

    measured = {}
    for sym in FX:
        if only and sym not in only:
            continue
        print(f"{sym:<10}{'...':>12}", end="\r", flush=True)
        frac, ticks, hrs = measure_fx(sym, a.hours)
        if frac is None:
            print(f"{sym:<10}{old.get(sym,0)*100:>11.4f}%{'FEHLER':>12}"
                  f"{'':>9}{0:>10}  Dukascopy nicht erreichbar")
            continue
        measured[sym] = frac
        o = old.get(sym)
        fac = (frac / o) if o else 0
        print(f"{sym:<10}{(o or 0)*100:>11.4f}%{frac*100:>11.4f}%"
              f"{fac:>8.2f}x{ticks:>10,}  Dukascopy {hrs}h")

    for sym, pair in CRYPTO.items():
        if only and sym not in only:
            continue
        frac = measure_crypto(sym, pair)
        if frac is None:
            print(f"{sym:<10}{old.get(sym,0)*100:>11.4f}%{'FEHLER':>12}"
                  f"{'':>9}{0:>10}  Binance nicht erreichbar")
            continue
        measured[sym] = frac
        o = old.get(sym)
        fac = (frac / o) if o else 0
        print(f"{sym:<10}{(o or 0)*100:>11.4f}%{frac*100:>11.4f}%"
              f"{fac:>8.2f}x{'Orderbuch':>10}  Binance")

    if not measured:
        raise SystemExit("\nNichts gemessen. Internetzugang pruefen.\n")

    print("-" * 68)
    print("\nWas das fuer die 0,10R-Grenze bedeutet:\n")
    print(f"{'Symbol':<10}{'Stop noetig alt':>17}{'Stop noetig neu':>17}")
    print("-" * 46)
    for sym, frac in measured.items():
        o = old.get(sym)
        print(f"{sym:<10}{(o/0.10*100 if o else 0):>16.2f}%"
              f"{frac/0.10*100:>16.2f}%")

    print("\n" + "=" * 68)
    print("Zum Einsetzen in datafeed.py (PAPER_SPREAD_FRAC):")
    print("=" * 68)
    for sym in sorted(measured):
        print(f'    "{sym}": {measured[sym]:.6f},')
    print("=" * 68)
    out = os.path.join(HERE, "measured_spreads.json")
    json.dump({k: round(v, 8) for k, v in measured.items()},
              open(out, "w"), indent=2)
    print(f"\nAuch gespeichert: {out}\n")


if __name__ == "__main__":
    main()
