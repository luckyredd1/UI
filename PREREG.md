# Vorab angemeldete Regeln

Was hier steht, wurde **vor** der Messung festgelegt und wird nicht
nachträglich geändert, weil das Ergebnis besser oder schlechter aussieht.
Genau das nachträgliche Anpassen hat die 89 Backtest-Hypothesen wertlos
gemacht: bei genug Varianten sieht immer eine gut aus.

---

## 02.09.2026 — Kostengrenze 0,10R

**Regel:** Kein Trade, bei dem der geschätzte Spread mehr als 10% des
Risikos frisst. Umgesetzt als `MAX_SPREAD_COST_R = 0.10` in `paper_bot.py`,
geprüft vor der Positionsgrößenberechnung. Übersprungene Signale werden als
`SKIP_COST` protokolliert, damit der Verzicht nachvollziehbar bleibt.

**Begründung — Arithmetik, nicht Rendite.**
Bei einem Ziel von 2R liegt der Nullpunkt bei einer Trefferquote von

    p = (1 + Kosten) / 3

| Kosten | nötige Trefferquote | Handicap |
|---|---|---|
| 0,00R | 33,3% | — |
| 0,10R | 36,7% | +3,3pp |
| 0,18R | 39,3% | +6,0pp |
| 0,76R | 58,6% | +25,2pp |

**Befund vor der Änderung** (30 Trades, Stand 02.09.2026):

- Spreadkosten im Schnitt **0,179R** pro Trade → nötig 39,3%
- 24 von 30 Trades (80%) mit Stop unter 0,5% → Kosten 0,212R → nötig 40,4%
- deren Gegenwert im Schnitt **9,18× das Konto** bei 1% Risiko
- schlechtester Einzelfall GBPAUD, Stop 0,04% (~4 Pips): Kosten **0,757R**,
  nötig 58,6%
- die 6 Trades ab 0,5% Stop: Kosten nur 0,045R → nötig 34,8%
- gemessene Trefferquote 44,4% bei ±9pp Unsicherheit

**Warum die Grenze unabhängig vom Ausgang richtig ist.**
Hat die Strategie keinen Vorteil, verliert jeder Trade genau seine Kosten —
dann ist Kostensenken das Einzige, was wirkt. Hat sie einen kleinen Vorteil,
sind die teuren Trades genau die, die ihn in einen Verlust drehen. Schaden
kann die Regel nur, wenn ausgerechnet die teuren Trades die besseren wären;
dafür gibt es weder einen Mechanismus noch einen Hinweis in den Daten.

**Bekannter Preis:** Von 30 vergangenen Trades hätten 10 stattgefunden.
Die Datensammlung dauert damit etwa dreimal so lange. Das wurde vorher
akzeptiert und ist kein Grund, die Grenze später zu lockern.

**Was die Regel widerlegen würde:** Wenn über mindestens 100 Trades die
übersprungenen (`SKIP_COST`) im Nachhinein systematisch besser gelaufen
wären als die gehandelten. Bis dahin gilt sie.

---

## Bereits geltende Regeln

| Regel | Wert | Grund |
|---|---|---|
| Risiko pro Trade | 1,0% | vom Nutzer festgelegt |
| Positionen je Korrelationsgruppe | 1 | drei Krypto-Positionen sind eine Wette, nicht drei |
| Hebelgrenzen | ESMA-Vorgaben für Privatkunden | was ein echter Broker erlauben würde |
| Sperre nach manuellem Schließen | 12 Stunden, nur dieses Symbol | manuelles Schließen ist eine Entscheidung, keine Marktlage |
| Verkleinern statt Ablehnen | bis 10% der Wunschgröße | Position soll möglich bleiben, nur kleiner |

## Kontrollgruppe

`sess_nowindow` läuft mit, ohne Zeitfenster. Schlagen die getimten
Varianten sie nicht, ist die Killzone-Idee wertlos. Diese Kontrolle wird
nicht entfernt, auch nicht wenn sie gewinnt.

---

## 02.09.2026 (nachmittags) — Kosten neu gemessen, Krypto-Ziel auf 4R

