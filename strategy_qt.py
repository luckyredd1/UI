"""Quarterly Theory (QT) — nach Traderdaye / ICT.

Der Tag wird in vier Sechs-Stunden-Quartale geteilt, in NEW YORKER Zeit:

    Q1  18:00-00:00   Accumulation   baut eine Spanne
    Q2  00:00-06:00   Manipulation   Raid durch die Q1-Spanne ("Judas Swing")
    Q3  06:00-12:00   Distribution   Bewegung in die Gegenrichtung
    Q4  12:00-18:00   Continuation   Fortsetzung oder Umkehr

Regel: In Q2 sticht der Kurs durch die Q1-Spanne und schliesst wieder
hinein. Danach wird fuer die Gegenbewegung in Q3 positioniert.

Unterschied zu strategy_session.py - und der ist der Grund, das ueberhaupt
getrennt zu bauen:

  1. Die Fenster sind an NEW YORKER Zeit gebunden, nicht an UTC. Damit
     verschieben sie sich mit der US-Sommerzeit. strategy_session rechnet
     in festen UTC-Stunden.
  2. Der Einstieg MUSS in Q3 liegen. strategy_session erlaubt ihn beliebig
     spaet, weil das Fenster dort nur den Sweep begrenzt.
  3. Die Spanne ist die des ganzen Q1, kein Swing-Punkt.

Ehrlichkeitshalber: das ist strukturell nah an sess_london_asia, dem
Kandidaten, der am 02.09.2026 mit -0,60R widerlegt wurde. Die drei Punkte
oben sind die echten Unterschiede - mehr ist es nicht.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import indicators as ind
import smc
from strategy_session import Context as _SessCtx  # nur fuer swing_points
from broker_mt5 import Candle

# Quartale in New Yorker Stunden: (Start, Ende)
QUARTERS = {"Q1": (18, 24), "Q2": (0, 6), "Q3": (6, 12), "Q4": (12, 18)}


def _dt(ts: str) -> datetime:
    return datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")


def _ny_offset(d: datetime) -> int:
    """Stunden, die New York hinter UTC liegt. 4 im Sommer, 5 im Winter.

    US-Regel: zweiter Sonntag im Maerz bis erster Sonntag im November.
    Ohne diese Umstellung liegen die Quartalsgrenzen im Winter eine Stunde
    daneben - genau der Fehler, den die Strategie nicht machen darf, weil
    sie ausschliesslich von Uhrzeiten lebt.
    """
    y = d.year
    mar = datetime(y, 3, 8)
    while mar.weekday() != 6:
        mar += timedelta(days=1)          # zweiter Sonntag im Maerz
    nov = datetime(y, 11, 1)
    while nov.weekday() != 6:
        nov += timedelta(days=1)          # erster Sonntag im November
    return 4 if mar <= d < nov else 5


class Context:
    __slots__ = ("high", "low", "close", "open", "atr", "q", "qday", "ranges",
                 "swing_h", "swing_l", "swing_n")

    def __init__(self, candles: list[Candle], p: dict):
        self.high = [c.high for c in candles]
        self.low = [c.low for c in candles]
        self.close = [c.close for c in candles]
        self.open = [c.open for c in candles]
        self.atr = ind.atr(self.high, self.low, self.close,
                           int(p.get("atr_len", 14)))
        # Swings nur fuer die MSS-Variante noetig, aber billig genug
        self.swing_n = int(p.get("swing_n", 2))
        self.swing_h, self.swing_l = smc.swing_points(self.high, self.low,
                                                      self.swing_n)

        # Jeden Balken einem Quartal und einem QT-Tag zuordnen. Der QT-Tag
        # beginnt mit Q1 um 18:00 NY - er laeuft dem Kalendertag also voraus.
        self.q: list[str] = []
        self.qday: list[str] = []
        # qt_shift_h verschiebt die GANZE Quartalseinteilung um n Stunden.
        # 0 ist die echte Lehrbuchlage. 6, 12 und 18 sind Scheinlagen mit
        # identischer Mechanik - die Kontrollgruppe. Findet die echte Lage
        # nichts, was die Scheinlagen nicht auch finden, dann traegt die
        # Quartalsstruktur nichts bei und QT ist nur ein Zeitfilter.
        shift = int(p.get("qt_shift_h", 0))
        for c in candles:
            u = _dt(c.ts)
            ny = u - timedelta(hours=_ny_offset(u)) + timedelta(hours=shift)
            h = ny.hour
            if 18 <= h < 24:
                qn, day = "Q1", (ny + timedelta(days=1)).strftime("%Y-%m-%d")
            elif h < 6:
                qn, day = "Q2", ny.strftime("%Y-%m-%d")
            elif h < 12:
                qn, day = "Q3", ny.strftime("%Y-%m-%d")
            else:
                qn, day = "Q4", ny.strftime("%Y-%m-%d")
            self.q.append(qn)
            self.qday.append(day)

        # Q1-Spanne je QT-Tag, erst gueltig wenn Q1 vorbei ist.
        # (hoch, tief, letzter Index von Q1)
        self.ranges: dict[str, tuple[float, float, int]] = {}
        cur = None
        hi = lo = None
        last = None
        for i in range(len(candles)):
            if self.q[i] == "Q1":
                d = self.qday[i]
                if d != cur:
                    cur, hi, lo, last = d, self.high[i], self.low[i], i
                else:
                    hi = max(hi, self.high[i])
                    lo = min(lo, self.low[i])
                    last = i
            elif cur is not None and self.q[i] != "Q1":
                self.ranges.setdefault(cur, (hi, lo, last))


def evaluate_at(candles, p, ctx: Context, i: int):
    """Signal am Balken i, oder None."""
    if i < int(p.get("min_bars", 200)) or i >= len(candles) - 1:
        return None
    # Einstiegsquartal. "Q3" ist die Lehrbuchregel; None ist die
    # Kontrollgruppe - derselbe Aufbau, nur ohne Zeitbedingung. Schlaegt Q3
    # die Kontrolle nicht, traegt das Quartalsfenster nichts bei.
    want_q = p.get("entry_quarter", "Q3")
    if want_q and ctx.q[i] != want_q:
        return None
    if not want_q and ctx.q[i] == "Q1":
        return None                            # in Q1 gibt es noch keine Spanne
    a = ctx.atr[i]
    if not a:
        return None
    day = ctx.qday[i]
    rng = ctx.ranges.get(day)
    if rng is None:
        return None
    q1_hi, q1_lo, q1_end = rng
    if q1_hi <= q1_lo:
        return None

    # --- Der Raid in Q2 -----------------------------------------------------
    min_pen = float(p.get("min_raid_atr", 0.15))
    # Wo darf der Raid stattfinden? "Q2" ist die QT-Lehrbuchregel. Alternativ
    # eine ICT-Killzone in UTC-Stunden - das ist die Kreuzung der beiden
    # Frameworks: QT liefert den Liquiditaets-Pool, ICT den Zeitpunkt.
    rw = p.get("raid_window", "Q2")
    kz = None
    if isinstance(rw, (tuple, list)):
        # Freie UTC-Stunden. Dient der Kontrollgruppe: dieselbe Killzone,
        # nur um n Stunden verschoben. Findet eine verschobene Zone dasselbe,
        # war nicht "London" der Grund, sondern irgendein Zeitfenster.
        kz = (int(rw[0]) % 24, int(rw[1]) % 24)
    elif rw and rw != "Q2":
        from strategy_session import WINDOWS
        kz = WINDOWS[rw]
    raid = None
    bullish = None
    for j in range(q1_end + 1, i):
        if kz is not None:
            hh = _dt(candles[j].ts).hour           # UTC-Stunde
            drin = (kz[0] <= hh < kz[1] if kz[0] < kz[1]
                    else hh >= kz[0] or hh < kz[1])   # Fenster ueber Mitternacht
            if not drin:
                continue
        elif rw == "Q2" and ctx.q[j] != "Q2":
            continue
        # Raid unter das Q1-Tief, Schluss wieder darueber -> Erwartung hoch
        if ctx.low[j] < q1_lo - min_pen * a and ctx.close[j] > q1_lo:
            raid, bullish = j, True
        # Raid ueber das Q1-Hoch, Schluss wieder darunter -> Erwartung runter
        elif ctx.high[j] > q1_hi + min_pen * a and ctx.close[j] < q1_hi:
            raid, bullish = j, False
    if raid is None:
        return None

    # --- Strukturbruch (MSS), optional -------------------------------------
    # Der Bestaetigungsschritt aus den ICT/SMC-Strategien: nach dem Raid muss
    # der Kurs ein Swing-Extrem von VOR dem Raid durchschliessen. Ohne ihn
    # wird jeder Raid gehandelt, auch die folgenlosen.
    zone_start = raid + 1
    if p.get("require_mss"):
        n_sw = ctx.swing_n
        if bullish:
            cand = [w.price for w in ctx.swing_h
                    if raid - 20 <= w.idx <= raid and w.idx + n_sw <= i]
            if not cand:
                return None
            barrier = max(cand)
            mss = next((j for j in range(raid + 1, i + 1)
                        if ctx.close[j] > barrier), None)
        else:
            cand = [w.price for w in ctx.swing_l
                    if raid - 20 <= w.idx <= raid and w.idx + n_sw <= i]
            if not cand:
                return None
            barrier = min(cand)
            mss = next((j for j in range(raid + 1, i + 1)
                        if ctx.close[j] < barrier), None)
        if mss is None or mss >= i:
            return None
        # Die Lucke muss zwischen Raid und Strukturbruch entstanden sein
        zone_start = raid + 1
        zone_end = mss
    else:
        zone_end = i - 1

    # --- Einstieg ueber eine offene Lucke in Richtung Q3 --------------------
    zones = smc.find_fvgs(ctx.high, ctx.low, zone_start, zone_end, bullish)
    zones = [g for g in zones if g.size >= float(p.get("min_fvg_atr", 0.10)) * a]
    zones = [g for g in zones
             if not smc.gap_filled(g, ctx.high, ctx.low, g.idx + 1, i - 1)]
    if not zones:
        return None
    gap = max(zones, key=lambda g: g.idx)
    tapped = ((ctx.low[i] <= gap.top and ctx.close[i] >= gap.bottom) if bullish
              else (ctx.high[i] >= gap.bottom and ctx.close[i] <= gap.top))
    if not tapped:
        return None

    entry = ctx.close[i]
    buf = float(p.get("stop_buffer_atr", 0.15))
    rr = float(p.get("rr", 2.0))
    if bullish:
        stop = ctx.low[raid] - buf * a
        if entry <= stop:
            return None
        dist = entry - stop
        target = entry + rr * dist
    else:
        stop = ctx.high[raid] + buf * a
        if entry >= stop:
            return None
        dist = stop - entry
        target = entry - rr * dist
    lo_ok = float(p.get("min_stop_atr", 0.3)) * a
    hi_ok = float(p.get("max_stop_atr", 6.0)) * a
    if not (lo_ok <= dist <= hi_ok):
        return None

    from strategy_session import Signal
    return Signal("BUY" if bullish else "SELL", entry, stop, target,
                  f"QT {day}: Q1-Spanne {q1_lo:.5f}-{q1_hi:.5f}, "
                  f"Raid in Q2 {'unten' if bullish else 'oben'}, "
                  f"FVG {gap.bottom:.5f}-{gap.top:.5f}, "
                  f"Stop {dist/a:.1f}xATR", candles[i].ts)


def evaluate(candles, p: dict):
    if len(candles) < int(p.get("min_bars", 200)):
        return None
    return evaluate_at(candles, p, Context(candles, p), len(candles) - 1)
