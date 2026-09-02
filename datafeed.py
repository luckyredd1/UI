"""Public market data — no broker, no account, no ID.

MetaQuotes has no crypto and its indices are DISABLED for trading. But the
forward test's job is to MEASURE, and measuring only needs data. Execution is
a separate question.

So: crypto comes from Binance's public endpoint (no key, no signup) and
indices from Yahoo's public chart endpoint. Both use urllib only -
no yfinance, no pandas, so this runs on plain Python anywhere.
with simulated fills, alongside the real broker orders on forex and gold.

  paper  = honest about its fills being simulated
  broker = real fills, real spread, real slippage

Keeping both, clearly labelled, is better than pretending one is the other.

  py datafeed.py --check     confirm the feeds work
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from broker_mt5 import Candle

TF_BINANCE = {"M5": "5m", "M15": "15m", "H1": "1h", "H4": "4h", "D1": "1d"}
TF_YF = {"M5": "5m", "M15": "15m", "H1": "60m", "H4": "1h", "D1": "1d"}

CRYPTO = {"BTCUSD": "BTCUSDT", "ETHUSD": "ETHUSDT", "SOLUSD": "SOLUSDT",
          "XRPUSD": "XRPUSDT", "BNBUSD": "BNBUSDT", "ADAUSD": "ADAUSDT",
          "DOGEUSD": "DOGEUSDT", "LINKUSD": "LINKUSDT", "AVAXUSD": "AVAXUSDT",
          "LTCUSD": "LTCUSDT"}
INDICES = {}          # Indexstaende sind keine handelbaren Instrumente

# Statt Indexstaenden echte, an der Boerse gehandelte ETFs. Yahoo liefert
# dafuer tatsaechliche Umsaetze statt eines Rechenwerts - und kaufen koennte
# man sie auch. Handelszeiten bleiben US-Kasse.
ETFS = {"SPY": "SPY",      # S&P 500
        "QQQ": "QQQ",      # Nasdaq 100
        "DIA": "DIA",      # Dow Jones
        "IWM": "IWM"}      # Russell 2000
# Deliberately NOT here: energy (NG=F, CL=F). Thin, gappy, and news-driven in a
# way these setups are not built for.
FOREX = {"EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
         "AUDUSD": "AUDUSD=X", "USDCAD": "USDCAD=X", "USDCHF": "USDCHF=X",
         "NZDUSD": "NZDUSD=X", "XAUUSD": "GC=F"}
# Bewusst NICHT mehr dabei: die 20 Kreuze ohne USD (duenne Yahoo-Daten,
# hohe Spreads, und sie teilen sich ohnehin einen Positionsplatz) und
# Silber (braucht 0,80% Stop, um die Kostengrenze zu bestehen - kommt auf
# M15 praktisch nie vor).

# Readable labels for the terminal.
DISPLAY = {
    "XAUUSD": "Gold", "XAGUSD": "Silber", "NAS100": "Nasdaq 100",
    "SPX500": "S&P 500", "US30": "Dow Jones", "GER40": "DAX 40",
    "UK100": "FTSE 100", "JP225": "Nikkei 225", "FRA40": "CAC 40",
    "EU50": "Euro Stoxx 50", "HK50": "Hang Seng", "AUS200": "ASX 200",
    "US2000": "Russell 2000", "BTCUSD": "Bitcoin", "ETHUSD": "Ethereum",
    "SOLUSD": "Solana", "XRPUSD": "XRP", "BNBUSD": "BNB", "ADAUSD": "Cardano",
    "DOGEUSD": "Dogecoin", "LINKUSD": "Chainlink", "AVAXUSD": "Avalanche",
    "LTCUSD": "Litecoin",
    "SPY": "S&P 500 ETF", "QQQ": "Nasdaq 100 ETF",
    "DIA": "Dow Jones ETF", "IWM": "Russell 2000 ETF",
}


def display(sym: str) -> str:
    if sym in DISPLAY:
        return DISPLAY[sym]
    if sym in FOREX and len(sym) == 6:
        return f"{sym[:3]}/{sym[3:]}"
    return sym

# What the TERMINAL should be told to display for each symbol.
TERMINAL_SYMBOL = {**{k: v for k, v in FOREX.items()},
                   **{k: v for k, v in ETFS.items()},
                   **{k: k[:-3] + "-USD" for k in CRYPTO}}


def binance(symbol: str, tf: str = "M15", limit: int = 1000) -> list[Candle]:
    """Public klines. No API key. Laedt seitenweise, damit auch Jahre gehen.

    Ein Aufruf liefert hoechstens 1000 Kerzen; fuer mehr wird rueckwaerts
    ueber endTime geblaettert.
    """
    pair = CRYPTO.get(symbol, symbol)
    iv = TF_BINANCE.get(tf, "15m")
    hosts = ["https://data-api.binance.vision", "https://api.binance.com"]
    rows: list = []
    end = None
    while len(rows) < limit:
        want = min(1000, limit - len(rows))
        got = None
        for host in hosts:
            url = (f"{host}/api/v3/klines?symbol={pair}&interval={iv}"
                   f"&limit={want}")
            if end is not None:
                url += f"&endTime={end}"
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=25) as r:
                    got = json.loads(r.read().decode())
                break
            except Exception:
                continue
        if not got:
            break
        rows = got + rows
        end = got[0][0] - 1                 # weiter rueckwaerts
        if len(got) < want:
            break                            # Anfang der Historie erreicht
        time.sleep(0.15)
    out = []
    for k in rows:
        ts = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc)
        out.append(Candle(ts.strftime("%Y-%m-%dT%H:%M:%S"),
                          float(k[1]), float(k[2]), float(k[3]), float(k[4]),
                          float(k[5])))
    return out[-limit:]


# A 15-minute bar does not change for 15 minutes, so re-downloading 60 days of
# them every scan is pure waste — and Yahoo's answer to that much traffic is an
# EMPTY frame, not an error, which would look exactly like "no setups found".
CACHE_DIR = os.path.join(HERE, "cache")
CACHE_TTL = {"M5": 240, "M15": 780, "H1": 3300, "H4": 13800, "D1": 43200}


def _cache_path(symbol: str, tf: str) -> str:
    return os.path.join(CACHE_DIR, f"{symbol}_{tf}.json")


def _cache_read(symbol: str, tf: str, max_age: int | None = None):
    p = _cache_path(symbol, tf)
    try:
        age = time.time() - os.path.getmtime(p)
    except OSError:
        return None
    if max_age is not None and age > max_age:
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return [Candle(*row) for row in json.load(f)]
    except Exception:
        return None


def _cache_write(symbol: str, tf: str, candles: list[Candle]) -> None:
    if not candles:
        return
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = _cache_path(symbol, tf) + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump([[c.ts, c.open, c.high, c.low, c.close, c.volume]
                       for c in candles], f)
        os.replace(tmp, _cache_path(symbol, tf))
    except Exception:
        pass


def _yahoo_json(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36"),
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            import gzip
            raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8", "replace"))


def _parse_chart(j, symbol: str) -> list[Candle]:
    """Yahoo's v8 chart payload -> Candles. Same shape the terminal parses."""
    res = (j.get("chart") or {}).get("result") or []
    if not res:
        err = ((j.get("chart") or {}).get("error") or {})
        raise RuntimeError(err.get("description") or "no data")
    r = res[0]
    ind = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    ts = r.get("timestamp") or []
    o, h, l, c, v = (ind.get("open") or [], ind.get("high") or [],
                     ind.get("low") or [], ind.get("close") or [],
                     ind.get("volume") or [])
    out = []
    for i in range(len(ts)):
        # a closed market leaves null rows; skip rather than invent a price
        if i >= len(c) or c[i] is None:
            continue
        close = float(c[i])
        pick = lambda arr: (float(arr[i]) if i < len(arr) and arr[i] is not None
                            else close)
        t = datetime.fromtimestamp(ts[i], tz=timezone.utc)
        out.append(Candle(t.strftime("%Y-%m-%dT%H:%M:%S"),
                          pick(o), pick(h), pick(l), close,
                          float(v[i]) if i < len(v) and v[i] is not None else 0.0))
    return out