**Anlass.** Die Spreads wurden mit `measure_spreads.py` real gemessen
(Dukascopy-Ticks, Binance-Orderbuch). Ergebnis: die gemessenen Rohspreads
lagen deutlich UNTER den Schätzungen — aber die Messung erfasste nur den
quotierten Spread, nicht Kommission und Börsengebühr. Bei Binance kostet
Spot 0,1% je Seite, also 0,2% hin und zurück; das ist das Vierfache des
größten gemessenen Krypto-Spreads. Die Kosten wurden daraufhin auf
realistische Retail-Gesamtkosten gesetzt, mit den Rohspreads als
dokumentierter Untergrenze.

**Regeländerung 1 — Grenze als Nachteil statt fester R-Zahl.**

    Nullpunkt:        p = (1 + c) / (m + 1)
    fairer Münzwurf:  p = 1 / (m + 1)
    Nachteil:         c / (m + 1)

Begrenzt wird jetzt der Nachteil auf **3,33 Prozentpunkte**
(`MAX_COST_HANDICAP_PP`). Bei einem 2R-Ziel ist das exakt die am Vormittag
angemeldete Grenze von 0,10R — die ursprüngliche Anmeldung bleibt also
gültig und wird nicht gelockert, nur korrekt auf andere Ziele übertragen.

**Regeländerung 2 — Krypto handelt mit 4R statt 2R.**
Weil der Nachteil `c/(m+1)` beträgt, kostet derselbe Spread bei 4R nur
drei Fünftel dessen, was er bei 2R kostet. Für teure Instrumente ist ein
größeres Ziel damit mechanisch begründet, nicht geraten.

**Was das kostet:** Bei 4R muss die Trefferquote über 20% liegen statt über
33%. Für einen Zufallslauf sind beide gleich unerreichbar; die Regel schafft
keinen Vorteil, sie verringert nur den Kostennachteil.

**Widerlegungsbedingung für Krypto:** Erzeugt Krypto über mindestens
100 Signale nicht genug handelbare Trades — nötiger Stop 0,60% (BTC) bis
1,50% (Alt-Coins) —, oder liegt die Trefferquote klar unter 20%, fliegt
Krypto aus dem Universum. Das wurde vorher festgelegt.

---

## 02.09.2026 (abends) — Quarterly Theory, vorab angemeldet

**Was geprüft wird.** Quarterly Theory nach Traderdaye/ICT. Der Tag zerfällt
in vier Sechs-Stunden-Quartale in **New Yorker Zeit** (mit Sommerzeit):

    Q1  18:00-00:00   Accumulation   baut die Spanne
    Q2  00:00-06:00   Manipulation   Raid durch die Q1-Spanne
    Q3  06:00-12:00   Distribution   Einstieg hier
    Q4  12:00-18:00   Continuation

Regel: Q1-Spanne bilden, in **Q2** Raid durch eine Seite mit Rückschluss
hinein, dann in **Q3** Einstieg über eine offene Fair Value Gap in
Gegenrichtung. Stop hinter dem Raid-Extrem plus 0,15 ATR, Ziel 2R.

**Parameter — vorher festgelegt, wird nicht nachjustiert:**

| Parameter | Wert |
|---|---|
| `min_raid_atr` | 0,15 |
| `min_fvg_atr` | 0,10 |
| `stop_buffer_atr` | 0,15 |
| `min_stop_atr` / `max_stop_atr` | 0,3 / 6,0 |
| `rr` | 2,0 (Krypto 4,0 wie überall) |

**Kontrollgruppe `qt_any`.** Identischer Aufbau, aber Einstieg in jedem
Quartal statt nur Q3. Schlägt `qt_q3` diese Kontrolle nicht, trägt das
Quartalsfenster nichts bei — dieselbe Logik wie bei `sess_nowindow`.

**Nulltest bestanden** (vor dem ersten echten Lauf): auf Zufallsläufen
ohne Drift und ohne Kosten ergab `qt_q3` −0,0220R bei z = −0,30 über
468 Trades, `qt_any` −0,0435R bei z = −0,82 über 874. Die Umsetzung
erfindet also keine Rendite.

**Erwartung, ehrlich notiert.** QT ist strukturell nah an
`sess_london_asia`, das am selben Tag mit −0,60R widerlegt wurde. Die
echten Unterschiede sind: New Yorker Zeit statt fester UTC-Stunden,
Einstieg zwingend in Q3, und die volle Q1-Spanne statt eines Swing-Punkts.
Die Aussicht ist entsprechend gedämpft. Notiert, damit ein positives
Ergebnis später nicht als „hatten wir doch erwartet" gelesen wird.

