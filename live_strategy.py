"""Was der Bot ab dem 02.09.2026 tatsaechlich handelt - und warum genau das.

DIE EHRLICHE FASSUNG ZUERST
---------------------------
Diese Strategie hat KEINEN nachgewiesenen Vorteil. Sie ist nicht die beste
von vielen guten, sondern die einzige aus der ganzen Familie, die auf
ungesehenen Daten nicht messbar NEGATIV war. Ihr gemessener Wert ist:

    H1, Pruefteil, 223 Trades:   -0,0301R je Trade   (z = -0,27)
    M15, Pruefteil,  77 Trades:  -0,0699R je Trade   (z = -0,33)

Das ist null, nicht Gewinn. Der Bot laeuft deshalb ab jetzt als MESSGERAET,
nicht als Verdienstquelle: er sammelt Vorwaertsdaten auf Kursen, die es beim
Testen noch nicht gab. Das ist die einzige Art von Beleg, die diese
Untersuchung noch nicht hat.

WAS RAUSGEFLOGEN IST UND WARUM
------------------------------
Vorher liefen fuenf Kandidaten parallel auf M15. Vier davon sind inzwischen
gemessen negativ, nicht bloss unklar:

  sess_london_asia   -0,60R   (widerlegt am 02.09.2026)
  sess_ny_london     -0,41R   auf M15, -0,10R auf H1
  mtf_h4_m15         -0,46R   auf M15 (z = -2,37)
  mtf_h1_m15         gleiche Familie, gleiche Richtung

Uebrig bleibt der fuenfte - und der war die KONTROLLGRUPPE: derselbe
Liquiditaets-Pool, aber ohne jede Zeitbedingung. Dass ausgerechnet die
Kontrolle als einzige uebrig bleibt, ist das Ergebnis in einem Satz: die
Uhrzeiten haben nie etwas beigetragen.

Das ist keine nachtraegliche Rosinenpickerei. Es wird nichts Gutes
ausgewaehlt, sondern nachweislich Schlechtes entfernt. Was uebrig bleibt,
ist ausdruecklich nicht als "gut" markiert.

WARUM H1 UND NICHT MEHR M15
---------------------------
Reine Arithmetik, keine Anpassung. Der Stop-Abstand waechst etwa mit der
Wurzel der Zeit, der Spread bleibt gleich. Die Kosten in R sind auf H1 also
rund halb so gross. Bei einer Strategie, die bei null steht, ist das der
einzige Hebel, der ohne neue Annahme wirkt.

Zweitens: Yahoo gibt fuer H1 730 Tage Historie statt 60. Jede kuenftige
Auswertung hat damit zwoelfmal so viel Vergleichsmaterial.

DIE REGEL, IN WORTEN
--------------------
  1. Spanne der asiatischen Sitzung (00-07 UTC) als Liquiditaets-Pool.
  2. Der Kurs sticht durch diese Spanne und schliesst wieder hinein -
     zu JEDER Uhrzeit, das ist der Punkt.
  3. Danach ein Strukturbruch (MSS): Schluss durch ein Swing-Extrem von
     vor dem Stich.
  4. Einstieg an einer offenen Kurslucke (FVG oder iFVG) in Richtung des
     Strukturbruchs.
  5. Stop hinter das Extrem des Stichs, Ziel 2R - bei Krypto 4R, weil dort
     die Kosten hoeher sind und ein groesseres Ziel den Nachteil verkleinert.
  6. Kein Trade, dessen Kosten die noetige Trefferquote um mehr als 3,33
     Prozentpunkte anheben.

Diese Parameter sind ab hier FESTGESCHRIEBEN. Wer sie waehrend des
Vorwaertstests aendert, faengt den Test von vorne an - dann misst man wieder
nur, wie gut man die Vergangenheit anpassen kann.
"""
from __future__ import annotations

# Zeitrahmen des Bots. Siehe oben: halbe Kosten in R gegenueber M15.
TIMEFRAME = "H1"

BASIS = {
    "family": "session",
    "atr_len": 14,
    "min_bars": 200,
    "swing_n": 2,
    "stop_buffer_atr": 0.15,
    "min_stop_atr": 0.3,
    "max_stop_atr": 6.0,
    "min_fvg_atr": 0.10,
    "entry_zone": "both",
    "utc_offset": 0,
    "rr": 2.0,                       # Krypto bekommt 4.0 ueber datafeed.rr_for
    "sweep_lookback": 48,
    "min_sweep_penetration_atr": 0.15,
    "target_mode": "rr",
}

# Genau ein Kandidat. Mehrere parallel waren richtig, solange offen war,
# welcher traegt - jetzt ist es das nicht mehr. Die Form bleibt dieselbe wie
# in forward.CANDIDATES, damit paper_bot.py nichts weiter aendern muss.
LIVE = [
    ("smc_baseline_h1", TIMEFRAME,
     dict(BASIS, pool="asia_range", sweep_window=None),
     "Asien-Spanne, Stich zu jeder Uhrzeit, Strukturbruch, FVG. Die frühere "
     "Kontrollgruppe - die einzige der Familie, die auf ungesehenen Daten "
     "nicht negativ war. Gemessen: -0,03R auf 223 Trades. Also null."),
]