def yahoo(symbol: str, tf: str = "M15", limit: int = 1000) -> list[Candle]:
    """Yahoo's public chart endpoint, via urllib only.

    Deliberately NOT yfinance: that drags in pandas and numpy, which turns a
    stdlib-only script into a heavy install. Without them this whole bot runs
    on plain Python anywhere - a phone, a free tier, a Raspberry Pi.
    """
    fresh = _cache_read(symbol, tf, CACHE_TTL.get(tf, 780))
    if fresh:
        return fresh[-limit:]
    tk = ETFS.get(symbol) or FOREX.get(symbol) or symbol
    interval = TF_YF.get(tf, "15m")
    # Yahoo deckelt Intraday unterschiedlich: Minutenaufloesung 60 Tage,
    # Stundenaufloesung dagegen 730. Das vorher pauschal auf 60d zu setzen
    # hat zwoelf Monate Historie verschenkt.
    if interval in ("5m", "15m"):
        period = "60d"
    elif interval in ("60m", "1h"):
        period = "730d"
    else:
        period = "5y"
    out = []
    for host in ("query1", "query2"):
        url = ("https://%s.finance.yahoo.com/v8/finance/chart/%s"
               "?range=%s&interval=%s&includePrePost=false"
               % (host, urllib.parse.quote(tk), period, interval))
        try:
            out = _parse_chart(_yahoo_json(url), symbol)
            if out:
                break
        except Exception:
            continue
    if not out:
        # Throttled, or the ticker went quiet. Serve stale rather than pretend
        # the market is empty - but say so, so a stuck feed stays visible.
        stale = _cache_read(symbol, tf)
        if stale:
            return stale[-limit:]
        raise RuntimeError(f"{symbol}: Yahoo returned no rows (rate limit?)")
    _cache_write(symbol, tf, out)
    return out[-limit:]