**Widerlegungsbedingung:** Liegt `qt_q3` über mindestens 100 Trades mit
zwei Standardfehlern komplett unter null, oder schlägt es die Kontrolle
`qt_any` nicht, ist QT erledigt.

---

## 02.09.2026 (spät) — QT kombiniert mit SMC

**Ergebnis von QT allein, vorweg.** `qt_q3` lieferte −0,2031R über 87 Trades
und lag damit **unter** seiner Kontrolle `qt_any` (−0,1123R über 134). Die
angemeldete Widerlegungsbedingung — „schlägt es die Kontrolle nicht" — ist
erfüllt. Der Unterschied ist mit z = −0,48 nicht signifikant; das Fenster
schadet also nicht nachweisbar, es trägt nur nichts bei.

**Was jetzt geprüft wird.** Meine QT-Umsetzung ließ einen Schritt weg, den
die Session-Strategien verlangen:

    sess_london_asia:  Sweep -> MSS -> FVG -> Einstieg
    qt_q3:             Raid  ->  —  -> FVG -> Einstieg

`qt_mss` fügt den Strukturbruch ein: nach dem Raid muss der Kurs ein
Swing-Extrem von vor dem Raid durchschließen, bevor ein Einstieg erlaubt
ist. Die Lücke muss zwischen Raid und Strukturbruch entstanden sein.
Kontrollgruppe `qt_mss_any` ohne Quartalsbedingung.

**Nulltest bestanden:** auf Zufallsläufen ergab `qt_mss` −0,0004R (z = 0,00)
über 200 Trades, die Kontrolle −0,0008R (z = −0,01) über 316.

**Die Hürde — und sie ist hoch.** Dies ist Hypothese 92. Bei so vielen
Tests liegt die ehrliche Schwelle nach Bonferroni bei **|z| > 3,27** statt
den üblichen 1,96. Bei rund 100 Trades und einem Standardfehler um 0,15
hieße das: **R/Trade über +0,49**, nicht knapp positiv. Alles darunter ist
mit der Anzahl bisheriger Versuche vereinbar und beweist nichts.

Diese Schwelle wird vorher festgelegt und nicht nachträglich gesenkt.

**Letzte Variante dieser Familie.** Danach ist der Ansatz
Liquiditäts-Raid → Struktur → FVG auf M15 ausgeschöpft, unabhängig vom
Ergebnis.

---

## 02.09.2026 (Nacht) — Vollständige Kombinationssuche, mit Trennung

**Anlass.** Die Frage war: alle Bausteine aus ICT, SMC und QT in jeder
möglichen Kombination testen.

**Warum das naiv wertlos wäre.** Bei 108 Kombinationen und *völlig
zufälligen* Ergebnissen zeigt der beste Kandidat im Mittel etwa +0,37R
allein durch die Auswahl. Ein realistischer echter Vorteil läge bei +0,10R.
Die Suche produziert also garantiert einen Sieger, der besser aussieht als
alles, was real sein könnte. Genau so sind die ersten 89 Hypothesen
entstanden.

**Wie es stattdessen läuft.** Die Daten werden **zeitlich** geteilt:

    [====== Suche 65% ======][=== Prüfung 35% ===]

- Gesucht wird nur im vorderen Teil.
- Der hintere Teil wird während der Suche **nicht angefasst**.
- Am Ende wird **genau ein** Kandidat — der beste aus der Suche — **einmal**
  auf dem hinteren Teil geprüft.
- **Dieses eine Ergebnis ist die Antwort.** Kein zweiter Versuch, keine
  Anpassung, kein „aber der Zweitplatzierte".

Weil auf ungesehenen Daten nur ein einziger Test stattfindet, gilt dort die
normale Schwelle (zwei Standardfehler), nicht die Bonferroni-Hürde. Das ist
der ganze Sinn der Trennung: die Suche darf beliebig groß sein, solange die
Prüfung einmalig ist.

**Suchraum, 108 Kombinationen:**

