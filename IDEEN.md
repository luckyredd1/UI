# Zurückgestellte Ideen

Was hier steht, wurde geprüft und bewusst **später** eingeplant — nicht
verworfen. Mit Begründung, damit wir es beim Wiederaufgreifen nicht neu
diskutieren müssen.

---

## Orochi Framework — zurückgestellt am 02.09.2026

**Was es ist.** Ein kostenpflichtiges Framework von „44emirr" / Orochi
Trading, verbreitet über TikTok. Bausteine laut Autor: Auction Market
Theory, TPO / Market Profile, Volume Profile, VWAP, „Rhythm", Orderflow,
Elliott Wave.

**Was daran seriös ist.** Auction Market Theory und Market Profile stammen
von Steidlmayer aus der CBOT-Zeit, VWAP und Orderflow sind institutioneller
Standard. Das sind keine erfundenen Konzepte.

**Warum jetzt nicht.**

1. **Datenlage.** Volume Profile braucht Volumen je Preisniveau, Orderflow
   braucht Ticks mit Aggressorseite. Wir haben OHLC-Kerzen von Yahoo und
   Binance. Für NQ — das dort bevorzugte Instrument — bräuchte es
   CME-Daten, kostenpflichtig.
2. **Elliott Wave ist nicht falsifizierbar.** Wellenzählung ist Auslegung;
   damit entzieht sich der Ansatz der Prüfmaschinerie, die wir aufgebaut
   haben. Was nicht widerlegbar ist, ist auch nicht bestätigbar.
3. **Die Werbeaussage stimmt nicht.** „Strategies have Alpha decay. The
   Orochi framework does not." Es gibt keine Methode ohne Alpha-Zerfall.
   Bei einem Bezahlprodukt ist das ein Warnzeichen, kein Argument.

**Woran es scheitern oder gelingen würde.** Sinnvoll prüfbar erst mit
echten Orderflow- und Volumendaten, und nur der systematische Teil
(AMT/Profile/VWAP) ohne den diskretionären Wellenanteil. Wenn wir
irgendwann CME- oder Börsendaten mit Volumen je Preis haben, lohnt ein
Blick auf **Volume Profile plus VWAP allein** — das ist codierbar.

Quellen: [Beschreibung](https://www.tiktok.com/@44emirr/video/7674334720536120590),
[Alpha-Decay-Aussage](https://www.tiktok.com/@44emirr/video/7672579706729876749?lang=ar)

---

## Höherer Zeitrahmen — zurückgestellt am 02.09.2026

Kosten in R = Spread ÷ Stop-Abstand. Der Stop-Abstand wächst ungefähr mit
der Wurzel der Zeit, also bringt der Wechsel von M15 auf H4 (16-fache Zeit)
etwa den vierfachen Stop und damit ein Viertel der Kosten in R.

Löst das Bruttoproblem nicht (M15 brutto −0,12R), würde einem kleinen
Vorteil aber überhaupt erst die Chance geben, die Kosten zu überleben.
Mechanisch begründet, deshalb vorgemerkt.