def prefetch(symbols=None, tf: str = "M15", limit: int = 1000) -> dict:
    """Warm the cache for every Yahoo-fed symbol, one request each.

    Yahoo's chart endpoint takes a single symbol, so there is no true batch
    here - but the cache means a scan re-uses whatever is still fresh, and the
    small stagger keeps the burst polite. ~40 requests per 15-minute scan is
    well inside what the endpoint tolerates.

    Returns {symbol: n_bars} for what it managed to cache.
    """
    syms = [s for s in (symbols or ALL_SYMBOLS) if s in ETFS or s in FOREX]
    done = {}
    for i, sym in enumerate(syms):
        try:
            cs = yahoo(sym, tf, limit)       # yahoo() reads/writes the cache
            if cs:
                done[sym] = len(cs)
        except Exception:
            continue
        if i % 8 == 7:
            time.sleep(0.4)
    return done


def fetch(symbol: str, tf: str = "M15", limit: int = 1000) -> list[Candle]:
    if symbol in CRYPTO:
        return binance(symbol, tf, limit)          # deepest history, no key
    if symbol in ETFS or symbol in FOREX:
        return yahoo(symbol, tf, limit)            # ~60 days of intraday
    raise KeyError(f"{symbol} is not a public-feed symbol")


ALL_SYMBOLS = list(FOREX) + list(CRYPTO) + list(ETFS)


# ---------------------------------------------------------------------------
# Correlation groups. Holding SOL and DOGE at once is not two bets, it is one
# crypto bet in two tickets — they rise and fall together. The bot opens at
# most one position per group, so the account cannot quietly become a single
# concentrated wager.
#
# FX is grouped by the dollar, because that is the factor that actually drives
# the majors: EURUSD, GBPUSD and AUDUSD are largely the same trade wearing
# different labels. Crosses without USD form their own group.
# ---------------------------------------------------------------------------
def group_of(sym: str) -> str:
    if sym in CRYPTO:
        return "CRYPTO"
    if sym in ETFS:
        return "EQUITY"
    if sym in ("XAUUSD", "XAGUSD"):
        return "METALS"
    if sym in FOREX:
        return "FX_USD" if "USD" in sym else "FX_CROSS"
    return "OTHER:" + sym


def groups() -> dict:
    out = {}
    for s in ALL_SYMBOLS:
        out.setdefault(group_of(s), []).append(s)
    return out