| Baustein | Varianten |
|---|---|
| Liquiditäts-Pool | Q1-Spanne, Asien-Spanne, London-Spanne, H1-Swing, H4-Swing |
| Zeitfenster | keins, Q3, London-Killzone, NY-AM-Killzone |
| Strukturbruch | mit / ohne (bei Session und MTF fest eingebaut) |
| Einstiegszone | FVG, iFVG, beides |
| Ziel | 2R, 3R, 4R |

Unsinnige Paarungen sind ausgeschlossen: Quartale nur bei QT, Killzones nur
bei der Session-Familie.

Mindestens 25 Trades je Kandidat in der Suche, sonst wird er verworfen.
Kostengrenze wie überall.

**Was das Ergebnis bedeutet:**

- Prüfteil klar positiv → erster echter Befund. Dann Vorwärtstest, nicht
  sofort glauben.
- Prüfteil klar negativ → der Suchgewinner trägt nicht.
- Prüfteil um null → der Gewinner war das, wonach er aussieht: der
  glückliche Beste aus 108 Versuchen.

Der Unterschied zwischen Such- und Prüfergebnis ist dabei die
interessanteste Zahl. Fällt er groß aus, ist das ein direktes Maß dafür,
wie viel die Suche an Selbsttäuschung erzeugt hat.

---

## 02.09.2026 (Nacht, 2) — Paarweise Kreuzungen der Frameworks

**Anlass.** Nicht das grosse Raster, sondern gezielte Zweierkombinationen:
ICT mit QT, ICT mit Sessions, SMC mit QT und so weiter.

**Was das Raster nicht abgedeckt hatte.** In `combo_search.py` waren
Quartale nur für die QT-Familie und Killzones nur für die Session-Familie
erlaubt. Die eigentliche Kreuzung — QT-Pool mit ICT-Zeitfenster — war damit
ausgeschlossen. Dafür wurde `raid_window` in `strategy_qt.py` ergänzt: der
Raid darf jetzt in Q2 (QT-Lehrbuch) oder in einer ICT-Killzone liegen.
Nulltest bestanden: Q2 z=+0,06, London-KZ z=+0,41, NY-AM-KZ z=+1,15.

**Die sieben Paarungen — vorher festgelegt, keine wird nachträglich
ergänzt oder entfernt:**

| Paarung | Inhalt |
|---|---|
| SMC allein | Asien-Spanne, Raid jederzeit, Strukturbruch (Grundlinie) |
| ICT-Session + SMC (London) | Asien-Spanne, Raid in London-Killzone |
| ICT-Session + SMC (NY) | London-Spanne, Raid in NY-AM-Killzone |
| QT + SMC | Q1-Spanne, Raid in Q2, Einstieg in Q3 |
| QT + ICT (London) | Q1-Spanne, Raid in London-Killzone |
| QT + ICT (NY) | Q1-Spanne, Raid in NY-AM-Killzone |
| ICT-MTF + SMC | H4-Swing, Strukturbruch |

**Verfahren.** Dieselbe Zeitteilung wie zuvor: 65% Suche, 35% Prüfung. Jede
Paarung wird auf beiden Teilen gerechnet, aber **nur die Zahl aus dem
Prüfteil zählt**. Der Suchteil steht daneben, um den Abstand sichtbar zu
machen.

**Schwelle.** Sieben Paarungen auf ungesehenen Daten sind sieben Tests,
also gilt eine Korrektur: **|z| > 2,45** statt 1,96. Wer aus sieben
Versuchen den besten nimmt, findet auch in reinem Rauschen einen guten.
Diese Schwelle wird nicht gesenkt.

**Was vorab bekannt ist und die Erwartung dämpft:** Vier von vier
Kontrollvergleichen haben gezeigt, dass Zeitfenster nichts beitragen; der
Suchsieger aus 108 Kombinationen brach von +0,21R auf −0,64R ein; und die
Verteilung über 59 Kandidaten war mit p=0,0019 signifikant nach unten
verschoben. Ein positives Ergebnis wäre eine Überraschung.

---

## 02.09.2026 — Nachprüfung der zwei positiven QT-Paarungen

**Vor dem Lauf angemeldet, damit das Ergebnis hinterher nicht zurechtgelegt
werden kann.**

Im Zwei-Jahres-Lauf auf H1 standen im Prüfteil zwei Paarungen positiv:

| Paarung | Trades | R/Trade | z |
|---|---|---|---|
| QT + SMC | 45 | +0,3524 | 1,36 |
| QT + ICT (London) | 37 | +0,4946 | 1,68 |

