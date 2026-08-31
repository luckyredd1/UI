#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
  TERMINAL  --  ein eigenes Bloomberg-artiges Markt-Terminal
=============================================================================
  Nur Python-Standardbibliothek. Keine pip-Installation noetig.
  Start:   python terminal.py          (oeffnet Browser auf http://127.0.0.1:8765)
           python terminal.py --demo   (synthetische Daten, kein Internet noetig)
           python terminal.py --port 9000 --no-browser
=============================================================================
"""

import argparse
import concurrent.futures as futures
import gzip
import http.cookiejar
import io
import json
import math
import os
import random
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "data")
UI_FILE = os.path.join(APP_DIR, "ui.html")
STATE_FILE = os.path.join(DATA_DIR, "state.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

DEMO = False
VERBOSE = False

# ---------------------------------------------------------------------------
#  Universum: wird fuer Screener / Heatmap / Movers verwendet
# ---------------------------------------------------------------------------
UNIVERSE = {
    "US_MEGA": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO",
                "BRK-B", "LLY", "JPM", "V", "XOM", "UNH", "MA", "COST", "HD",
                "PG", "JNJ", "ABBV", "WMT", "NFLX", "CRM", "AMD", "ORCL", "KO",
                "PEP", "CVX", "ADBE", "MRK", "TMO", "BAC", "ACN", "MCD", "CSCO",
                "LIN", "ABT", "INTC", "DIS", "QCOM", "TXN", "INTU", "IBM", "CAT",
                "GE", "VZ", "AMGN", "PFE", "NOW", "UBER", "BA", "GS", "SBUX",
                "PLTR", "COIN", "MU", "SHOP", "PANW", "ANET", "SMCI", "ARM"],
    "DE": ["SAP.DE", "SIE.DE", "ALV.DE", "DTE.DE", "AIR.DE", "MBG.DE", "BMW.DE",
           "BAS.DE", "BAYN.DE", "VOW3.DE", "IFX.DE", "MUV2.DE", "DBK.DE",
           "ADS.DE", "RWE.DE", "MRK.DE", "HEN3.DE", "P911.DE", "ZAL.DE",
           "RHM.DE", "CBK.DE", "1COV.DE", "EOAN.DE", "FRE.DE", "HEI.DE"],
    "EU": ["ASML.AS", "MC.PA", "OR.PA", "TTE.PA", "SAN.PA", "AIR.PA", "NESN.SW",
           "NOVN.SW", "ROG.SW", "UBSG.SW", "SHEL.L", "AZN.L", "HSBA.L", "ULVR.L",
           "BP.L", "NOVO-B.CO", "ISP.MI", "ENI.MI"],
    "INDEX": ["^GSPC", "^NDX", "^DJI", "^RUT", "^VIX", "^GDAXI", "^STOXX50E",
              "^FTSE", "^FCHI", "^N225", "^HSI", "000001.SS"],
    "FX": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X", "EURCHF=X",
           "AUDUSD=X", "USDCAD=X", "EURGBP=X", "NZDUSD=X", "EURJPY=X",
           "GBPJPY=X"],
    "COMMOD": ["GC=F", "SI=F", "CL=F", "BZ=F", "NG=F", "HG=F", "ZW=F", "ZC=F"],
    "CRYPTO": ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD",
               "DOGE-USD", "AVAX-USD", "LINK-USD", "BNB-USD", "LTC-USD"],
    "RATES": ["^TNX", "^FVX", "^TYX", "^IRX"],
}



# ---------------------------------------------------------------------------
# Readable names for every ticker in UNIVERSE. Used by the tape, the watchlist
# and anywhere else a bare Yahoo ticker would otherwise be shown.
# ---------------------------------------------------------------------------
NAMES = {
    # Indices
    "^GSPC": "S&P 500", "^NDX": "Nasdaq 100", "^DJI": "Dow Jones",
    "^RUT": "Russell 2000", "^VIX": "VIX", "^GDAXI": "DAX",
    "^STOXX50E": "Euro Stoxx 50", "^FTSE": "FTSE 100", "^FCHI": "CAC 40",
    "^N225": "Nikkei 225", "^HSI": "Hang Seng", "000001.SS": "Shanghai Comp.",
    # Rates
    "^TNX": "US 10 Jahre", "^FVX": "US 5 Jahre", "^TYX": "US 30 Jahre",
    "^IRX": "US 13 Wochen",
    # Commodities
    "GC=F": "Gold", "SI=F": "Silber", "HG=F": "Kupfer", "CL=F": "WTI Oel",
    "BZ=F": "Brent Oel", "NG=F": "Erdgas", "ZW=F": "Weizen", "ZC=F": "Mais",
    # FX
    "EURUSD=X": "EUR/USD", "GBPUSD=X": "GBP/USD", "USDJPY=X": "USD/JPY",
    "USDCHF=X": "USD/CHF", "EURCHF=X": "EUR/CHF", "AUDUSD=X": "AUD/USD",
    "USDCAD=X": "USD/CAD", "EURGBP=X": "EUR/GBP", "NZDUSD=X": "NZD/USD",
    "EURJPY=X": "EUR/JPY", "GBPJPY=X": "GBP/JPY",
    # Crypto
    "BTC-USD": "Bitcoin", "ETH-USD": "Ethereum", "SOL-USD": "Solana",
    "XRP-USD": "XRP", "ADA-USD": "Cardano", "DOGE-USD": "Dogecoin",
    "AVAX-USD": "Avalanche", "LINK-USD": "Chainlink", "BNB-USD": "BNB",
    "LTC-USD": "Litecoin",
    # US mega caps
    "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "Nvidia",
    "GOOGL": "Alphabet", "AMZN": "Amazon", "META": "Meta", "TSLA": "Tesla",
    "AVGO": "Broadcom", "BRK-B": "Berkshire H.", "LLY": "Eli Lilly",
    "JPM": "JPMorgan", "V": "Visa", "XOM": "Exxon Mobil",
    "UNH": "UnitedHealth", "MA": "Mastercard", "COST": "Costco",
    "HD": "Home Depot", "PG": "Procter & G.", "JNJ": "Johnson & J.",
    "ABBV": "AbbVie", "WMT": "Walmart", "NFLX": "Netflix",
    "CRM": "Salesforce", "AMD": "AMD", "ORCL": "Oracle", "KO": "Coca-Cola",
    "PEP": "PepsiCo", "CVX": "Chevron", "ADBE": "Adobe", "MRK": "Merck & Co",
    "TMO": "Thermo Fisher", "BAC": "Bank of Am.", "ACN": "Accenture",
    "MCD": "McDonald's", "CSCO": "Cisco", "LIN": "Linde", "ABT": "Abbott",
    "INTC": "Intel", "DIS": "Disney", "QCOM": "Qualcomm",
    "TXN": "Texas Instr.", "INTU": "Intuit", "IBM": "IBM",
    "CAT": "Caterpillar", "GE": "GE Aerospace", "VZ": "Verizon",
    "AMGN": "Amgen", "PFE": "Pfizer", "NOW": "ServiceNow", "UBER": "Uber",
    "BA": "Boeing", "GS": "Goldman Sachs", "SBUX": "Starbucks",
    "PLTR": "Palantir", "COIN": "Coinbase", "MU": "Micron",
    "SHOP": "Shopify", "PANW": "Palo Alto", "ANET": "Arista",
    "SMCI": "Super Micro", "ARM": "Arm Holdings",
    # DAX / German
    "SAP.DE": "SAP", "SIE.DE": "Siemens", "ALV.DE": "Allianz",
    "DTE.DE": "Dt. Telekom", "AIR.DE": "Airbus", "MBG.DE": "Mercedes-Benz",
    "BMW.DE": "BMW", "BAS.DE": "BASF", "BAYN.DE": "Bayer",
    "VOW3.DE": "Volkswagen", "IFX.DE": "Infineon", "MUV2.DE": "Munich Re",
    "DBK.DE": "Dt. Bank", "ADS.DE": "Adidas", "RWE.DE": "RWE",
    "MRK.DE": "Merck KGaA", "HEN3.DE": "Henkel", "P911.DE": "Porsche AG",
    "ZAL.DE": "Zalando", "RHM.DE": "Rheinmetall", "CBK.DE": "Commerzbank",
    "1COV.DE": "Covestro", "EOAN.DE": "E.ON", "FRE.DE": "Fresenius",
    "HEI.DE": "Heidelberg M.",
    # Europe
    "ASML.AS": "ASML", "MC.PA": "LVMH", "OR.PA": "L'Oreal",
    "TTE.PA": "TotalEnergies", "SAN.PA": "Sanofi", "AIR.PA": "Airbus PA",
    "NESN.SW": "Nestle", "NOVN.SW": "Novartis", "ROG.SW": "Roche",
    "UBSG.SW": "UBS", "SHEL.L": "Shell", "AZN.L": "AstraZeneca",
    "HSBA.L": "HSBC", "ULVR.L": "Unilever", "BP.L": "BP",
    "NOVO-B.CO": "Novo Nordisk", "ISP.MI": "Intesa SP", "ENI.MI": "Eni",
}


def name_of(t):
    return NAMES.get(t) or t.replace("=X", "").replace("^", "")


# ---------------------------------------------------------------------------
# The ticker tape: a curated, ordered, human-readable strip. Kept separate from
# UNIVERSE so the screener/heatmap keep their full symbol lists while the tape
# stays short enough to read. (ticker, label)
# Deliberately absent: energy (CL=F, BZ=F, NG=F) and 000001.SS.
# ---------------------------------------------------------------------------
TAPE = [
    # --- Indices -----------------------------------------------------------
    "^GSPC", "^NDX", "^DJI", "^RUT", "^VIX",
    "^GDAXI", "^STOXX50E", "^FTSE", "^FCHI", "^N225", "^HSI", "000001.SS",
    # --- Rates -------------------------------------------------------------
    "^TNX", "^FVX", "^TYX", "^IRX",
    # --- Commodities (energy back in, as asked) ----------------------------
    "GC=F", "SI=F", "HG=F", "CL=F", "BZ=F", "NG=F", "ZW=F", "ZC=F",
    # --- FX ----------------------------------------------------------------
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X", "USDCAD=X", "AUDUSD=X",
    "NZDUSD=X", "EURGBP=X", "EURCHF=X", "EURJPY=X", "GBPJPY=X",
    # --- Crypto ------------------------------------------------------------
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "BNB-USD", "ADA-USD",
    "DOGE-USD", "LINK-USD", "AVAX-USD", "LTC-USD",
    # --- US mega caps ------------------------------------------------------
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO",
    "BRK-B", "LLY", "JPM", "V", "XOM", "UNH", "MA", "COST", "WMT", "NFLX",
    "AMD", "ORCL", "CRM", "ADBE", "INTC", "DIS", "QCOM", "IBM", "BA", "GS",
    "PLTR", "COIN", "MU", "PANW", "ARM", "UBER",
    # --- Germany -----------------------------------------------------------
    "SAP.DE", "SIE.DE", "ALV.DE", "DTE.DE", "AIR.DE", "MBG.DE", "BMW.DE",
    "BAS.DE", "BAYN.DE", "VOW3.DE", "IFX.DE", "MUV2.DE", "DBK.DE", "ADS.DE",
    "RHM.DE", "P911.DE", "CBK.DE", "EOAN.DE",
    # --- Europe ------------------------------------------------------------
    "ASML.AS", "MC.PA", "OR.PA", "TTE.PA", "SAN.PA", "NESN.SW", "NOVN.SW",
    "ROG.SW", "UBSG.SW", "SHEL.L", "AZN.L", "HSBA.L", "ULVR.L", "BP.L",
    "NOVO-B.CO",
]


def universe_all():
    out = []
    for v in UNIVERSE.values():
        out.extend(v)
    return out

def universe_equities():
    return UNIVERSE["US_MEGA"] + UNIVERSE["DE"] + UNIVERSE["EU"]

# ---------------------------------------------------------------------------
#  Cache
# ---------------------------------------------------------------------------
class Cache:
    def __init__(self):
        self._d = {}
        self._lock = threading.Lock()

    def get(self, key, ttl):
        with self._lock:
            hit = self._d.get(key)
        if not hit:
            return None
        ts, val = hit
        if time.time() - ts > ttl:
            return None
        return val

    def put(self, key, val):
        with self._lock:
            self._d[key] = (time.time(), val)

    def stats(self):
        with self._lock:
            return len(self._d)

CACHE = Cache()

def log(*a):
    if VERBOSE:
        print("[terminal]", *a, file=sys.stderr)

# ---------------------------------------------------------------------------
#  HTTP-Schicht mit Yahoo-Cookie/Crumb-Handling
# ---------------------------------------------------------------------------
_cookiejar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(_cookiejar))
_crumb = {"value": None, "ts": 0}
_crumb_lock = threading.Lock()

def http_get(url, timeout=12, headers=None, binary=False):
    hdr = {
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "close",
    }
    if headers:
        hdr.update(headers)
    req = urllib.request.Request(url, headers=hdr)
    with _opener.open(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            try:
                raw = gzip.decompress(raw)
            except Exception:
                pass
    if binary:
        return raw
    return raw.decode("utf-8", "replace")

def http_json(url, timeout=12, headers=None):
    return json.loads(http_get(url, timeout=timeout, headers=headers))

def yahoo_crumb(force=False):
    """Cookie + Crumb besorgen (fuer quoteSummary / quote v7 noetig)."""
    with _crumb_lock:
        if not force and _crumb["value"] and time.time() - _crumb["ts"] < 1800:
            return _crumb["value"]
        try:
            try:
                http_get("https://fc.yahoo.com/", timeout=8)
            except Exception:
                pass
            if not len(_cookiejar):
                try:
                    http_get("https://finance.yahoo.com/", timeout=10)
                except Exception:
                    pass
            c = http_get("https://query1.finance.yahoo.com/v1/test/getcrumb",
                         timeout=8)
            c = c.strip()
            if c and len(c) < 32 and "<" not in c:
                _crumb["value"] = c
                _crumb["ts"] = time.time()
                log("crumb ok:", c)
                return c
        except Exception as e:
            log("crumb failed:", e)
        _crumb["value"] = None
        return None

def yahoo_json(path, params=None, host="query1", need_crumb=False, timeout=12):
    params = dict(params or {})
    if need_crumb:
        c = yahoo_crumb()
        if c:
            params["crumb"] = c
    url = "https://%s.finance.yahoo.com%s" % (host, path)
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        return http_json(url, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            time.sleep(1.6)
            return http_json(url, timeout=timeout)
        if e.code in (401, 403) and need_crumb:
            c = yahoo_crumb(force=True)
            if c:
                params["crumb"] = c
                url = "https://%s.finance.yahoo.com%s?%s" % (
                    host, path, urllib.parse.urlencode(params))
                return http_json(url, timeout=timeout)
        raise

# ---------------------------------------------------------------------------
#  Demo-Daten (Random-Walk, deterministisch pro Symbol)
# ---------------------------------------------------------------------------
def _demo_series(symbol, n=260, interval_sec=86400):
    rnd = random.Random(hash(symbol) & 0xFFFFFFFF)
    base = 20 + (hash(symbol) % 400)
    drift = (rnd.random() - 0.45) * 0.0015
    vol = 0.008 + rnd.random() * 0.022
    px = base
    now = int(time.time())
    ts, o, h, l, c, v = [], [], [], [], [], []
    for i in range(n):
        op = px
        px = max(0.5, px * (1 + drift + rnd.gauss(0, vol)))
        hi = max(op, px) * (1 + abs(rnd.gauss(0, vol / 2)))
        lo = min(op, px) * (1 - abs(rnd.gauss(0, vol / 2)))
        ts.append(now - (n - i) * interval_sec)
        o.append(round(op, 4)); h.append(round(hi, 4))
        l.append(round(lo, 4)); c.append(round(px, 4))
        v.append(int(abs(rnd.gauss(5e6, 2e6))))
    return {"t": ts, "o": o, "h": h, "l": l, "c": c, "v": v}

DEMO_NAMES = {"AAPL": "Apple Inc.", "MSFT": "Microsoft Corp.",
              "SAP.DE": "SAP SE", "^GSPC": "S&P 500", "BTC-USD": "Bitcoin USD"}

def _demo_quote(symbol):
    s = _demo_series(symbol, 60)
    last, prev = s["c"][-1], s["c"][-2]
    lo = min(s["l"]); hi = max(s["h"])
    return {
        "symbol": symbol,
        "name": DEMO_NAMES.get(symbol, symbol.replace("-", " ").split(".")[0].title()),
        "price": last, "prevClose": prev,
        "change": round(last - prev, 4),
        "changePct": round((last / prev - 1) * 100, 3),
        "open": s["o"][-1], "high": s["h"][-1], "low": s["l"][-1],
        "volume": s["v"][-1], "currency": "USD", "exchange": "DEMO",
        "high52": round(hi, 2), "low52": round(lo, 2),
        "marketState": "REGULAR", "ts": s["t"][-1], "demo": True,
    }

# ---------------------------------------------------------------------------
#  Quotes  (via chart-Endpoint -> kein Crumb noetig, sehr robust)
# ---------------------------------------------------------------------------
# UI-Kuerzel -> (Yahoo-Range, Standardintervall)
RANGE_MAP = {
    "1d": ("1d", "2m"), "5d": ("5d", "15m"), "1m": ("1mo", "1h"),
    "3m": ("3mo", "1d"), "6m": ("6mo", "1d"), "ytd": ("ytd", "1d"),
    "1y": ("1y", "1d"), "2y": ("2y", "1d"), "5y": ("5y", "1wk"),
    "max": ("max", "1mo"),
}

# Wieviele Tage Historie Yahoo je Intervall maximal liefert
INTERVAL_MAX_DAYS = {
    "1m": 7, "2m": 60, "5m": 60, "15m": 60, "30m": 60, "90m": 60,
    "60m": 730, "1h": 730,
    "1d": 999999, "5d": 999999, "1wk": 999999, "1mo": 999999, "3mo": 999999,
}
RANGE_DAYS = {
    "1d": 1, "5d": 5, "1mo": 31, "3mo": 93, "6mo": 186, "ytd": 366,
    "1y": 366, "2y": 731, "5y": 1827, "10y": 3653, "max": 999999,
}
INTRADAY = ("1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h")


INTERVAL_ORDER = ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"]


def valid_intervals(rng, symbol=None):
    """Welche Intervalle fuer diesen Zeitraum moeglich sind - in Anzeigereihenfolge.

    Sekunden gibt es nur bei Krypto (Binance) und unabhaengig vom Zeitraum,
    weil sie immer das juengste Fenster zeigen.
    """
    days = RANGE_DAYS.get(rng, 999999)
    out = [iv for iv in INTERVAL_ORDER if days <= INTERVAL_MAX_DAYS.get(iv, 0)]
    if symbol and is_crypto(symbol):
        out = ["1s", "5s", "15s", "30s"] + out
    return out


def fix_interval(rng, iv):
    """Unzulaessige Kombinationen still auf das naechstbeste Intervall drehen."""
    days = RANGE_DAYS.get(rng, 999999)
    order = ["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"]
    if iv not in INTERVAL_MAX_DAYS:
        iv = RANGE_MAP.get(rng, ("1y", "1d"))[1]
    if days <= INTERVAL_MAX_DAYS.get(iv, 0):
        return iv
    try:
        i = order.index(iv)
    except ValueError:
        i = order.index("1d")
    for j in range(i + 1, len(order)):
        if days <= INTERVAL_MAX_DAYS.get(order[j], 0):
            return order[j]
    return "1mo"

def fetch_chart(symbol, rng="1y", interval="1d"):
    key = "chart:%s:%s:%s" % (symbol, rng, interval)
    if interval in ("1m", "2m"):
        ttl = 20
    elif interval in INTRADAY:
        ttl = 45
    elif rng in ("1d", "5d"):
        ttl = 45
    else:
        ttl = 900
    hit = CACHE.get(key, ttl)
    if hit is not None:
        return hit
    if DEMO:
        secs = {"1m": 60, "2m": 120, "5m": 300, "15m": 900, "30m": 1800,
                "60m": 3600, "1h": 3600, "90m": 5400, "1d": 86400,
                "1wk": 604800, "1mo": 2592000}.get(interval, 86400)
        span = RANGE_DAYS.get(rng, 366) * 86400
        n = max(40, min(600, int(span / secs)))
        s = _demo_series(symbol, n, secs)
        out = {"meta": _demo_quote(symbol), "series": s}
        CACHE.put(key, out)
        return out
    j = yahoo_json("/v8/finance/chart/" + urllib.parse.quote(symbol),
                   {"range": rng, "interval": interval,
                    "includePrePost": "false", "events": "div,split"})
    res = (j.get("chart") or {}).get("result") or []
    if not res:
        err = (j.get("chart") or {}).get("error")
        raise RuntimeError((err or {}).get("description") or "no data")
    r = res[0]
    m = r.get("meta") or {}
    ind = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    tss = r.get("timestamp") or []
    o, h, l, c, v = (ind.get("open") or [], ind.get("high") or [],
                     ind.get("low") or [], ind.get("close") or [],
                     ind.get("volume") or [])
    T, O, H, L, C, V = [], [], [], [], [], []
    for i in range(len(tss)):
        try:
            if c[i] is None:
                continue
        except IndexError:
            continue
        T.append(tss[i])
        O.append(o[i] if i < len(o) and o[i] is not None else c[i])
        H.append(h[i] if i < len(h) and h[i] is not None else c[i])
        L.append(l[i] if i < len(l) and l[i] is not None else c[i])
        C.append(c[i])
        V.append(v[i] if i < len(v) and v[i] is not None else 0)
    price = m.get("regularMarketPrice")
    prev = m.get("chartPreviousClose") or m.get("previousClose")
    if price is None and C:
        price = C[-1]
    if prev is None and len(C) > 1:
        prev = C[-2]
    chg = (price - prev) if (price is not None and prev) else 0.0
    pct = (chg / prev * 100.0) if prev else 0.0
    meta = {
        "symbol": m.get("symbol") or symbol,
        "name": m.get("longName") or m.get("shortName") or symbol,
        "price": price, "prevClose": prev,
        "change": round(chg, 4), "changePct": round(pct, 3),
        "open": m.get("regularMarketOpen") or (O[-1] if O else None),
        "high": m.get("regularMarketDayHigh") or (H[-1] if H else None),
        "low": m.get("regularMarketDayLow") or (L[-1] if L else None),
        "volume": m.get("regularMarketVolume") or (V[-1] if V else None),
        "currency": m.get("currency") or "", "exchange": m.get("fullExchangeName")
        or m.get("exchangeName") or "",
        "high52": m.get("fiftyTwoWeekHigh"), "low52": m.get("fiftyTwoWeekLow"),
        "marketState": m.get("marketState") or "", "ts": m.get("regularMarketTime"),
        "tz": m.get("exchangeTimezoneName") or "",
        "instrumentType": m.get("instrumentType") or "",
    }
    out = {"meta": meta, "series": {"t": T, "o": O, "h": H, "l": L, "c": C, "v": V}}
    CACHE.put(key, out)
    return out

def get_quote(symbol):
    key = "q:" + symbol
    hit = CACHE.get(key, 20)
    if hit is not None:
        return hit
    try:
        q = fetch_chart(symbol, "5d", "1d")["meta"]
        q["ok"] = True
    except Exception as e:
        q = {"symbol": symbol, "ok": False, "error": str(e)[:120]}
    CACHE.put(key, q)
    return q

BATCH_FIELDS = ("symbol,shortName,longName,regularMarketPrice,regularMarketChange,"
                "regularMarketChangePercent,regularMarketPreviousClose,regularMarketOpen,"
                "regularMarketDayHigh,regularMarketDayLow,regularMarketVolume,currency,"
                "fullExchangeName,fiftyTwoWeekHigh,fiftyTwoWeekLow,marketState,"
                "regularMarketTime,quoteType,exchangeTimezoneName")

def _batch_quotes(symbols):
    """Eine Anfrage fuer viele Symbole (spart Rate-Limit). Braucht Crumb."""
    out = {}
    for i in range(0, len(symbols), 45):
        chunk = symbols[i:i + 45]
        try:
            j = yahoo_json("/v7/finance/quote",
                           {"symbols": ",".join(chunk), "fields": BATCH_FIELDS},
                           need_crumb=True, timeout=14)
        except Exception as e:
            log("batch quote fail:", e)
            return out
        for r in (j.get("quoteResponse") or {}).get("result") or []:
            sym = r.get("symbol")
            if not sym:
                continue
            price = r.get("regularMarketPrice")
            prev = r.get("regularMarketPreviousClose")
            chg = r.get("regularMarketChange")
            pctv = r.get("regularMarketChangePercent")
            if chg is None and price is not None and prev:
                chg = price - prev
            if pctv is None and prev:
                pctv = (chg or 0) / prev * 100.0
            out[sym] = {
                "symbol": sym, "ok": True,
                "name": r.get("longName") or r.get("shortName") or sym,
                "price": price, "prevClose": prev,
                "change": round(chg, 4) if chg is not None else None,
                "changePct": round(pctv, 3) if pctv is not None else None,
                "open": r.get("regularMarketOpen"),
                "high": r.get("regularMarketDayHigh"),
                "low": r.get("regularMarketDayLow"),
                "volume": r.get("regularMarketVolume"),
                "currency": r.get("currency") or "",
                "exchange": r.get("fullExchangeName") or "",
                "high52": r.get("fiftyTwoWeekHigh"), "low52": r.get("fiftyTwoWeekLow"),
                "marketState": r.get("marketState") or "",
                "ts": r.get("regularMarketTime"),
                "tz": r.get("exchangeTimezoneName") or "",
                "instrumentType": r.get("quoteType") or "",
            }
    return out

def get_quotes(symbols, workers=10):
    symbols = [s for s in dict.fromkeys([s for s in symbols if s])]
    if not symbols:
        return []
    res, missing = {}, []
    for s in symbols:
        hit = CACHE.get("q:" + s, 20)
        if hit is not None:
            res[s] = hit
        else:
            missing.append(s)
    if missing and not DEMO:
        try:
            for sym, q in _batch_quotes(missing).items():
                CACHE.put("q:" + sym, q)
                res[sym] = q
        except Exception as e:
            log("batch fehler:", e)
        missing = [s for s in missing if s not in res]
    if missing:
        with futures.ThreadPoolExecutor(max_workers=min(workers, len(missing))) as ex:
            for q in ex.map(get_quote, missing):
                res[q["symbol"]] = q
    return [res.get(s) or {"symbol": s, "ok": False, "error": "keine Daten"}
            for s in symbols]


# ---------------------------------------------------------------------------
#  Sekunden-Kerzen (nur Krypto) - Binance liefert 1s-Klines ohne Schluessel
# ---------------------------------------------------------------------------
BINANCE_HOSTS = ["https://data-api.binance.vision", "https://api.binance.com"]
CRYPTO_RE = re.compile(r"^([A-Z0-9]{2,10})-(USD|USDT|EUR)$")
SEC_INTERVALS = {"1s": 1, "5s": 5, "15s": 15, "30s": 30}
SEC_PAGES = {1: 1, 5: 3, 15: 5, 30: 5}


def is_crypto(sym):
    return bool(CRYPTO_RE.match((sym or "").upper()))


def binance_symbol(sym):
    m = CRYPTO_RE.match((sym or "").upper())
    if not m:
        return None
    base, quote = m.group(1), m.group(2)
    if quote in ("USD", "USDT"):
        quote = "USDT"
    return base + quote


def _binance_klines(bsym, interval="1s", limit=1000, end_ms=None):
    q = {"symbol": bsym, "interval": interval, "limit": min(1000, limit)}
    if end_ms:
        q["endTime"] = int(end_ms)
    last = None
    for host in BINANCE_HOSTS:
        try:
            return http_json(host + "/api/v3/klines?" + urllib.parse.urlencode(q),
                             timeout=12)
        except Exception as e:
            last = e
            continue
    raise RuntimeError("Binance nicht erreichbar: %s" % str(last)[:100])


def _aggregate(series, factor):
    """1s-Kerzen zu n-Sekunden-Kerzen zusammenfassen."""
    if factor <= 1:
        return series
    T, O, H, L, C, V = [], [], [], [], [], []
    n = len(series["t"])
    i = 0
    while i < n:
        bucket = (series["t"][i] // factor) * factor
        j = i
        hi, lo, vol = series["h"][i], series["l"][i], 0.0
        while j < n and (series["t"][j] // factor) * factor == bucket:
            hi = max(hi, series["h"][j])
            lo = min(lo, series["l"][j])
            vol += series["v"][j] or 0
            j += 1
        T.append(bucket); O.append(series["o"][i]); H.append(hi)
        L.append(lo); C.append(series["c"][j - 1]); V.append(int(vol))
        i = j
    return {"t": T, "o": O, "h": H, "l": L, "c": C, "v": V}


def fetch_seconds(symbol, iv):
    """Sekundenchart fuer ein Krypto-Symbol."""
    factor = SEC_INTERVALS[iv]
    key = "sec:%s:%s" % (symbol, iv)
    hit = CACHE.get(key, 8)
    if hit is not None:
        return hit

    if DEMO:
        n = {1: 900, 5: 600, 15: 333, 30: 166}[factor]
        ser = _demo_series(symbol, n, factor)
        meta = _demo_quote(symbol)
        meta["price"] = ser["c"][-1]
        out = {"meta": meta, "series": ser, "source": "DEMO",
               "spanSec": (ser["t"][-1] - ser["t"][0]) if len(ser["t"]) > 1 else 0}
        CACHE.put(key, out)
        return out

    bsym = binance_symbol(symbol)
    if not bsym:
        raise RuntimeError("Sekunden-Kerzen gibt es nur fuer Krypto")

    pages = SEC_PAGES.get(factor, 3)
    rows, end_ms = [], None
    for _ in range(pages):
        chunk = _binance_klines(bsym, "1s", 1000, end_ms)
        if not chunk:
            break
        rows = chunk + rows
        end_ms = int(chunk[0][0]) - 1
        if len(chunk) < 1000:
            break

    if not rows:
        raise RuntimeError("keine Sekundendaten erhalten")

    base = {"t": [], "o": [], "h": [], "l": [], "c": [], "v": []}
    for r in rows:
        base["t"].append(int(r[0]) // 1000)
        base["o"].append(float(r[1])); base["h"].append(float(r[2]))
        base["l"].append(float(r[3])); base["c"].append(float(r[4]))
        base["v"].append(float(r[5]))
    ser = _aggregate(base, factor)

    meta = get_quote(symbol)
    if not meta.get("ok"):
        meta = {"symbol": symbol, "ok": True, "name": symbol,
                "currency": "USD", "exchange": "Binance"}
    meta = dict(meta)
    last = ser["c"][-1]
    prev = meta.get("prevClose")
    meta["price"] = last
    if prev:
        meta["change"] = round(last - prev, 6)
        meta["changePct"] = round((last / prev - 1) * 100, 3)
    meta["exchange"] = (meta.get("exchange") or "") + " / Binance 1s"
    out = {"meta": meta, "series": ser, "source": "BINANCE",
           "spanSec": (ser["t"][-1] - ser["t"][0]) if len(ser["t"]) > 1 else 0}
    CACHE.put(key, out)
    return out

# ---------------------------------------------------------------------------
#  Fundamentaldaten
# ---------------------------------------------------------------------------
FUND_MODULES = ("summaryDetail,defaultKeyStatistics,financialData,"
                "assetProfile,calendarEvents,price,earnings,"
                "incomeStatementHistory,recommendationTrend")

def _num(d, *keys):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    if isinstance(cur, dict):
        return cur.get("raw")
    if isinstance(cur, (int, float)):
        return cur
    return None

def get_profile(symbol):
    key = "prof:" + symbol
    hit = CACHE.get(key, 3600)
    if hit is not None:
        return hit
    if DEMO:
        rnd = random.Random(hash(symbol))
        out = {"symbol": symbol, "ok": True, "demo": True,
               "sector": "Technology", "industry": "Software",
               "country": "United States", "employees": rnd.randint(500, 200000),
               "summary": "Demo-Profil. Echte Fundamentaldaten erscheinen im Live-Modus.",
               "marketCap": rnd.randint(5, 3000) * 1e9,
               "trailingPE": round(rnd.uniform(8, 45), 2),
               "forwardPE": round(rnd.uniform(8, 35), 2),
               "priceToBook": round(rnd.uniform(0.8, 15), 2),
               "pegRatio": round(rnd.uniform(0.5, 3.5), 2),
               "dividendYield": round(rnd.uniform(0, 4), 2),
               "beta": round(rnd.uniform(0.4, 2.2), 2),
               "profitMargin": round(rnd.uniform(-5, 35), 2),
               "operatingMargin": round(rnd.uniform(-5, 45), 2),
               "revenueGrowth": round(rnd.uniform(-15, 60), 2),
               "earningsGrowth": round(rnd.uniform(-30, 80), 2),
               "returnOnEquity": round(rnd.uniform(-10, 60), 2),
               "debtToEquity": round(rnd.uniform(0, 250), 1),
               "currentRatio": round(rnd.uniform(0.5, 4), 2),
               "totalRevenue": rnd.randint(1, 400) * 1e9,
               "ebitda": rnd.randint(1, 120) * 1e9,
               "freeCashflow": rnd.randint(-5, 100) * 1e9,
               "targetMean": None, "recommendation": "buy",
               "nextEarnings": None, "revenueHistory": []}
        CACHE.put(key, out)
        return out
    try:
        j = yahoo_json("/v10/finance/quoteSummary/" + urllib.parse.quote(symbol),
                       {"modules": FUND_MODULES}, host="query2", need_crumb=True)
        res = ((j.get("quoteSummary") or {}).get("result") or [None])[0]
        if not res:
            raise RuntimeError("keine Fundamentaldaten")
        sd = res.get("summaryDetail") or {}
        ks = res.get("defaultKeyStatistics") or {}
        fd = res.get("financialData") or {}
        ap = res.get("assetProfile") or {}
        ce = res.get("calendarEvents") or {}
        pc = 100.0
        def pct(x):
            return round(x * pc, 2) if isinstance(x, (int, float)) else None
        rev_hist = []
        for it in ((res.get("earnings") or {}).get("financialsChart") or {}).get("yearly", []) or []:
            rev_hist.append({"year": it.get("date"),
                             "revenue": _num(it, "revenue"),
                             "earnings": _num(it, "earnings")})
        ne = None
        try:
            ed = ((ce.get("earnings") or {}).get("earningsDate") or [])
            if ed:
                ne = ed[0].get("raw")
        except Exception:
            pass
        out = {
            "symbol": symbol, "ok": True,
            "sector": ap.get("sector"), "industry": ap.get("industry"),
            "country": ap.get("country"), "website": ap.get("website"),
            "employees": ap.get("fullTimeEmployees"),
            "summary": (ap.get("longBusinessSummary") or "")[:1200],
            "marketCap": _num(sd, "marketCap") or _num(res, "price", "marketCap"),
            "trailingPE": _num(sd, "trailingPE"), "forwardPE": _num(sd, "forwardPE"),
            "priceToBook": _num(ks, "priceToBook"), "pegRatio": _num(ks, "pegRatio"),
            "dividendYield": pct(_num(sd, "dividendYield")),
            "payoutRatio": pct(_num(sd, "payoutRatio")),
            "beta": _num(sd, "beta") or _num(ks, "beta"),
            "profitMargin": pct(_num(fd, "profitMargins")),
            "operatingMargin": pct(_num(fd, "operatingMargins")),
            "grossMargin": pct(_num(fd, "grossMargins")),
            "revenueGrowth": pct(_num(fd, "revenueGrowth")),
            "earningsGrowth": pct(_num(fd, "earningsGrowth")),
            "returnOnEquity": pct(_num(fd, "returnOnEquity")),
            "returnOnAssets": pct(_num(fd, "returnOnAssets")),
            "debtToEquity": _num(fd, "debtToEquity"),
            "currentRatio": _num(fd, "currentRatio"),
            "totalRevenue": _num(fd, "totalRevenue"),
            "totalCash": _num(fd, "totalCash"), "totalDebt": _num(fd, "totalDebt"),
            "ebitda": _num(fd, "ebitda"), "freeCashflow": _num(fd, "freeCashflow"),
            "targetMean": _num(fd, "targetMeanPrice"),
            "targetHigh": _num(fd, "targetHighPrice"),
            "targetLow": _num(fd, "targetLowPrice"),
            "numAnalysts": _num(fd, "numberOfAnalystOpinions"),
            "recommendation": fd.get("recommendationKey"),
            "eps": _num(ks, "trailingEps"), "epsForward": _num(ks, "forwardEps"),
            "sharesOut": _num(ks, "sharesOutstanding"),
            "shortPctFloat": pct(_num(ks, "shortPercentOfFloat")),
            "nextEarnings": ne, "revenueHistory": rev_hist,
        }
    except Exception as e:
        out = {"symbol": symbol, "ok": False, "error": str(e)[:160]}
    CACHE.put(key, out)
    return out

# ---------------------------------------------------------------------------
#  News + Sentiment
# ---------------------------------------------------------------------------
POS = ("beat beats beating surge surges surged soar soars soared rally rallies "
       "rallied jump jumps jumped gain gains gained rise rises rose climb climbs "
       "climbed record high highs strong stronger strength outperform upgrade "
       "upgraded raises raised boost boosts boosted profit profits growth grows "
       "expands expansion win wins won approval approved breakthrough optimism "
       "bullish buyback dividend upside momentum recovery rebound top tops topped "
       "exceeds exceeded solid robust surges positive success successful").split()
NEG = ("miss misses missed plunge plunges plunged slump slumps slumped fall falls "
       "fell drop drops dropped decline declines declined sink sinks sank tumble "
       "tumbles tumbled loss losses losing weak weaker weakness underperform "
       "downgrade downgraded cuts cut cutting slash slashed warns warning warned "
       "lawsuit probe investigation fraud recall layoff layoffs bankruptcy default "
       "risk risks bearish selloff crash correction fears fear concern concerns "
       "slowdown halt halted delay delayed negative disappoint disappointing "
       "sues fined fine penalty").split()
INTENS = {"very": 1.4, "sharply": 1.5, "massive": 1.6, "record": 1.4,
          "slightly": 0.6, "modest": 0.7, "slight": 0.6}
NEGATORS = {"not", "no", "never", "without", "fails", "fail", "unlikely"}

def score_sentiment(text):
    if not text:
        return 0.0, []
    words = re.findall(r"[a-zA-Z']+", text.lower())
    score, hits = 0.0, []
    for i, w in enumerate(words):
        base = 0.0
        if w in POS:
            base = 1.0
        elif w in NEG:
            base = -1.0
        if base == 0.0:
            continue
        mult = 1.0
        if i > 0:
            prev = words[i - 1]
            mult *= INTENS.get(prev, 1.0)
            if prev in NEGATORS:
                mult *= -0.8
        score += base * mult
        hits.append(w)
    if not hits:
        return 0.0, []
    norm = max(-1.0, min(1.0, score / (math.sqrt(len(hits) + 1) * 1.9)))
    return round(norm, 3), hits[:6]

MARKET_FEEDS = [
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ("CNBC Markets", "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
    ("CNBC Top", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("Investing.com", "https://www.investing.com/rss/news_25.rss"),
    ("Handelsblatt", "https://www.handelsblatt.com/contentexport/feed/finanzen"),
    ("FAZ Wirtschaft", "https://www.faz.net/rss/aktuell/wirtschaft/"),
]

def _parse_rss(xml_text, source):
    items = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return items
    nodes = root.iter("item")
    for it in nodes:
        title = (it.findtext("title") or "").strip()
        if not title:
            continue
        link = (it.findtext("link") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()
        desc = re.sub(r"<[^>]+>", " ", it.findtext("description") or "")[:300].strip()
        ts = _parse_date(pub)
        s, hits = score_sentiment(title + " " + desc)
        items.append({"title": title, "link": link, "source": source,
                      "published": pub, "ts": ts, "summary": desc,
                      "sentiment": s, "cues": hits})
    if not items:  # Atom
        ns = "{http://www.w3.org/2005/Atom}"
        for it in root.iter(ns + "entry"):
            title = (it.findtext(ns + "title") or "").strip()
            if not title:
                continue
            ln = it.find(ns + "link")
            link = ln.get("href") if ln is not None else ""
            pub = (it.findtext(ns + "updated") or "").strip()
            s, hits = score_sentiment(title)
            items.append({"title": title, "link": link, "source": source,
                          "published": pub, "ts": _parse_date(pub),
                          "summary": "", "sentiment": s, "cues": hits})
    return items

_MONTHS = {m: i + 1 for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}

def _parse_date(s):
    if not s:
        return None
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s+(\d{2}):(\d{2}):(\d{2})", s)
    if m:
        d, mo, y, H, M, S = m.groups()
        try:
            return int(datetime(int(y), _MONTHS.get(mo, 1), int(d), int(H),
                                int(M), int(S), tzinfo=timezone.utc).timestamp())
        except Exception:
            return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})", s)
    if m:
        y, mo, d, H, M, S = [int(x) for x in m.groups()]
        try:
            return int(datetime(y, mo, d, H, M, S, tzinfo=timezone.utc).timestamp())
        except Exception:
            return None
    return None

DEMO_HEADLINES = [
    "Chipmaker beats quarterly estimates as AI demand surges",
    "Fed signals patience, markets rally on rate-cut hopes",
    "Retailer warns of weak consumer spending, shares plunge",
    "Regulator opens probe into cloud pricing practices",
    "Automaker raises full-year guidance after strong deliveries",
    "Oil slumps as OPEC+ delays output decision",
    "Bank downgraded on credit quality concerns",
    "Record buyback announced, stock jumps in late trading",
]

def get_news(symbol=None, limit=40):
    key = "news:" + (symbol or "_market")
    hit = CACHE.get(key, 240)
    if hit is not None:
        return hit
    if DEMO:
        rnd = random.Random(hash(key) & 0xFFFF)
        out = []
        for i in range(limit):
            t = rnd.choice(DEMO_HEADLINES)
            if symbol:
                t = symbol + ": " + t
            s, h = score_sentiment(t)
            out.append({"title": t, "link": "#", "source": "DEMO",
                        "published": "", "ts": int(time.time()) - i * 1800,
                        "summary": "", "sentiment": s, "cues": h})
        CACHE.put(key, out)
        return out
    feeds = []
    if symbol:
        feeds = [("Yahoo " + symbol,
                  "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%s&region=US&lang=en-US"
                  % urllib.parse.quote(symbol))]
    else:
        feeds = MARKET_FEEDS
    items = []

    def pull(f):
        try:
            return _parse_rss(http_get(f[1], timeout=10), f[0])
        except Exception as e:
            log("feed fail", f[0], e)
            return []

    with futures.ThreadPoolExecutor(max_workers=max(1, len(feeds))) as ex:
        for r in ex.map(pull, feeds):
            items.extend(r)
    if symbol and not items:
        try:
            j = yahoo_json("/v1/finance/search",
                           {"q": symbol, "quotesCount": 0, "newsCount": 20})
            for n in j.get("news") or []:
                s, h = score_sentiment(n.get("title", ""))
                items.append({"title": n.get("title", ""),
                              "link": n.get("link", ""),
                              "source": n.get("publisher", "Yahoo"),
                              "published": "", "ts": n.get("providerPublishTime"),
                              "summary": "", "sentiment": s, "cues": h})
        except Exception as e:
            log("search-news fail", e)
    seen, uniq = set(), []
    for it in items:
        k = it["title"][:90].lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(it)
    uniq.sort(key=lambda x: x.get("ts") or 0, reverse=True)
    uniq = uniq[:limit]
    CACHE.put(key, uniq)
    return uniq

# ---------------------------------------------------------------------------
#  Suche
# ---------------------------------------------------------------------------
def search_symbols(q, limit=12):
    if DEMO:
        return [{"symbol": q.upper(), "name": "Demo Treffer", "exchange": "DEMO",
                 "type": "EQUITY"}]
    key = "search:" + q.lower()
    hit = CACHE.get(key, 900)
    if hit is not None:
        return hit
    try:
        j = yahoo_json("/v1/finance/search",
                       {"q": q, "quotesCount": limit, "newsCount": 0,
                        "enableFuzzyQuery": "true"})
        out = []
        for r in j.get("quotes") or []:
            if not r.get("symbol"):
                continue
            out.append({"symbol": r["symbol"],
                        "name": r.get("longname") or r.get("shortname") or "",
                        "exchange": r.get("exchDisp") or r.get("exchange") or "",
                        "type": r.get("quoteType") or ""})
        CACHE.put(key, out)
        return out
    except Exception as e:
        return [{"symbol": q.upper(), "name": "(Suche nicht verfuegbar: %s)"
                 % str(e)[:60], "exchange": "", "type": ""}]

# ---------------------------------------------------------------------------
#  Technische Indikatoren
# ---------------------------------------------------------------------------
def sma(vals, n):
    out, s = [], 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        out.append(round(s / n, 4) if i >= n - 1 else None)
    return out

def ema(vals, n):
    out, k, prev = [], 2.0 / (n + 1), None
    for i, v in enumerate(vals):
        prev = v if prev is None else v * k + prev * (1 - k)
        out.append(round(prev, 4) if i >= n - 1 else None)
    return out

def rsi(vals, n=14):
    if len(vals) < n + 1:
        return [None] * len(vals)
    out = [None] * len(vals)
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = vals[i] - vals[i - 1]
        gains += max(d, 0.0); losses += max(-d, 0.0)
    ag, al = gains / n, losses / n
    out[n] = 100.0 if al == 0 else round(100 - 100 / (1 + ag / al), 2)
    for i in range(n + 1, len(vals)):
        d = vals[i] - vals[i - 1]
        ag = (ag * (n - 1) + max(d, 0.0)) / n
        al = (al * (n - 1) + max(-d, 0.0)) / n
        out[i] = 100.0 if al == 0 else round(100 - 100 / (1 + ag / al), 2)
    return out

def macd(vals, fast=12, slow=26, sig=9):
    ef, es = ema(vals, fast), ema(vals, slow)
    line = [(ef[i] - es[i]) if (ef[i] is not None and es[i] is not None) else None
            for i in range(len(vals))]
    valid = [x for x in line if x is not None]
    sg = ema(valid, sig)
    signal, j = [None] * len(line), 0
    for i in range(len(line)):
        if line[i] is not None:
            signal[i] = sg[j]; j += 1
    hist = [(line[i] - signal[i]) if (line[i] is not None and signal[i] is not None)
            else None for i in range(len(line))]
    return line, signal, hist

def bollinger(vals, n=20, k=2.0):
    mid = sma(vals, n)
    up, lo = [None] * len(vals), [None] * len(vals)
    for i in range(n - 1, len(vals)):
        w = vals[i - n + 1:i + 1]
        mu = sum(w) / n
        sd = math.sqrt(sum((x - mu) ** 2 for x in w) / n)
        up[i] = round(mu + k * sd, 4); lo[i] = round(mu - k * sd, 4)
    return up, mid, lo

def atr(h, l, c, n=14):
    trs = []
    for i in range(len(c)):
        if i == 0:
            trs.append(h[i] - l[i])
        else:
            trs.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    return ema(trs, n)

def technicals(series):
    c = series["c"]
    if len(c) < 5:
        return {}
    line, signal, hist = macd(c)
    bu, bm, bl = bollinger(c)
    r = rsi(c)
    def last(a):
        for x in reversed(a):
            if x is not None:
                return x
        return None
    def perf(days):
        if len(c) > days:
            return round((c[-1] / c[-1 - days] - 1) * 100, 2)
        return None
    return {
        "sma20": sma(c, 20), "sma50": sma(c, 50), "sma200": sma(c, 200),
        "ema12": ema(c, 12), "rsi": r, "macd": line, "macdSignal": signal,
        "macdHist": hist, "bbUpper": bu, "bbMid": bm, "bbLower": bl,
        "atr": atr(series["h"], series["l"], c),
        "last": {"rsi": last(r), "sma20": last(sma(c, 20)),
                 "sma50": last(sma(c, 50)), "sma200": last(sma(c, 200)),
                 "macd": last(line), "macdSignal": last(signal),
                 "atr": last(atr(series["h"], series["l"], c))},
        "perf": {"d1": perf(1), "w1": perf(5), "m1": perf(21), "m3": perf(63),
                 "m6": perf(126), "y1": perf(252)},
    }

# ---------------------------------------------------------------------------
#  Screener
# ---------------------------------------------------------------------------
SCREEN_SETS = {
    "us": UNIVERSE["US_MEGA"],
    "de": UNIVERSE["DE"],
    "eu": UNIVERSE["EU"],
    "equities": universe_equities(),
    "crypto": UNIVERSE["CRYPTO"],
    "fx": UNIVERSE["FX"],
    "commod": UNIVERSE["COMMOD"],
    "index": UNIVERSE["INDEX"],
}

def screen(set_name="equities", with_fundamentals=False, limit=200):
    syms = SCREEN_SETS.get(set_name, SCREEN_SETS["equities"])[:limit]
    rows = get_quotes(syms, workers=8)
    rows = [r for r in rows if r.get("ok")]
    if with_fundamentals:
        with futures.ThreadPoolExecutor(max_workers=6) as ex:
            profs = list(ex.map(get_profile, [r["symbol"] for r in rows]))
        for r, p in zip(rows, profs):
            if p.get("ok"):
                for k in ("marketCap", "trailingPE", "forwardPE", "priceToBook",
                          "dividendYield", "profitMargin", "revenueGrowth",
                          "returnOnEquity", "debtToEquity", "beta", "sector",
                          "pegRatio", "targetMean", "recommendation"):
                    r[k] = p.get(k)
    return rows

# ---------------------------------------------------------------------------
#  Zustand: Watchlists, Portfolio, Alerts
# ---------------------------------------------------------------------------
DEFAULT_STATE = {
    "watchlists": {
        "MAIN": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",
                 "AVGO", "AMD", "NFLX", "ORCL", "CRM", "PLTR", "COIN", "MU",
                 "ARM", "UBER", "DIS", "JPM", "V", "MA", "WMT", "COST",
                 "LLY", "UNH", "XOM", "BA", "GS"],
        "MAKRO": ["^GSPC", "^NDX", "^DJI", "^RUT", "^VIX", "^GDAXI",
                  "^STOXX50E", "^FTSE", "^N225", "^HSI",
                  "EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X", "USDCAD=X",
                  "AUDUSD=X", "GC=F", "SI=F", "HG=F", "CL=F", "BZ=F", "NG=F",
                  "^TNX", "^TYX", "BTC-USD", "ETH-USD"],
        "DAX": ["SAP.DE", "SIE.DE", "ALV.DE", "DTE.DE", "AIR.DE", "MBG.DE",
                "BMW.DE", "BAS.DE", "BAYN.DE", "VOW3.DE", "IFX.DE", "MUV2.DE",
                "DBK.DE", "ADS.DE", "RWE.DE", "MRK.DE", "HEN3.DE", "P911.DE",
                "ZAL.DE", "RHM.DE", "CBK.DE", "1COV.DE", "EOAN.DE", "FRE.DE",
                "HEI.DE"],
        "KRYPTO": ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "BNB-USD",
                   "ADA-USD", "DOGE-USD", "LINK-USD", "AVAX-USD", "LTC-USD"],
        "EUROPA": ["ASML.AS", "MC.PA", "OR.PA", "TTE.PA", "SAN.PA", "AIR.PA",
                   "NESN.SW", "NOVN.SW", "ROG.SW", "UBSG.SW", "SHEL.L",
                   "AZN.L", "HSBA.L", "ULVR.L", "BP.L", "NOVO-B.CO",
                   "ISP.MI", "ENI.MI"],
    },
    "positions": [],
    "alerts": [],
    "settings": {"refresh": 20, "theme": "amber", "layout": "monitor"},
}
_state_lock = threading.Lock()

def load_state():
    with _state_lock:
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                s = json.load(f)
            for k, v in DEFAULT_STATE.items():
                s.setdefault(k, v)
            # Grow existing watchlists with newly-added defaults, without
            # touching symbols the user added themselves or reordering theirs.
            wl = s.get("watchlists")
            if isinstance(wl, dict):
                removed = set(s.get("wl_removed") or [])
                for name, defaults in DEFAULT_STATE["watchlists"].items():
                    cur = wl.get(name)
                    if cur is None:
                        wl[name] = list(defaults)
                        continue
                    if not isinstance(cur, list):
                        continue
                    have = set(cur)
                    cur.extend(t for t in defaults
                               if t not in have and t not in removed)
            return s
        except Exception:
            return json.loads(json.dumps(DEFAULT_STATE))

def save_state(s):
    with _state_lock:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2, ensure_ascii=False)
        os.replace(tmp, STATE_FILE)
    return s


# ---------------------------------------------------------------------------
#  Paper-Konto (vom Bot nebenan)  -- ADDED
#  Liest paper_book.json aus dem uebergeordneten Ordner. Rein lesend; wenn die
#  Datei fehlt, meldet der Endpunkt einfach "nicht vorhanden".
# ---------------------------------------------------------------------------
PAPER_BOOK = os.path.join(os.path.dirname(APP_DIR), "paper_book.json")
PAPER_START = 100000.0

# Wenn der Bot woanders laeuft (z.B. auf dem Handy), zeigt dieses Terminal
# dessen Buch statt eines eigenen. Sonst haette man zwei Konten, die
# auseinanderlaufen, und keines waere die Wahrheit.
#   setx PAPER_BOOK_URL http://192.168.x.x:8765/api/paper/book
PAPER_BOOK_URL = os.environ.get("PAPER_BOOK_URL", "").strip()
_REMOTE_CACHE = {"book": None, "ts": 0.0, "err": None}


def _read_book():
    """Das Buch lesen - lokal, oder vom Bot-Geraet.

    Bei der Fernvariante wird die letzte gute Antwort bis zu 60 Sekunden
    weiterverwendet. Ein kurzer WLAN-Aussetzer soll das Portfolio nicht
    leerraeumen; ein dauerhaft totes Geraet aber schon sichtbar werden.
    """
    if not PAPER_BOOK_URL:
        with open(PAPER_BOOK, "r", encoding="utf-8") as f:
            return json.load(f), None
    now = time.time()
    try:
        req = urllib.request.Request(PAPER_BOOK_URL,
                                     headers={"User-Agent": "terminal"})
        with urllib.request.urlopen(req, timeout=4) as r:
            b = json.loads(r.read().decode("utf-8", "replace"))
        _REMOTE_CACHE.update({"book": b, "ts": now, "err": None})
        return b, None
    except Exception as e:
        age = now - _REMOTE_CACHE["ts"]
        if _REMOTE_CACHE["book"] is not None and age < 60:
            return _REMOTE_CACHE["book"], "Bot-Geraet gerade nicht erreichbar"
        raise


def account_view():
    try:
        b, warn = _read_book()
    except Exception:
        return {"present": False}

    closed = b.get("closed") or []
    openp = b.get("open") or []
    realised = sum(float(c.get("pnl") or 0) for c in closed)
    cash = float(b.get("equity") or PAPER_START)

    # unrealised, valued from live quotes
    unreal = 0.0
    syms = {}
    for p in openp:
        y = p.get("yahoo") or p.get("symbol")
        syms.setdefault(y, []).append(p)
    if syms:
        try:
            qs = {q["symbol"]: q for q in get_quotes(list(syms))}
        except Exception:
            qs = {}
        for y, group in syms.items():
            px = (qs.get(y) or {}).get("price")
            if px is None:
                continue
            for p in group:
                d = 1 if p.get("direction") == "BUY" else -1
                unreal += (px - float(p.get("entry") or 0)) * float(p.get("qty") or 0) * d

    # --- open positions, priced live, with SL/TP distances ---
    open_rows = []
    for p in openp:
        y = p.get("yahoo") or p.get("symbol")
        px = (qs.get(y) or {}).get("price") if syms else None
        d = 1 if p.get("direction") == "BUY" else -1
        entry = float(p.get("entry") or 0)
        qty = float(p.get("qty") or 0)
        stop = float(p.get("stop") or 0)
        tgt = float(p.get("target") or 0)
        risk = abs(entry - stop)
        pnl = ((px - entry) * qty * d) if px else None
        open_rows.append({
            "id": p.get("id"), "cand": p.get("cand"), "symbol": p.get("symbol"),
            "yahoo": y, "direction": p.get("direction"),
            "entry": entry, "stop": stop, "target": tgt, "qty": qty,
            "price": px, "opened": p.get("opened"),
            "riskAmount": float(p.get("risk_amount") or 0),
            "pnl": round(pnl, 2) if pnl is not None else None,
            "rNow": round(((px - entry) * d / risk), 2) if (px and risk) else None,
            "toStopPct": round(abs(px - stop) / px * 100, 2) if px else None,
            "toTargetPct": round(abs(tgt - px) / px * 100, 2) if px else None,
            "reason": p.get("reason", ""),
        })

    # --- closed trades, newest first ---
    hist = []
    for c in sorted(closed, key=lambda x: x.get("closed_at") or "", reverse=True)[:200]:
        hist.append({
            "closedAt": c.get("closed_at"), "cand": c.get("cand"),
            "symbol": c.get("symbol"), "direction": c.get("direction"),
            "entry": c.get("entry"), "exit": c.get("exit"),
            "stop": c.get("stop"), "target": c.get("target"),
            "outcome": c.get("outcome"), "r": c.get("r"), "pnl": c.get("pnl"),
            "opened": c.get("opened"), "reason": c.get("reason", ""),
        })

    # --- realised P&L per calendar day, for the heatmap ---
    from datetime import timedelta as _td
    daymap = {}
    for c in closed:
        d = (c.get("closed_at") or "")[:10]
        if not d:
            continue
        e = daymap.setdefault(d, {"pnl": 0.0, "n": 0, "wins": 0})
        e["pnl"] += float(c.get("pnl") or 0)
        e["n"] += 1
        if float(c.get("r") or 0) > 0:
            e["wins"] += 1
    daily = []
    if daymap:
        first = datetime.fromisoformat(min(daymap)).date()
        today = datetime.now(timezone.utc).date()
        # always show at least the last 8 weeks, and never start mid-week
        span_start = min(first, today - _td(days=55))
        span_start -= _td(days=span_start.weekday())
        d = span_start
        while d <= today:
            k = d.isoformat()
            e = daymap.get(k)
            daily.append({"date": k, "dow": d.weekday(),
                          "pnl": round(e["pnl"], 2) if e else 0.0,
                          "n": e["n"] if e else 0,
                          "wins": e["wins"] if e else 0})
            d += _td(days=1)

    rs = [float(c.get("r") or 0) for c in closed]
    wins = len([r for r in rs if r > 0])
    by = {}
    for c in closed:
        k = c.get("cand") or "?"
        e = by.setdefault(k, {"n": 0, "wins": 0, "r": 0.0, "pnl": 0.0})
        e["n"] += 1
        e["r"] += float(c.get("r") or 0)
        e["pnl"] += float(c.get("pnl") or 0)
        if float(c.get("r") or 0) > 0:
            e["wins"] += 1
    for k, e in by.items():
        e["meanR"] = round(e["r"] / e["n"], 3) if e["n"] else 0
        e["winPct"] = round(100 * e["wins"] / e["n"], 1) if e["n"] else 0
        e["pnl"] = round(e["pnl"], 2)
        e["r"] = round(e["r"], 2)

    return {"present": True,
            "remote": bool(PAPER_BOOK_URL),
            "remoteWarn": warn,
            "start": PAPER_START,
            "cash": round(cash, 2),
            "equity": round(cash + unreal, 2),
            "realised": round(realised, 2),
            "unrealised": round(unreal, 2),
            "returnPct": round((cash + unreal - PAPER_START) / PAPER_START * 100, 2),
            "openCount": len(openp),
            "closedCount": len(closed),
            "wins": wins,
            "winPct": round(100 * wins / len(rs), 1) if rs else 0,
            "totalR": round(sum(rs), 2),
            "meanR": round(sum(rs) / len(rs), 3) if rs else 0,
            "byCandidate": by,
            "daily": daily,
            "openRows": open_rows,
            "history": hist}


def paper_close(pos_id, price=None):
    """Close one bot position at the current market price.

    Charges the same spread the bot would have paid, so a hand-closed trade
    stays comparable with one that hit its stop or target. Marked
    outcome "manual" so it is never mistaken for a rule-based exit.
    """
    try:
        with open(PAPER_BOOK, "r", encoding="utf-8") as f:
            b = json.load(f)
    except Exception as e:
        return {"ok": False, "error": "paper_book.json nicht lesbar: %s" % e}

    openp = b.get("open") or []
    pos = next((p for p in openp if p.get("id") == pos_id), None)
    if pos is None:
        return {"ok": False, "error": "Position nicht gefunden"}

    y = pos.get("yahoo") or pos.get("symbol")
    if price is None:
        try:
            price = (get_quote(y) or {}).get("price")
        except Exception:
            price = None
    if not price:
        return {"ok": False, "error": "Kein Kurs fuer %s" % y}

    d = 1 if pos.get("direction") == "BUY" else -1
    half = float(price) * float(pos.get("spread_frac") or 0.0002) / 2.0
    exit_px = float(price) - half * d          # you cross the spread on exit
    entry = float(pos.get("entry") or 0)
    qty = float(pos.get("qty") or 0)
    pnl = (exit_px - entry) * qty * d
    risk_amt = float(pos.get("risk_amount") or 0)

    pos.update(closed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
               outcome="manual", exit=round(exit_px, 8),
               pnl=round(pnl, 2),
               r=round(pnl / risk_amt, 3) if risk_amt else 0.0)
    b["open"] = [p for p in openp if p.get("id") != pos_id]
    b.setdefault("closed", []).append(pos)
    b["equity"] = round(float(b.get("equity") or PAPER_START) + pnl, 2)

    tmp = PAPER_BOOK + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(b, f, indent=2)
    os.replace(tmp, PAPER_BOOK)
    return {"ok": True, "closed": {"symbol": pos.get("symbol"),
                                   "pnl": pos["pnl"], "r": pos["r"]}}

def portfolio_view():
    st = load_state()
    pos = st.get("positions") or []
    if not pos:
        return {"positions": [], "totals": {"value": 0, "cost": 0, "pnl": 0,
                                            "pnlPct": 0, "dayPnl": 0}}
    qs = {q["symbol"]: q for q in get_quotes([p["symbol"] for p in pos])}
    out, tv, tc, tday = [], 0.0, 0.0, 0.0
    for p in pos:
        q = qs.get(p["symbol"], {})
        px = q.get("price")
        qty = float(p.get("qty") or 0)
        cost = float(p.get("cost") or 0)
        val = (px or 0) * qty
        cb = cost * qty
        pnl = val - cb
        day = (q.get("change") or 0) * qty
        tv += val; tc += cb; tday += day
        out.append({**p, "price": px, "name": q.get("name") or p["symbol"],
                    "currency": q.get("currency"), "changePct": q.get("changePct"),
                    "value": round(val, 2), "costBasis": round(cb, 2),
                    "pnl": round(pnl, 2),
                    "pnlPct": round((pnl / cb * 100) if cb else 0, 2),
                    "dayPnl": round(day, 2)})
    for r in out:
        r["weight"] = round(r["value"] / tv * 100, 2) if tv else 0
    out.sort(key=lambda r: -r["value"])
    return {"positions": out,
            "totals": {"value": round(tv, 2), "cost": round(tc, 2),
                       "pnl": round(tv - tc, 2),
                       "pnlPct": round(((tv - tc) / tc * 100) if tc else 0, 2),
                       "dayPnl": round(tday, 2)}}

def check_alerts():
    st = load_state()
    alerts = st.get("alerts") or []
    active = [a for a in alerts if not a.get("triggered")]
    if not active:
        return []
    qs = {q["symbol"]: q for q in get_quotes(sorted({a["symbol"] for a in active}))}
    fired, changed = [], False
    for a in active:
        q = qs.get(a["symbol"]) or {}
        px = q.get("price")
        if px is None:
            continue
        op, tgt = a.get("op", ">"), float(a.get("value", 0))
        field = a.get("field", "price")
        cur = px if field == "price" else (q.get("changePct") or 0)
        hit = (cur > tgt) if op == ">" else (cur < tgt)
        if hit:
            a["triggered"] = int(time.time())
            a["triggerPrice"] = px
            fired.append({**a, "current": cur, "name": q.get("name")})
            changed = True
    if changed:
        save_state(st)
    return fired

# ---------------------------------------------------------------------------
#  Diagnose
# ---------------------------------------------------------------------------
def diagnostics():
    checks = []

    def add(name, fn):
        t0 = time.time()
        try:
            info = fn()
            checks.append({"name": name, "ok": True, "ms": int((time.time() - t0) * 1000),
                           "info": info})
        except Exception as e:
            checks.append({"name": name, "ok": False, "ms": int((time.time() - t0) * 1000),
                           "info": "%s: %s" % (type(e).__name__, str(e)[:140])})

    def _crumb_check():
        c = yahoo_crumb(force=True)
        if not c:
            raise RuntimeError("kein Crumb erhalten - Fundamentaldaten bleiben leer")
        return "Crumb erhalten"

    def _summary_check():
        pr = get_profile("AAPL")
        if not pr.get("ok"):
            raise RuntimeError(pr.get("error") or "keine Daten")
        return "Marktkapitalisierung %s" % pr.get("marketCap")

    def _batch_check():
        b = _batch_quotes(["AAPL", "SAP.DE", "BTC-USD"])
        if not b:
            raise RuntimeError("Batch-Endpunkt liefert nichts (Crumb fehlt?)")
        return "%d von 3 Symbolen" % len(b)

    def _search_check():
        r = search_symbols("apple")
        if not r or "(Suche nicht" in (r[0].get("name") or ""):
            raise RuntimeError("Suche liefert keine Treffer")
        return "%d Treffer" % len(r)

    def _news_check(sym, label):
        n = get_news(sym, 20)
        if not n:
            raise RuntimeError("keine Schlagzeilen empfangen")
        return "%d Schlagzeilen (%s)" % (len(n), label)

    add("Yahoo Chart (Kurse/Historie)",
        lambda: "AAPL = %s" % fetch_chart("AAPL", "5d", "1d")["meta"]["price"])
    add("Yahoo Batch-Quotes (Watchlist)", _batch_check)
    add("Yahoo Crumb (Fundamentaldaten)", _crumb_check)
    add("Yahoo quoteSummary (F3)", _summary_check)
    add("Yahoo Symbolsuche", _search_check)

    def _binance_check():
        d = fetch_seconds("BTC-USD", "1s")
        n = len(d["series"]["c"])
        return "%d Sekundenkerzen, letzter Kurs %s" % (n, d["series"]["c"][-1])

    add("Binance Sekundenkerzen (Krypto)", _binance_check)
    add("Markt-Nachrichten (RSS)", lambda: _news_check(None, "Markt"))
    add("Symbol-Nachrichten", lambda: _news_check("AAPL", "AAPL"))
    return {"demo": DEMO, "python": sys.version.split()[0],
            "cacheEntries": CACHE.stats(), "checks": checks,
            "time": int(time.time())}

# ---------------------------------------------------------------------------
#  HTTP-Server
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "Terminal/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if VERBOSE:
            sys.stderr.write("[http] %s - %s\n" % (self.address_string(), fmt % args))

    # -- helpers ----------------------------------------------------------
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str))

    def _err(self, msg, code=400):
        self._json({"ok": False, "error": str(msg)[:300]}, code)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    # -- routing ----------------------------------------------------------
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        p, q = u.path, urllib.parse.parse_qs(u.query)

        def one(k, d=None):
            v = q.get(k)
            return v[0] if v else d

        try:
            if p in ("/", "/index.html"):
                return self._serve_ui()
            if p == "/favicon.ico":
                return self._send(200, b"", "image/x-icon")
            if p == "/api/paper/book":
                # Rohes Buch fuer ein zweites Terminal auf einem anderen Geraet.
                try:
                    with open(PAPER_BOOK, "r", encoding="utf-8") as f:
                        return self._send(200, f.read().encode("utf-8"),
                                          "application/json; charset=utf-8")
                except Exception:
                    return self._json({"open": [], "closed": [],
                                       "equity": PAPER_START})
            if p == "/api/config":
                return self._json({"ok": True, "demo": DEMO,
                                   "universe": UNIVERSE,
                                   "tape": [{"s": t, "l": name_of(t)} for t in TAPE],
                                   "names": NAMES,
                                   "screenSets": sorted(SCREEN_SETS.keys()),
                                   "ranges": list(RANGE_MAP.keys()),
                                   "intervals": {k: valid_intervals(RANGE_MAP[k][0])
                                                 for k in RANGE_MAP},
                                   "defaultIntervals": {k: RANGE_MAP[k][1]
                                                        for k in RANGE_MAP},
                                   "version": "1.4"})
            if p == "/api/diag":
                return self._json(diagnostics())
            if p == "/api/quotes":
                syms = [s.strip() for s in (one("symbols", "") or "").split(",") if s.strip()]
                return self._json({"ok": True, "quotes": get_quotes(syms),
                                   "ts": int(time.time())})
            if p == "/api/chart":
                sym = one("symbol", "AAPL")
                rk = (one("range", "1y") or "1y").lower()
                rng, default_iv = RANGE_MAP.get(rk, RANGE_MAP["1y"])
                want = one("interval") or default_iv
                # --- Sekundenchart (nur Krypto) ---
                if want in SEC_INTERVALS and is_crypto(sym):
                    d = fetch_seconds(sym, want)
                    return self._json({"ok": True, "meta": d["meta"],
                                       "series": d["series"],
                                       "tech": technicals(d["series"]),
                                       "range": rk, "interval": want,
                                       "intervalAdjusted": False,
                                       "live": True, "source": d.get("source"),
                                       "spanSec": d.get("spanSec"),
                                       "validIntervals": valid_intervals(rng, sym)})
                if want in SEC_INTERVALS:
                    want = "1m"
                iv = fix_interval(rng, want)
                d = fetch_chart(sym, rng, iv)
                return self._json({"ok": True, "meta": d["meta"],
                                   "series": d["series"],
                                   "tech": technicals(d["series"]),
                                   "range": rk, "interval": iv,
                                   "intervalAdjusted": (iv != want),
                                   "live": False,
                                   "validIntervals": valid_intervals(rng, sym)})
            if p == "/api/profile":
                return self._json({"ok": True, "profile": get_profile(one("symbol", "AAPL"))})
            if p == "/api/news":
                sym = one("symbol")
                items = get_news(sym, int(one("limit", "40")))
                avg = round(sum(i["sentiment"] for i in items) / len(items), 3) if items else 0
                return self._json({"ok": True, "symbol": sym, "items": items,
                                   "avgSentiment": avg})
            if p == "/api/search":
                return self._json({"ok": True, "results": search_symbols(one("q", ""))})
            if p == "/api/screen":
                return self._json({"ok": True,
                                   "rows": screen(one("set", "equities"),
                                                  one("fund", "0") in ("1", "true"))})
            if p == "/api/state":
                return self._json({"ok": True, "state": load_state()})
            if p == "/api/account":
                return self._json({"ok": True, **account_view()})
            if p == "/api/portfolio":
                return self._json({"ok": True, **portfolio_view()})
            if p == "/api/alerts/check":
                return self._json({"ok": True, "fired": check_alerts(),
                                   "alerts": load_state().get("alerts", [])})
            return self._err("unbekannter Endpunkt: " + p, 404)
        except urllib.error.HTTPError as e:
            return self._err("Datenquelle HTTP %s (%s)" % (e.code, p), 502)
        except urllib.error.URLError as e:
            return self._err("Keine Verbindung zur Datenquelle: %s" % e.reason, 502)
        except Exception as e:
            log("ERR", p, repr(e))
            return self._err("%s: %s" % (type(e).__name__, e), 500)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        p, b = u.path, self._body()
        try:
            if p == "/api/state":
                st = load_state()
                if "watchlists" in b and isinstance(b["watchlists"], dict):
                    # A default symbol absent from an incoming list was deleted
                    # on purpose. Remember that, or load_state() would merge it
                    # straight back in on the next start.
                    gone = set(st.get("wl_removed") or [])
                    for name, defaults in DEFAULT_STATE["watchlists"].items():
                        incoming = b["watchlists"].get(name)
                        if isinstance(incoming, list):
                            gone |= {t for t in defaults if t not in incoming}
                        # a list the user deleted entirely: leave its defaults be
                    st["wl_removed"] = sorted(gone)
                for k in ("watchlists", "positions", "alerts", "settings"):
                    if k in b:
                        st[k] = b[k]
                return self._json({"ok": True, "state": save_state(st)})
            if p == "/api/paper/close":
                if PAPER_BOOK_URL:
                    # Das Buch gehoert dem anderen Geraet - dort schliessen
                    # lassen, statt hier eine Kopie zu veraendern, die beim
                    # naechsten Abruf sowieso ueberschrieben wuerde.
                    try:
                        base = PAPER_BOOK_URL.rsplit("/api/", 1)[0]
                        req = urllib.request.Request(
                            base + "/api/paper/close",
                            data=json.dumps({"id": b.get("id")}).encode(),
                            headers={"Content-Type": "application/json"})
                        with urllib.request.urlopen(req, timeout=8) as r:
                            out = json.loads(r.read().decode())
                        # kein Cache-Reset noetig: _read_book versucht
                        # ohnehin immer zuerst das Netz. Ein Reset wuerde nur
                        # den Puffer gegen WLAN-Aussetzer zerstoeren.
                        return self._json(out)
                    except Exception as e:
                        return self._json(
                            {"ok": False,
                             "error": "Bot-Geraet nicht erreichbar: %s" % e}, 502)
                res = paper_close(b.get("id"))
                if not res.get("ok"):
                    return self._json(res, 400)
                return self._json({"ok": True, **res, **account_view()})
            if p == "/api/position":
                st = load_state()
                pos = st.setdefault("positions", [])
                act = b.get("action", "add")
                if act == "delete":
                    st["positions"] = [x for x in pos if x.get("id") != b.get("id")]
                else:
                    rec = {"id": b.get("id") or ("p%d" % int(time.time() * 1000)),
                           "symbol": (b.get("symbol") or "").upper().strip(),
                           "qty": float(b.get("qty") or 0),
                           "cost": float(b.get("cost") or 0),
                           "note": b.get("note", ""),
                           "date": b.get("date") or datetime.now().strftime("%Y-%m-%d")}
                    pos = [x for x in pos if x.get("id") != rec["id"]]
                    pos.append(rec)
                    st["positions"] = pos
                save_state(st)
                return self._json({"ok": True, **portfolio_view()})
            if p == "/api/alert":
                st = load_state()
                al = st.setdefault("alerts", [])
                act = b.get("action", "add")
                if act == "delete":
                    st["alerts"] = [x for x in al if x.get("id") != b.get("id")]
                elif act == "clear":
                    st["alerts"] = [x for x in al if not x.get("triggered")]
                elif act == "reset":
                    for x in al:
                        if x.get("id") == b.get("id"):
                            x.pop("triggered", None)
                            x.pop("triggerPrice", None)
                else:
                    al.append({"id": "a%d" % int(time.time() * 1000),
                               "symbol": (b.get("symbol") or "").upper().strip(),
                               "field": b.get("field", "price"),
                               "op": b.get("op", ">"),
                               "value": float(b.get("value") or 0),
                               "note": b.get("note", "")})
                save_state(st)
                return self._json({"ok": True, "alerts": load_state().get("alerts", [])})
            return self._err("unbekannter Endpunkt: " + p, 404)
        except Exception as e:
            return self._err("%s: %s" % (type(e).__name__, e), 500)

    def _serve_ui(self):
        try:
            with open(UI_FILE, "rb") as f:
                html = f.read()
        except FileNotFoundError:
            return self._send(500, "ui.html fehlt neben terminal.py", "text/plain; charset=utf-8")
        self._send(200, html, "text/html; charset=utf-8")

# ---------------------------------------------------------------------------
def free_port(start):
    for port in range(start, start + 40):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit("kein freier Port gefunden")

def warmup():
    try:
        st = load_state()
        syms = []
        for v in st.get("watchlists", {}).values():
            syms.extend(v)
        get_quotes(list(dict.fromkeys(syms))[:40])
        get_news(None, 40)
        log("warmup fertig")
    except Exception as e:
        log("warmup fehler:", e)

def main():
    global DEMO, VERBOSE
    ap = argparse.ArgumentParser(description="Eigenes Markt-Terminal")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--demo", action="store_true", help="synthetische Daten, kein Internet")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    DEMO, VERBOSE = a.demo, a.verbose
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(STATE_FILE):
        save_state(json.loads(json.dumps(DEFAULT_STATE)))
    port = free_port(a.port)
    url = "http://%s:%d/" % (a.host, port)
    srv = ThreadingHTTPServer((a.host, port), Handler)
    srv.daemon_threads = True
    print("=" * 66)
    print("  TERMINAL laeuft%s" % ("  [DEMO-MODUS]" if DEMO else ""))
    print("  " + url)
    print("  Beenden mit Strg+C")
    print("=" * 66)
    threading.Thread(target=warmup, daemon=True).start()
    if not a.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nTerminal beendet.")
    finally:
        srv.server_close()

def _pause(msg="\nZum Schliessen die Eingabetaste druecken..."):
    """Haelt das Fenster offen, wenn per Doppelklick gestartet wurde."""
    try:
        input(msg)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        pass
    except Exception:
        import traceback
        print("\n" + "=" * 66)
        print("  FEHLER BEIM START")
        print("=" * 66)
        traceback.print_exc()
        print("=" * 66)
        print("  Bitte diesen Text abfotografieren oder kopieren.")
        _pause()
        sys.exit(1)