# ---------------------------------------------------------------------------
# Hebel-Obergrenzen fuer Privatkunden in der EU (ESMA). Damit rechnet das
# Papierkonto genauso, wie ein echter Broker es dir erlauben wuerde - sonst
# oeffnet der Bot Positionen, die real abgelehnt worden waeren.
#   benoetigte Margin = Gegenwert / Hebel
# ---------------------------------------------------------------------------
LEVERAGE = {
    "FX_USD": 30,     # Waehrungspaare mit USD gelten als Majors
    "FX_CROSS": 20,   # Kreuze ohne USD
    "METALS": 20,     # Gold, Silber
    "EQUITY": 5,      # Aktien-ETFs, Privatkunden
    "CRYPTO": 2,      # Krypto - die harte Grenze, und die beisst am meisten
}


def leverage_of(sym: str) -> int:
    return LEVERAGE.get(group_of(sym), 5)


# Typical round-trip cost as a FRACTION of price, used to charge paper trades.
# Crypto spot ~0.02%, index CFDs ~0.01%. Rough, and deliberately not generous.
# Gesamtkosten Hin- und Rueckweg als Anteil vom Kurs - NICHT nur der Spread.
# Enthaelt Kommission bzw. Boersengebuehr, so wie ein Privatkunde sie zahlt.
#
# Die Rohspreads wurden am 02.09.2026 mit measure_spreads.py gemessen
# (Dukascopy-Ticks, Binance-Orderbuch) und stehen als Kommentar dahinter.
# Der Retail-Preis liegt darueber: den rohen Interbank-Spread bekommt man
# nicht ohne Kommission, und bei Krypto ist die Gebuehr groesser als der
# Spread. Genau diesen Teil hatte die Messung nicht erfasst.
PAPER_SPREAD_FRAC = {
    # Forex, alles inklusive (roher Spread gemessen)
    "EURUSD": 0.00008,   # roh 0.000026
    "GBPUSD": 0.00010,   # roh 0.000052
    "USDJPY": 0.00008,   # roh 0.000019
    "AUDUSD": 0.00014,   # roh 0.000112
    "USDCAD": 0.00012,   # roh 0.000087
    "USDCHF": 0.00012,   # roh 0.000086
    "NZDUSD": 0.00018,   # roh 0.000154
    "XAUUSD": 0.00025,   # roh 0.000127
    # US-ETFs, boersengehandelt, meist ohne Kommission
    "SPY": 0.00003, "QQQ": 0.00005, "DIA": 0.00010, "IWM": 0.00010,
    # Krypto als CFD. Der reine Boersenspread ist winzig (BTC roh 0.000000),
    # aber Binance nimmt 0,1% je Seite = 0,2% hin und zurueck. Als CFD steckt
    # der Preis stattdessen im Spread. Beides liegt weit ueber dem Rohspread.
    "BTCUSD": 0.0010, "ETHUSD": 0.0012, "BNBUSD": 0.0020,
    "SOLUSD": 0.0020, "XRPUSD": 0.0020, "LTCUSD": 0.0020,
    "ADAUSD": 0.0025, "DOGEUSD": 0.0025, "LINKUSD": 0.0025,
    "AVAXUSD": 0.0025,
}

# Krypto bekommt ein groesseres Ziel. Begruendung ist Arithmetik: der
# Nachteil durch Kosten betraegt c/(m+1) in Trefferquote-Punkten, schrumpft
# also mit groesserem Ziel. Bei 4R kostet derselbe Spread nur noch drei
# Fuenftel des Nachteils, den er bei 2R verursacht.
RR_OVERRIDE = {"CRYPTO": 4.0}


def rr_for(sym: str, default: float = 2.0) -> float:
    return RR_OVERRIDE.get(group_of(sym), default)


def paper_spread(symbol: str, price: float) -> float:
    return price * PAPER_SPREAD_FRAC.get(symbol, 0.0002)


if __name__ == "__main__":
    print("\nPublic feeds — no account required\n")
    for sym in ALL_SYMBOLS:
        try:
            cs = fetch(sym, "M15", 200)
            print(f"  OK    {sym:<9} {len(cs):>4} bars   "
                  f"{cs[0].ts[:16]} .. {cs[-1].ts[:16]}   last {cs[-1].close:,.2f}")
        except Exception as exc:
            print(f"  FAIL  {sym:<9} {str(exc)[:70]}")
    print("\nBoth feeds are public and need no key. Pure standard library:"
          " no yfinance, no pandas.\n")