Keine erreicht die Schwelle 2,45. Bei sieben Versuchen liegt das erwartete
Maximum von |z| in reinem Rauschen bei etwa 1,8 — 1,68 ist damit genau der
Normalfall ohne jeden Vorteil. Der M15-Lauf ist **keine** unabhängige
Bestätigung: sein Prüfzeitraum (02.07.2026–02.09.2026) liegt vollständig
innerhalb des H1-Prüfzeitraums (28.12.2025–02.09.2026).

### Was geprüft wird

1. **Scheinlagen.** Die gesamte Quartalseinteilung wird um 6, 12 und 18
   Stunden verschoben (`qt_shift_h`). Mechanik und Handelszahl bleiben
   vergleichbar, nur die Uhrzeiten sind falsch.
2. **Bootstrap** statt Standardfehler, weil die R-Verteilung mit +2R/+4R
   gegen −1R stark rechtsschief ist.
3. **Herkunft** je Symbol und Gruppe.

### Vorher festgelegte Auslegung

- **Erreicht mindestens eine Scheinlage den Wert der echten Lage**, ist
  Quarterly Theory als Zeitstruktur widerlegt. Sie wird dann nicht weiter
  verfolgt, unabhängig davon, wie gut die absolute Zahl aussieht.
- **Ist die echte Lage die beste von vieren**, beweist das nichts — bei vier
  Versuchen ist einer zwangsläufig der beste, mit Wahrscheinlichkeit 1/4 der
  echte. Es wäre lediglich die Erlaubnis, weiterzusuchen.
- **Liegt der Bootstrap-Bereich nicht komplett über null**, gilt weiterhin
  „kein Nachweis".
- **Kommen über 60% des Gesamt-R aus zwei Symbolen**, ist das Ergebnis eine
  Eigenschaft dieser Symbole und keine der Strategie.

### Erwartung (damit sie hinterher nicht angepasst wird)

Mindestens eine Scheinlage erreicht die echte Lage, und der Bootstrap-Bereich
schließt null ein. Begründung: 37 Trades bei einer Streuung um 1,8R lassen
keine andere Auflösung zu, und alle bisherigen Zeitfenster-Tests haben gegen
ihre eigenen Kontrollen verloren.

### Was auch ein günstiger Ausgang nicht wäre

Kein Grund, Geld einzusetzen. Der nächste Schritt wäre ein Vorwärtstest auf
Papier über Monate — Daten, die es heute noch nicht gibt.

---

## 02.09.2026 — Ergebnis der QT-Nachprüfung und die Anmeldung des nächsten Schritts

### Was der Scheinlagen-Test ergeben hat

**QT + SMC:** die Kontrolle hat funktioniert — alle vier Lagen haben
brauchbare Handelszahlen (45 / 38 / 13 / 57).

| Lage | Trades | R/Trade |
|---|---|---|
| ECHT (0h) | 45 | +0,3523 |
| Schein +6h | 38 | +0,0187 |
| Schein +12h | 13 | −0,1017 |
| Schein +18h | 57 | +0,0421 |

Scheinlagen im Mittel −0,014R, echte Lage +0,352R. Die echte Lage ist die
beste von vieren. Das widerlegt QT nicht — bestätigt es aber auch nicht
(1/4 Zufallswahrscheinlichkeit, und die Paarung war schon vorher als beste
von sieben ausgewählt).

**QT + ICT (London): die Kontrolle war WERTLOS.** Die verschobenen Quartale
erzeugten 3, 0 und 0 Trades. Grund: wird das Quartalsraster verschoben, liegt
die London-Killzone nicht mehr zwischen Q1-Ende und Q3 — die Scheinlagen
konnten gar nicht antreten. Das ist ein Konstruktionsfehler des Tests, kein
Ergebnis. Diese Zeile wird nicht als Beleg gewertet.

**Beide Bootstrap-Bereiche schließen null ein** (−0,143 bis +0,865 bzw.
−0,060 bis +1,066). Nach der vorher festgelegten Auslegung gilt: kein
Nachweis.

**Herkunft:** bei QT + SMC liefern zwei Symbole mit je einem einzigen Trade
(AVAXUSD +3,97R, LTCUSD +3,91R) die Hälfte des Gesamt-R. Ohne diese zwei
Kerzen bleiben +0,186R statt +0,352R.

