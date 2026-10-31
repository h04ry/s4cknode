# Sicherheits- und Betriebshinweise

Zugangsdaten, private Discord-IDs und lokale Betriebsdaten gehören nicht in das Repository. Tokens bleiben in `.env`, Einstellungen in der privaten SQLite-Datenbank. `.env.example` enthält ausschließlich leere Vorlagen. Private Sicherungen, Schlüssel und Exporte dürfen nicht hochgeladen werden.

## Bestehende Betreiberoberfläche
Die aktuelle Weboberfläche ist ein internes Werkzeug des Bot-Betreibers. Sie enthält noch keine Benutzeranmeldung und erlaubt Änderungen an Modulen, Quellcode und Einstellungen. Sie ist deshalb nicht für direkten Zugriff aus dem Internet oder die Freigabe an unberechtigte Servermitglieder geeignet. Netzwerkzugriff konsequent auf vertrauenswürdige Betreiber begrenzen. Anmeldung, serverbezogene Autorisierung und ein öffentlich erreichbares Dashboard sind geplante Erweiterungen, keine bereits implementierte Schutzfunktion.

Der Bot und seine Weboberfläche sollten unter einem eigenen unprivilegierten Betriebssystembenutzer laufen. Eine eventuelle sudo-Freigabe auf den benötigten Dienst-Neustart beschränken. Spiel-/Infrastrukturzugriffe und optionale Löschfunktionen erst nach Prüfung ihrer Rechte aktivieren.

## Meldung eines Problems
Keine aktiven Tokens, Passwörter, privaten Schlüssel oder personenbezogenen Konfigurationen in öffentliche Issues oder Pull Requests schreiben. Zugangsdaten nach versehentlicher Offenlegung beim jeweiligen Dienst widerrufen/wechseln; das Löschen einer Datei oder ein Force-Push ersetzt dies nicht.

Eine Quelltextprüfung ist keine vollständige Sicherheitszertifizierung. Vor einem produktiven oder öffentlich erreichbaren Betrieb die eigene Umgebung und alle aktivierten Funktionen prüfen.
