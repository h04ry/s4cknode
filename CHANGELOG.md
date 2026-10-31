# Neuerungen

## Radio, Verwaltung und Anleitung

- Internetradio im Discord-Sprachkanal mit Senderwahl und Lautstärke von 0 bis 100.
- `!radio` erklärt alle Radiobefehle mit vollständigen Eingaben und Beispielen.
- `!radiolist`, `!radiojoin`, `!radiosender`, `!radiolautstärke`, `!radiolautstaerke` und `!radiostop`.
- `!radiotitel` liest aktuelle Titelinformationen aus dem bestehenden Stream, sofern der Sender sie liefert.
- Automatisches Verlassen leerer Sprachkanäle nach zwei Minuten; zurückkehrende Zuhörer brechen den Timer ab.
- Temporärer Radio-Status mit Sender und Titel; danach Rückkehr zum normalen Status.
- Radio-Webseite mit Kanalwahl, Senderverwaltung, Wiedergabesteuerung und Lautstärkeregler.
- Private Einstellungen in SQLite; Tokens und Passwörter in `.env`.
- Module lassen sich über den Webeditor ohne vollständigen Bot-Neustart laden und ändern.
- GitHub-Repository-Modus mit Commit-Beschreibungen im Discord-Kanal und dauerhaft gespeichertem Meldefortschritt.
- Vollständige Anleitung für Installation, alle Befehle, optionale Module, Rechte und Fehlerbehebung.

Hinweise: Die Weboberfläche besitzt noch keine Anmeldung. Radio überträgt Audio, kein Video. Titelinformationen hängen vom Sender ab. Für automatische Updates aus einem privaten GitHub-Repository benötigt der Bot einen lokalen Lesetoken.
# Radio-Bedienfeld (31.10.2026)

- Persistentes Discord-Bedienfeld mit Senderauswahl, Beitreten, Stoppen, Lautstärkeschritten und genauer Eingabe.
- Gemeinsamer Zustand mit Web und Textbefehlen; Titel und Status werden bei Änderungen aktualisiert.
- Pro Server gespeicherte Panel-Zuordnung, bis zu 100 Sender mit Seiten und Wiederverwendung über `!radiopanel`.
- Voice-Kanalprüfung schützt die laufende Wiedergabe vor Änderungen durch Außenstehende.
- Erfolgreiche Radio-Klicks aktualisieren nur das Bedienfeld; private Bestätigungen sammeln sich nicht mehr darunter. Fehlermeldungen bleiben sichtbar.


## Mehrserver-Betrieb (31.10.2026)
- Servergetrennte SQLite-Einstellungen und geprüfte Migration der ursprünglichen Installation.
- Eigene Senderlisten, Meldekanäle, Twitch-Accounts und Zustellfortschritte sowie getrennte Statistikkanäle.
- Serverauswahl in Web-Einstellungen und Radioverwaltung; fremde Kanal-IDs werden abgewiesen.
- `!server`, `!server setup`, `!server info`, `!server set` und `!server invite` für Serververwalter.
- Wiederholbares Statistik-/Bot-Setup, gespeicherter Twitch-Zustand, konfigurierbare Pings und Freigabeliste für GitHub-Repositorys.
- Gemeinsame Prozessverwaltung nur durch Betreiber; globale Radio-Presence ohne serverfremde Titel.

## Regeln und Themenrollen (31.10.2026)
- Dauerhafter Regelbestätigungs-Button mit automatischer Mitgliedsrolle und gespeicherter Zustimmung.
- Fünf freiwillige Themenrollen für passende Kanalbereiche; manuelle Team-/Kollegenrollen bleiben geschützt.
- Persönliche Sichtbarkeitssperren verhindern eine Freischaltung durch vorab manuell vergebene Rollen.
- Begrüßung neuer menschlicher Mitglieder, erneute Bestätigung nach Wiederbeitritt und Erhalt fremder Kanalrechte beim Aufräumen.
- Vollständige Themenstruktur einmalig für den neuen Server eingerichtet; bestehender Server unverändert.

## Alte Gameserver-Anbindung entfernt (31.10.2026)
- Die bisherigen ARK-/Icarus-Cogs und AMP-Anbindung entfernt, einschließlich alter Befehle, Konfigurationsfelder und nicht mehr benötigter Umgebungsvariablen.
- Bestehende Radio-, Community-, Twitch-, GitHub- und Statistikfunktionen bleiben erhalten.
- Eine neue, unabhängige Gameserver-Statusfunktion mit Konfiguration im Webinterface ist als zukünftiges Projekt vorgemerkt.