### Der nächste Test — vorher angemeldet

`crosses_test.py`: dieselben zwei Regeln, unverändert, auf **19
Währungskreuzen ohne USD**, die in diesem Projekt nie getestet wurden. Für
sie ist die gesamte Historie ungesehen, nicht nur die hinteren 35 %.

Kontrollgruppen: für QT + SMC wieder die verschobenen Quartale; für
QT + ICT (London) diesmal die **verschobene Killzone** (04–07, 10–13, 13–16
UTC) bei echtem Quartalsraster — damit die Kontrolle überhaupt Trades
erzeugt.

Die Spreads der Kreuze sind **absichtlich zu hoch** angesetzt (2- bis 4-fache
der Majors, ungemessen). Ein zu hoher Spread kann ein echtes Ergebnis
zerstören, aber kein schlechtes schönrechnen.

### Vorher festgelegte Auslegung

- Schwelle |z| > 2,24 (zwei Regeln, Bonferroni).
- **Bleibt QT + SMC unter der Schwelle oder wird negativ**, ist die Sache
  entschieden: das positive Ergebnis auf den sieben USD-Paaren war eine
  Eigenschaft dieser Paare. Kein weiterer Versuch mit dieser Regelfamilie.
- **Erreicht mindestens eine Scheinlage die echte Lage**, gilt dasselbe.
- **Hängt über 60 % des Gesamt-R an drei Symbolen**, oder halbiert sich der
  Wert nach Streichen der zwei größten Gewinner, zählt es nicht.
- **Nur wenn alle vier Bedingungen gehalten werden**, geht es weiter — und
  zwar mit einem Vorwärtstest auf Papier über Monate, nicht mit Geld.

### Erwartung

Kein Nachweis. Begründung: der Wert +0,3523R hängt zur Hälfte an zwei
einzelnen Krypto-Kerzen, und die verbleibenden +0,186R liegen dort, wo alle
bisherigen Kandidaten gelandet sind — nahe null.

---

## 02.09.2026 — Ergebnis: die Regelfamilie ist beendet

`crosses_test.py`, 19 nie getestete Währungskreuze, ganze Historie
(07.12.2023–02.09.2026) ungesehen:

| Regel | Trades | Treffer | R/Trade | z |
|---|---|---|---|---|
| QT + SMC | 86 | 26,7 % | **−0,2311** | −1,60 |
| QT + ICT (London) | 61 | 27,9 % | **−0,1990** | −1,14 |

**Beide vorher festgelegten Abbruchbedingungen sind eingetreten:**

1. Beide Regeln liegen unter der Schwelle — und zwar auf der **negativen**
   Seite, nicht nur unentschieden.
2. Bei beiden erreichen **2 von 3 Scheinlagen** die echte Lage oder sind
   besser. Die Quartalsstruktur trägt nichts bei.

Dazu: das Streichen der größten Gewinner macht beide Werte *schlechter*
(−0,231 → −0,284 bzw. −0,199 → −0,273). Das Ergebnis hängt an keinem
Ausreißer, es ist durchgehend negativ.

Die Stichprobe ist größer als die, die vorher positiv aussah: 86 und 61
Trades gegen 45 und 37.

### Zusammengefasst mit dem vorherigen Lauf

45 Trades zu +0,3523R (7 USD-Paare) plus 86 Trades zu −0,2311R (19 Kreuze)
ergeben **131 Trades zu −0,031R**, z ≈ −0,24. Also null.

### Was damit erklärt ist

Die +0,3523R auf den sieben USD-Paaren waren zweifache Auswahl: die beste
von sieben Paarungen, und die Hälfte des Werts kam aus zwei einzelnen
Krypto-Kerzen (AVAXUSD und LTCUSD, je ein Trade, je knapp +4R). Der
Scheinlagen-Test hatte das nicht auffangen können, weil er nur prüft, ob die
Uhrzeit stimmt — nicht, ob die Zahl selbst trägt.

### Entscheidung

**Die Familie ICT / SMC / Quarterly Theory wird nicht weiter verfolgt.**
Keine weitere Variante, kein weiterer Parameter, keine weitere Kreuzung.
Das war vorher so angemeldet und wird eingehalten.
