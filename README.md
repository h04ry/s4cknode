# S4CKNode Discord Bot

Ein modularer Discord-Bot für Internetradio, Twitch-Meldungen, GitHub-Neuerungen und Serverstatistiken. Die Weboberfläche verwaltet Sender, Einstellungen und Python-Module. Private IDs und Einstellungen liegen in SQLite, Zugangsdaten in einer lokalen `.env`.

Geplante Erweiterungen: [ROADMAP.md](ROADMAP.md). Hinweise zum geschützten Betrieb: [SECURITY.md](SECURITY.md).

## Inhalt

- [Mehrere Discord-Server](#mehrere-discord-server)

- [Schnellstart für Mitglieder](#schnellstart-für-mitglieder)
- [Alle aktiven Befehle](#alle-aktiven-befehle)
- [Internetradio im Detail](#internetradio-im-detail)
- [Twitch-Benachrichtigungen](#twitch-benachrichtigungen)
- [GitHub-Neuerungen im Discord-Kanal](#github-neuerungen-im-discord-kanal)
- [Serverstatistiken](#serverstatistiken)
- [Bot-Status](#bot-status)
- [Weboberfläche](#weboberfläche)
- [Installation und Einrichtung](#installation-und-einrichtung)
- [Dauerbetrieb mit systemd](#dauerbetrieb-mit-systemd)
- [Optionale Module](#optionale-module)
- [Einstellungen und Datenhaltung](#einstellungen-und-datenhaltung)
- [Wartung und Fehlerbehebung](#wartung-und-fehlerbehebung)

## Mehrere Discord-Server

Dieselbe Bot-Anwendung kann mehreren Discord-Servern beitreten. Der Betreiber lädt den Bot mit den OAuth2-Scopes `bot` und `applications.commands` ein. Jeder Server hat eigene Zielkanäle, Twitch-Accounts, GitHub-Quelle und Zustellfortschritte, Statistikkanäle, Radiosender, Lautstärke, Senderwahl und Radio-Bedienfeld.

Serververwalter verwenden:

| Eingabe | Wirkung nur auf dem aktuellen Server |
|---|---|
| `!server` | Einrichtungshilfe |
| `!server setup` | Fehlende Bot-Kanäle, Radio-Bedienfeld und vier Statistikkanäle anlegen; vorhandene Objekte wiederverwenden |
| `!server info` | Eigene Meldungseinstellungen anzeigen |
| `!server invite` | Einladungslink für weitere Server |
| `!server set bot.status_channel_id #bot-status` | Startmeldungen in diesen Textkanal |
| `!server set twitch.channel_id #twitch` | Ziel für Twitch-Meldungen |
| `!server set twitch.mention_everyone false` | Twitch-Pings ausschalten (`true` zum Einschalten) |
| `!server set github.channel_id #github` | GitHub-Zielkanal |
| `!server set github.repo_filter owner/repo` | Freigegebenes Repository überwachen |
| `!server set github.user account` | Öffentliche Account-Ereignisse (wenn Repository-Filter leer) |
| `!server set github.repo_filter aus` | Repository-Filter leeren |
| `!server set twitch.channel_id aus` | Twitch-Zustellung auf diesem Server deaktivieren |

Die Serverbefehle benötigen „Server verwalten“. Kanal-Erwähnungen oder genaue Kanal-IDs werden akzeptiert; fremde Serverkanäle und globale Einstellungen werden abgewiesen. `!server setup` richtet Funktionsbereiche ein und ersetzt keine vollständige persönliche Rollen-/Kanalvorlage. Es löscht keine vorhandenen Kanäle oder Rollen. Neue Meldungskanäle sind für Mitglieder schreibgeschützt; Kategorien und Kanalrechte können anschließend angepasst werden.

Neue Server übernehmen keine privaten Listen oder Zielkanäle anderer Server. Sender starten mit neutralen Vorgaben, Twitch/GitHub benötigen eine eigene Einrichtung. Im Web unter **Einstellungen** zuerst den Discord-Server auswählen; unter **Radio** gilt auch die Senderverwaltung für den ausgewählten Server.

Globale Funktionen bleiben bewusst beim Betreiber: `.env`-Zugangsdaten, Code-/Modulverwaltung, Dienst-Neustarts, Infrastrukturzugang und der normale Discord-Bot-Status. Ein Neustart betrifft immer alle Server und ist per `!restart` nur für den Bot-Owner freigegeben. Das bestehende Webinterface ist eine private Betreiberoberfläche ohne Serveradmin-Anmeldung; es darf nicht an fremde Serveradmins freigegeben werden.

Der Bot-Betreiber muss Repositorys für den gemeinsamen GitHub-Lesetoken zuerst in den globalen Einstellungen unter `github.allowed_repos` freigeben (Liste von `owner/repo`). Ein Serveradmin erhält dadurch keinen beliebigen Zugriff auf andere mit dem Token lesbare Repositorys. Öffentliches Account-Monitoring verwendet keine Token-Autorisierung.

Beim Update einer bestehenden Installation werden die alten servergebundenen SQLite-Einstellungen einmalig dem anhand eines bisherigen Melde-/Statistikkanals ermittelten Server zugeordnet. Vorher eine konsistente SQLite-Sicherung erstellen. Die Migration überschreibt keine vorhandenen Guild-Einstellungen und ordnet keine alten Daten neuen Servern zu. GitHub-Fortschritt und bisherige Radio-Zuordnungen bleiben erhalten.

## Regeln und Themenrollen

Auf einem vom Betreiber entsprechend eingerichteten Server übernimmt das Modul `community` die Regelbestätigung und Themenauswahl. Das Erstellen einer vollständigen Rollen-/Kanalstruktur erfolgt einmalig durch den Betreiber; `!server setup` allein installiert diese persönliche Vorlage nicht.

1. Neue menschliche Mitglieder sehen zunächst nur Willkommen und Regeln.
2. Im Regelkanal auf **Regeln gelesen und akzeptiert** klicken. Der Bot speichert die Bestätigung und vergibt **Mitglied**.
3. Im Rollenkanal freiwillig **Tech & IT**, **Internet & Netzwerke**, **IT-Security**, **Coding** und/oder **Gaming** auswählen. Sichtbar werden die passenden Themenbereiche. Jede Auswahl ersetzt die bisherigen Themenrollen; die allgemeinen Bereiche bleiben auch ohne Themenrolle verfügbar.
4. **Arbeitskollegen** und **Moderator** werden ausschließlich von der Administration manuell vergeben. Die Kollegenrolle erschließt nach Regelbestätigung einen privaten Kollegenbereich. Moderatoren erhalten keinen automatischen Zugriff auf diesen Bereich; Administratoren und der Serverinhaber können aufgrund ihrer Discord-Rechte alle Bereiche sehen.

Die Regeln gelten auch bei vorzeitig manuell vergebenen Themen-/Kollegenrollen: Bis zur Bestätigung setzt der Bot eine persönliche Sichtbarkeitssperre auf die geschützten Kategorien bzw. unsynchronisierten Kanäle. Nach Bestätigung entfernt er seine temporären Sperren und erhält andere individuelle Rechte. Native Discord-Mitgliedschaftsprüfungen müssen gegebenenfalls zuerst abgeschlossen werden. Bots werden nicht zur Bestätigung aufgefordert.

Regel- und Themen-Buttons sind dauerhaft registriert und funktionieren nach Modulneuladen oder Neustart weiter. Eine bestätigte Mitgliedschaft bleibt bei Reload erhalten; nach Verlassen und erneutem Beitritt müssen die Regeln wieder bestätigt werden. Alte oder serverfremde Bedienfelder und privilegierte Rollen sind von der Selbstvergabe ausgeschlossen. Temporäre Sperren werden bei Austritt aufgeräumt.

Rollenzuordnungen, Kanal-/Nachrichten-IDs und Versionsstand liegen pro Server in `community_config`, Bestätigungen in `community_acceptance`, verwaltete temporäre Rechte in `community_gate_blocks`. Nicht eingerichtete Server werden von diesem Modul nicht verändert. Der Bot benötigt zum Vergeben der Rollen „Rollen verwalten“ und eine höhere Rolle; für die individuelle Kanalsperre passende Rechte zur Kanalberechtigungsverwaltung. Die Bot-Presence und andere Funktionen bleiben davon unabhängig.

## Schnellstart für Mitglieder

Normale Befehle werden als Nachricht in einen Discord-Textkanal geschrieben und beginnen mit `!`. Nur `/ping` ist ein Slash-Befehl. Die Radiobefehle benötigen keinen Slash.

```text
!radio
!radiolist
!radiojoin
!radiosender Radio Paradise
!radiolautstärke 30
!radiotitel
!radiostop
```

Vor `!radiojoin` einem normalen Sprachkanal beitreten. Sendernamen aus `!radiolist` übernehmen. Ein Sendername darf Leerzeichen enthalten; Anführungszeichen sind nicht erforderlich. Platzhalter wie `<Sendername>` ersetzen, die spitzen Klammern nicht mitschreiben.

## Alle aktiven Befehle

### Allgemein und Radio

| Vollständige Eingabe | Funktion | Voraussetzung |
|---|---|---|
| `/ping` | Antwortet mit der Bot-Latenz in Millisekunden | Bot und Slash-Befehle im Server verfügbar |
| `!radio` | Vollständige Radio-Hilfe mit Beispielen | Textkanal in einem Discord-Server |
| `!radiopanel` | Erstellt ein dauerhaftes Radio-Bedienfeld im aktuellen Textkanal oder verlinkt das vorhandene | Berechtigung „Server verwalten“; normaler Textkanal |
| `!radiolist` | Listet alle eingerichteten Sender auf | Textkanal in einem Discord-Server |
| `!radiojoin` | Bot kommt in deinen Sprachkanal und startet den zuletzt gewählten Sender | Du bist im Sprachkanal; Bot darf verbinden und sprechen |
| `!radiosender <Sendername>` | Wechselt zum angegebenen Sender | Du bist im Sprachkanal des Bots; Radio ist verbunden |
| `!radiolautstärke <0–100>` | Ändert die Lautstärke | Du bist im Sprachkanal des Bots |
| `!radiolautstaerke <0–100>` | Derselbe Lautstärkebefehl ohne Umlaut | Wie oben |
| `!radiotitel` | Zeigt Sender und aktuellen Musiktitel, sofern verfügbar | Textkanal in einem Discord-Server |
| `!radiostop` | Stoppt Radio und verlässt den Sprachkanal | Du bist im Sprachkanal des Bots |

### Twitch

| Vollständige Eingabe | Funktion |
|---|---|
| `!twitch` | Zeigt die verfügbaren Twitch-Unterbefehle |
| `!twitch list` | Listet überwachte Twitch-Accounts auf |
| `!twitch add <Loginname>` | Nimmt einen Account in die Überwachung auf |
| `!twitch del <Loginname>` | Entfernt einen Account |

Beispiel: `!twitch add beispiel_streamer`. Es wird der Twitch-Login eingegeben, keine komplette URL. Listenänderungen mit add/del benötigen „Server verwalten“; list ist für Mitglieder verfügbar. Alle Listen gelten nur im aufrufenden Server.

### Statistiken und Verwaltung

| Vollständige Eingabe | Funktion | Berechtigung |
|---|---|---|
| `!stats` | Statistik-Hilfe | Discord-Administrator |
| `!stats setup` | Erstellt Kategorie und vier Statistik-Sprachkanäle; speichert IDs | Discord-Administrator |
| `!stats update` | Aktualisiert alle Zähler sofort | Discord-Administrator |
| `!stats info` | Zeigt die konfigurierten Statistik-Kanal-IDs | Discord-Administrator |
| `!status <Typ> <Text>` | Setzt und speichert den normalen Bot-Status | Bot-Owner |
| `!load <Modulname>` | Lädt eine vorhandene `.py`-Erweiterung | Bot-Owner |
| `!unload <Modulname>` | Entlädt eine Erweiterung | Bot-Owner |
| `!restart` | Beendet den Bot; ein eingerichteter Dienst startet ihn erneut | Bot-Owner, nur im Statuskanal des aufrufenden Servers |

Bot-Owner ist der von Discord für die Anwendung ermittelte Eigentümer beziehungsweise ein entsprechendes Teammitglied. Die Rolle „Administrator“ allein ersetzt diese Prüfung bei Owner-Befehlen nicht.

Beispiele:

```text
!status watching deinen Stream
!status playing gemeinsam mit euch
!load general
!unload general
```

Modulnamen ohne `cogs.` und ohne Dateiendung eingeben. Ein globaler `!help`- oder `!hilfe`-Befehl ist derzeit nicht eingerichtet; `!radio` erklärt die Radiobedienung.

## Internetradio im Detail

### Radio per Klick im Discord

Ein Serververwalter schreibt einmal `!radiopanel` in den gewünschten Textkanal. Der Bot erstellt dort eine feste Nachricht mit Senderauswahl und Buttons. Wiederholtes Einrichten verwendet das bestehende Bedienfeld desselben Servers; nach dem Löschen der Nachricht lässt sie sich mit dem Befehl neu erstellen.

- **Sender auswählen:** Wechselt den laufenden Sender. Ist der Bot nicht verbunden, wird die Auswahl für den nächsten Beitritt gespeichert. Bei mehr als 25 Sendern erscheinen Buttons zum Blättern.
- **In meinen Voicekanal kommen:** Verbindet den Bot mit deinem normalen Sprachkanal und startet den gewählten Sender. Solange in einem anderen Kanal noch Menschen zuhören, wird der Bot nicht von dort weggezogen.
- **−10 % / +10 %:** Ändert die Lautstärke in Schritten von zehn Prozentpunkten, begrenzt auf 0 bis 100.
- **Wert eingeben:** Öffnet ein Eingabefenster für eine genaue ganzzahlige Lautstärke von 0 bis 100.
- **Stoppen & verlassen:** Beendet die Wiedergabe und die Voice-Verbindung.

Zum Bedienen musst du in einem normalen Sprachkanal sein. Wenn der Bot verbunden ist, kannst du Sender, Lautstärke und Stopp nur aus seinem Sprachkanal steuern. Erfolgreiche Klicks hinterlassen keine zusätzliche Nachricht; der neue Zustand erscheint direkt im Bedienfeld. Fehlermeldungen sind nur für die klickende Person sichtbar. Senderseiten können alle Personen mit Kanalzugriff durchblättern; die angezeigte Seite ist gemeinsam.

Das Bedienfeld zeigt Sender, Titel (falls vom Stream geliefert), Voicekanal, Lautstärke und Wiedergabestatus. Es nutzt dieselbe Radio-Steuerung wie Webinterface und Textbefehle. Externe Änderungen werden spätestens bei der nächsten Prüfung nach etwa zehn Sekunden sichtbar; nur geänderte Anzeigen werden an Discord geschickt. Bestehende Befehle bleiben verfügbar.

Kanal, Nachricht und Senderseite werden pro Server in SQLite gespeichert. Die Buttons werden nach Bot-Neustarts oder Neuladen von `radio_panel` erneut registriert. Eine Wiedergabe startet dadurch nicht automatisch. Der Bot benötigt im Textkanal **Kanal anzeigen**, **Nachrichten senden**, **Links einbetten** und **Nachrichtenverlauf anzeigen**. Das Modul `radio_panel` ergänzt `radio` und `radio_help` und kann unabhängig davon neu geladen werden.

### Beitreten, Sender wählen und stoppen

`!radiojoin` verbindet den Bot mit dem Sprachkanal der aufrufenden Person. Ist er bereits in einem anderen Kanal desselben Servers, wird er verschoben. Danach startet der zuletzt gespeicherte Sender. Ohne vorherige Auswahl dient der erste Sender der Liste als Vorgabe. Stage-Kanäle werden nicht unterstützt.

`!radiosender Radio Paradise` wechselt die laufende Wiedergabe. Der Sender muss zuvor in der Liste angelegt sein. Lautstärke, Senderwechsel und Stoppen sind über Discord nur für Personen im Sprachkanal des Bots möglich. Die Weboberfläche kann unabhängig davon steuern.

Die Lautstärke reicht von 0 bis 100, anfangs 30. `0` ist stumm und beendet die Wiedergabe nicht. Senderwahl und Lautstärke werden für jeden Discord-Server separat gespeichert. Auch die Senderliste wird pro Server getrennt gespeichert; Änderungen beeinflussen andere Server nicht.

`!radiostop` beendet Wiedergabe und Voice-Verbindung. Nach einem Bot-Neustart oder einem Neuladen des Radiomoduls tritt der Bot keinem Kanal automatisch bei. Erneut `!radiojoin` verwenden.

### Titelanzeige

`!radiotitel` liest den laufenden Titel aus ICY-Metadaten der bestehenden Audioverbindung. Je nach Sender steht dort „Interpret – Titel“ oder eine andere vom Sender gelieferte Beschreibung. Es ist kein zweiter Metadatenstream erforderlich.

Sendet der Anbieter keine Titelinformationen oder sind diese noch nicht eingetroffen, weist der Bot darauf hin. Ist kein Radio aktiv, nennt er den Startbefehl. Aus einer beliebigen Stream-Adresse kann der Bot keine zuverlässigen Musiktitel erraten.

### Leere Sprachkanäle

Ohne menschliche Zuhörer verlässt der Bot den Sprachkanal nach zwei Minuten. Andere Bots zählen nicht als Zuhörer. Kommt vorher eine Person zurück, wird der Timer abgebrochen. Wenn es anschließend wieder leer wird, beginnt eine neue volle Wartezeit. Ein Kanalwechsel setzt den Timer ebenfalls zurück.

Die Prüfung erfolgt bei Voice-Kanalwechseln und zusätzlich alle zehn Sekunden. Der Austritt kann dadurch einige Sekunden nach Ablauf der zwei Minuten erfolgen.

### Sender im Web verwalten

Im Bot Manager auf **Radio** klicken oder `/radio` öffnen:

1. Discord-Server und geeigneten Sprachkanal auswählen.
2. Sender auswählen und **Verbinden & Radio starten** anklicken.
3. Mit **Sender abspielen** wechseln und über den Regler die Lautstärke einstellen.
4. **Stoppen & verlassen** beendet die Verbindung.

Unter **Radiosender verwalten** können Name und direkte HTTP-/HTTPS-Audiostream-Adresse hinzugefügt oder vorhandene Einträge entfernt werden. Namen müssen eindeutig sein und dürfen höchstens 80 Zeichen enthalten. Bis zu 100 Sender sind möglich. Website-Adressen und Playlist-Dateien sind keine direkten Audiostreams; URLs mit eingebetteten Zugangsdaten werden abgewiesen.

Die Auswahl blendet Statistikkanäle, den AFK-Kanal und Kanäle ohne passende Bot-Rechte aus. Das Entfernen eines Listeneintrags beendet einen bereits laufenden Stream nicht sofort. Bei einem Stream-Ausfall den Sender erneut starten; der Streamzugriff versucht zuvor begrenzt, die Verbindung wiederherzustellen.

Radio Paradise und SomaFM Groove Salad sind neutrale Vorgaben einer neuen Installation; Verfügbarkeit und Inhalte liegen beim jeweiligen Anbieter. Das Modul überträgt Audio und stellt keinen Video- oder „Go Live“-Stream bereit.

## Twitch-Benachrichtigungen

In `.env` `TWITCH_CLIENT_ID` und `TWITCH_CLIENT_SECRET` aus einer Twitch-Anwendung hinterlegen. Im Web unter **Einstellungen → gewünschten Server → Twitch** den Discord-Benachrichtigungskanal und die überwachten Loginnamen festlegen. Alternativ die oben aufgeführten `!twitch`-Befehle verwenden.

Der Bot prüft alle zwei Minuten. Wird ein Kanal live erkannt, sendet er Titel, Kategorie, Zuschauerzahl, Vorschaubild und einen Twitch-Link. Bei einem Kategoriewechsel wird das vorhandene Embed aktualisiert. Beim Wechsel auf offline folgt eine Abschlussmeldung.

Live-Meldungen erwähnen `@everyone` nur bei aktivierter Server-Einstellung `twitch.mention_everyone` und passenden Discord-Rechten. Neue Server starten ohne Ping. Die Abschlussdauer basiert auf dem von Twitch gelieferten Streamstart. Zuschauerzahl und Titel werden bei einem Kategoriewechsel aktualisiert.

Streamer-Liste, Onlinestatus und Nachrichten-IDs bleiben pro Server und Zielkanal in SQLite erhalten. Ein Reload übernimmt den bisherigen Zustand. Ein Absturz direkt zwischen Discord-Versand und Speicherung kann weiterhin eine doppelte Meldung verursachen.

## GitHub-Neuerungen im Discord-Kanal

In **Einstellungen → gewünschten Server → GitHub** den Zielkanal einstellen. Für Bot-Updates bei **Repository-Filter** das vom Betreiber freigegebene Repository im Format `owner/repository` eintragen.

### Repository-Modus

Mit ausgefülltem Repository-Filter prüft der Bot alle zwei Minuten die Commits des Standardbranches. Jede neue Änderung wird mit Commit-Titel, Beschreibung und Link zur vollständigen Anleitung im Discord-Kanal gepostet. Damit die Meldungen verständlich sind, sollen Commit-Beschreibungen die sichtbaren Neuerungen in normalen Worten zusammenfassen.

Der zuletzt erfolgreich gemeldete Commit wird in SQLite gespeichert. Ein Neustart erzeugt dadurch keine Wiederholung der bereits bestätigten Meldungen. Scheitert die Discord-Zustellung, wird der Fortschritt nicht vorgezogen; die Meldung kann später erneut versucht werden. Bei einer ganz neuen Einrichtung wird zunächst der aktuelle Stand gemerkt und keine alte Historie in den Kanal kopiert. Nach einem Force-Push oder sehr großem Rückstand wird nur der neueste Stand gemeldet. Ein Absturz genau zwischen erfolgreichem Senden und Speichern kann trotzdem eine Wiederholung verursachen.

Ein privates Repository benötigt einen **Fine-grained Personal Access Token** mit Zugriff ausschließlich auf das gewünschte Repository und **Contents: Read-only**. Token in der lokalen `.env` als `GITHUB_TOKEN=...` hinterlegen. Der Monitor liest den Wert bei der nächsten Abfrage ein. Ein öffentliches Repository kann ohne Token gelesen werden, unterliegt dann aber niedrigeren API-Limits.

Tokens werden bei GitHub unter **Settings → Developer settings → Personal access tokens → Fine-grained tokens** erstellt. „Only select repositories“ auswählen, das gewünschte Repository freigeben, Contents auf Read-only setzen und ein Ablaufdatum wählen. Der Token gehört weder in Discord-Nachrichten noch in Git.

### Account-Modus

Bleibt der Repository-Filter leer, liest der Bot öffentliche Ereignisse des eingestellten GitHub-Accounts. Unterstützt sind Releases, Issues, Issue-/PR-Kommentare, Pull Requests und Push-Ereignisse, soweit GitHub Commit-Daten mitliefert. Für zuverlässige Neuerungsmeldungen zu diesem Bot den Repository-Modus verwenden. Private Account-Ereignisse sind kein Ersatz für den expliziten Repository-Zugriff.

## Serverstatistiken

`!stats setup` erstellt eine Kategorie mit vier nicht betretbaren Voice-Zählern: alle Mitglieder, Menschen, Bots und Server-Boosts. Die vier IDs werden sofort in SQLite gespeichert. Wiederholtes Setup verwendet vorhandene Kanäle erneut und ergänzt nur fehlende. Ein unvollständiger Lauf kann fortgesetzt werden.

Die Zähler werden alle zehn Minuten aktualisiert. `!stats update` erzwingt die nächste Aktualisierung; `!stats info` zeigt die Zuordnungen. Der Bot benötigt Kanalverwaltung. Für die Unterscheidung von Bots und Menschen muss der Mitgliederzugriff funktionieren.

Jeder Server besitzt eine eigene Statistik-Konfiguration. `!stats update` aktualisiert nur den aufrufenden Server; der Hintergrundtask verarbeitet alle Server getrennt und überspringt nicht eingerichtete Zähler.

## Bot-Status

```text
!status playing ein Spiel
!status watching deinen Stream
!status listening Musik
!status streaming mein Programm
```

Die normalen Statuswerte werden gespeichert und bei einem erneuten Start geladen. Während Radio spielt, zeigt der Bot stattdessen vorübergehend einen benutzerdefinierten Text wie **📻 Streamt Sendername – Interpret – Titel**. Titelwechsel werden innerhalb des nächsten Zehn-Sekunden-Intervalls übernommen. Ohne Titel wird nur der Sender angezeigt.

Nach Radioende, Verbindungsabbruch oder dem Verlassen des Kanals kehrt der normale Status zurück. Radio überschreibt die gespeicherten Einstellungen nicht. Ein während der Wiedergabe geänderter normaler Status wird nach Radioende verwendet. Sobald der Bot mehreren Servern angehört, zeigt der globale Radio-Status nur die Anzahl der Server mit Wiedergabe; private Sender-/Titelinformationen stehen im jeweiligen Radio-Bedienfeld. Discord stellt nur eine gemeinsame Bot-Presence bereit.

Der Radio-Text ist keine Videoübertragung und kein offizielles Twitch-/YouTube-Streaming-Badge. Der normale Typ `streaming` allein konfiguriert ebenfalls keinen Videostream.

## Weboberfläche

Die Weboberfläche läuft standardmäßig auf Port 5000. Sie bietet:

- Online-/Dienststatus und die letzten 150 Bot-Protokollzeilen.
- Modulübersicht mit Dateistatus und tatsächlich geladenem Zustand.
- Python-Editor für Module und `main.py`.
- Erstellen, Speichern, Aktivieren, Deaktivieren und Löschen von Modulen.
- Zentrale Einstellungen für Kanäle, Rollen, Benutzer und externe Dienste.
- Radio-Steuerung und Senderverwaltung.
- Einen Bot-Neustartknopf bei passender Dienst-/sudo-Konfiguration.

### Module direkt übernehmen

**Speichern** lädt ein aktiviertes Modul neu. Ein deaktiviertes Modul wird nur gespeichert. **Aktivieren** lädt das Modul sofort und benennt `.py.off` in `.py` um; **Deaktivieren** entlädt es und führt die umgekehrte Umbenennung aus. **Löschen** entlädt das Modul vor dem Entfernen seiner Datei. Neue Module erhalten zunächst eine minimale Vorlage ohne eigenen Beispielbefehl.

Vor dem Speichern wird die Python-Syntax geprüft. Vor Speichern und Löschen entstehen private Sicherungen unter `.runtime/backups/`. Schlägt das Neuladen fehl, wird die vorherige Datei wiederhergestellt; discord.py stellt die vorige Erweiterung wieder her. Externe Nebenwirkungen selbst geschriebenen Codes lassen sich dadurch nicht allgemein zurücknehmen.

Globale Slash-Befehlsänderungen werden mit Discord synchronisiert; Fehler erscheinen als Warnung. Die Registrierungsanzeige in Discord kann sich verzögert aktualisieren. Während der Änderung bleibt der Bot-Prozess aktiv, der flüchtige Zustand des betreffenden Moduls geht aber verloren. Das Neuladen des Radios beendet zum Beispiel die Voice-Verbindung.

Direkte Änderungen in VS Code werden nicht automatisch überwacht. Anschließend im Webeditor speichern oder das Modul als Owner entladen und erneut laden. Bei `.py.off` muss vor `!load` eine passende `.py`-Datei hergestellt werden. Die Web-Schalter erledigen dies automatisch.

Änderungen an `main.py`, `runtime_control.py`, `config_store.py`, Bibliotheken und dem Bot-Dienst benötigen weiterhin einen Bot-Neustart. Änderungen an `webui/app.py` benötigen einen Neustart des Web-Dienstes. Bei einer Zeitüberschreitung vor einer Wiederholung den tatsächlichen Modulstatus prüfen.

### Zugriff auf die Weboberfläche

**Die Weboberfläche hat derzeit keine Anmeldung.** Jeder mit Netzwerkzugriff darauf kann Code und Einstellungen ändern und damit Aktionen unter dem Bot-Dienstbenutzer ausführen. Sie darf nicht ungeschützt ins Internet veröffentlicht werden. Ein öffentliches Quellcode-Repository veröffentlicht nicht automatisch die laufende Weboberfläche.

Zugriff etwa auf ein vertrauenswürdiges LAN oder VPN begrenzen. Für Zugriff über einen SSH-Tunnel den Port zusätzlich per Firewall schützen oder Flask an localhost binden. Der private Steuer-Socket unter `.runtime/control.sock` schützt nur die lokale Verbindung zwischen Webprozess und Bot; er ersetzt keine Web-Anmeldung.

## Installation und Einrichtung

### 1. Voraussetzungen

- Linux für den lokalen Unix-Steuer-Socket, beispielsweise Debian 13.
- Python 3.11 oder neuer; die bestehende Installation verwendet Python 3.13.
- Git, FFmpeg und `libopus` für Radio.
- Discord-Anwendung mit Bot-Token.
- Internetzugriff auf Discord, Streamanbieter sowie bei Nutzung Twitch und GitHub.

Für Bot und Remote-Editor zusammen sind 2 GiB RAM eine vernünftige Ausgangsbasis. Der tatsächliche Bedarf hängt von Servergröße, Modulen und gleichzeitigen Radiowiedergaben ab.

### 2. Dateien und Python-Umgebung

```bash
sudo apt update
sudo apt install git python3 python3-venv ffmpeg libopus0
git clone https://github.com/h04ry/s4cknode.git
cd s4cknode
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
```

Bei einem privaten Repository ist für das Klonen eine eigene GitHub-Berechtigung notwendig. Eine öffentliche Anleitung allein erteilt keinen Zugriff auf ein privates Repository.

`requirements.txt` enthält die benötigten Basispakete einschließlich Voice-Unterstützung. `requirements-radio.txt` enthält nur die zusätzlichen Radioanforderungen und ersetzt die vollständige Paketliste nicht. Das optionale KI-Modul benötigt zusätzlich `google-genai`.

`main.py` unterstützt außerdem eine installationsbezogene Paketablage unter `.runtime/radio-deps`. Diese Ablage ist privat und nicht Bestandteil des Repositories. Bei einer neuen Installation werden die Pakete regulär in `.venv` installiert. Ein vorhandenes System-FFmpeg wird bevorzugt; sonst nutzt Radio den Decoder aus `imageio-ffmpeg`. Die bestehende Installation kann ihre private Opus-Ablage verwenden, neue Installationen sollen `libopus0` installieren.

### 3. Discord-Anwendung vorbereiten

Im Discord Developer Portal eine Anwendung und einen Bot anlegen beziehungsweise den vorhandenen Bot verwenden. Den Token nur in `.env` unter `DISCORD_TOKEN` speichern.

Der aktuelle Einstieg fordert alle Discord-Intents an. Die benötigten privilegierten Intents im Developer Portal aktivieren, insbesondere **Message Content**, **Server Members** und die angeforderten Presence-Intents. Ohne Message Content können die `!`-Befehle im Server ausbleiben.

Den Bot mit den OAuth2-Scopes `bot` und `applications.commands` in den eigenen Server einladen. Nur die für die aktivierten Funktionen benötigten Rechte vergeben:

| Funktion | Wichtige Discord-Rechte |
|---|---|
| Normale Befehle, Twitch/GitHub, Hilfe | Kanäle ansehen, Nachrichten senden, Links einbetten |
| Radio | Verbinden und Sprechen im gewünschten Sprachkanal |
| Statistik-Setup und Zähler | Kanäle verwalten |
| Wiederfinden/Bearbeiten bestehender Meldungen | Nachrichtenverlauf lesen |
| Optionale Chat-Löschung | Nachrichten verwalten |
| Optionale Medienanfragen | Kanäle verwalten, Nachrichten verwalten |
| Twitch-Massenbenachrichtigung | `@everyone` nur vergeben, wenn gewünscht |

### 4. Zugangsdaten hinterlegen

```dotenv
DISCORD_TOKEN=
TWITCH_CLIENT_ID=
TWITCH_CLIENT_SECRET=
GITHUB_TOKEN=
GEMINI_API_KEY=
```

Nur `DISCORD_TOKEN` ist für den Grundbetrieb notwendig. Die übrigen Werte werden für die entsprechenden Dienste beziehungsweise optionalen Module benötigt. Kanal-, Rollen- und Benutzer-IDs gehören in SQLite, nicht in `.env` oder Python-Dateien. Falls `BOT_CONFIG_DB` gesetzt wird, müssen Bot und Weboberfläche denselben Datenbankpfad verwenden.

### 5. Erster Start

Im Projektverzeichnis ausführen:

```bash
.venv/bin/python main.py
```

In einem zweiten Terminal aus demselben Projekt:

```bash
.venv/bin/python webui/app.py
```

Die Oberfläche unter `http://<server-ip>:5000` öffnen und unter **Einstellungen** die gewünschten Kanäle und Dienste einrichten. Im Discord-Entwicklermodus lassen sich Kanal-, Rollen- und Benutzer-IDs per Rechtsklick kopieren. IDs vollständig als Text einfügen; keine Beispielzahlen übernehmen.

Zuerst Statuskanal, Twitch-/GitHub-Zielkanäle und den gewünschten normalen Bot-Status setzen. Danach gegebenenfalls `!stats setup` ausführen und Radio testen. Der Bot benötigt keine manuell vorbereitete Datenbank: Tabellen und neutrale Standardwerte werden automatisch angelegt.

### 6. Verhalten bei fehlenden Einstellungen

Nicht konfigurierte Benachrichtigungskanäle oder leere Accountlisten lösen keine persönlichen Ersatzwerte aus. Twitch benötigt passende API-Zugangsdaten. GitHub kann bei privaten Repositories ohne Token nicht lesen. Optionale Module erst nach vollständiger Einrichtung aktivieren. Eine erfolgreiche Dienstanzeige ersetzt nicht die Prüfung, ob ein einzelner externer Dienst erreichbar ist.

## Dauerbetrieb mit systemd

Beide Dienste müssen unter demselben Benutzer und mit derselben Konfiguration laufen. Das folgende Beispiel verwendet `botuser` und `/opt/s4cknode/bot`; Benutzer, Pfade und Installation entsprechend vorbereiten und anpassen. Der Dienstbenutzer muss Projektdateien, SQLite und `.runtime` schreiben dürfen.

`/etc/systemd/system/discordbot.service`:

```ini
[Unit]
Description=S4CKNode Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=botuser
WorkingDirectory=/opt/s4cknode/bot
ExecStart=/opt/s4cknode/bot/.venv/bin/python /opt/s4cknode/bot/main.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/botweb.service`:

```ini
[Unit]
Description=S4CKNode Weboberflaeche
After=network-online.target discordbot.service

[Service]
Type=simple
User=botuser
WorkingDirectory=/opt/s4cknode/bot/webui
ExecStart=/opt/s4cknode/bot/.venv/bin/python /opt/s4cknode/bot/webui/app.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now discordbot botweb
systemctl status discordbot botweb
journalctl -u discordbot -n 100 --no-pager
journalctl -u botweb -n 100 --no-pager
```

Für den Neustartknopf benötigt der Web-Dienstbenutzer eine eng begrenzte sudo-Regel. Den tatsächlichen Pfad mit `command -v systemctl` prüfen. Eine Beispielregel, mit `visudo` eingerichtet und an den Benutzer angepasst:

```sudoers
botuser ALL=(root) NOPASSWD: /usr/bin/systemctl restart discordbot
```

Keine pauschalen passwortlosen Administratorrechte für die Weboberfläche vergeben. `!restart` setzt voraus, dass ein Dienst oder Startskript den beendeten Bot wieder startet. Nicht zusätzlich manuell eine zweite Bot-Instanz starten, wenn `discordbot` bereits läuft.

## Optionale Module

Dateien mit `.py.off` sind deaktiviert. Nach Einrichtung können sie im Web aktiviert werden. Folgende Erweiterungen sind vorhanden:

| Modul | Befehle | Einrichtung und Grenzen |
|---|---|---|
| `ai` | `!ask <Frage>` und direkte Bot-Erwähnung | `google-genai` und `GEMINI_API_KEY`; Fragen werden an Google gesendet; aktuelle Implementierung hat keinen dauerhaften Gesprächsverlauf |
| `remote_docker` | `!miner start`, `!miner stop`, `!miner restart`, `!miner status` | SQLite: SSH-Ziel, Benutzer, Schlüsselpfad auf dem Bot-Server, erlaubte Discord-Benutzer, Steuerkanal und Twitch-Containername |
| `clear_chat` | `!nuke` | Festgelegter Zielkanal und erlaubte Benutzer; Bestätigungsbuttons; betrachtet bis zu 1000 Nachrichten und löscht passende aus den letzten 24 Stunden |
| `media_requests` | `!request <Film- oder Serientitel>`, `!close` | Anfragekanal und Kategorie; erstellt einen eigenen Anfragekanal mit Zugriff für Anfragenden, Bot und Administratoren |

`!miner` prüft Benutzerliste und Steuerkanal. Weitere im Docker-Modul hinterlegte Containernamen besitzen derzeit keine eigenen Steuerbefehle. Der SSH-Schlüssel liegt auf dem Bot-Server und gehört nicht in das Repository. Der Remote-SSH-Zugriff läuft aktuell synchron und kann den Bot bei langsamen Gegenstellen kurz blockieren.

Bei Medienanfragen prüft `!close` aktuell die Anfragekategorie, keine gesonderte Eigentümerrolle, und löscht den dortigen Kanal nach einer kurzen Wartezeit.

Optionale Infrastrukturzugriffe und Löschbefehle führen echte Änderungen an Servern oder Discord-Inhalten aus. Einstellungen und Kanalrechte vor dem Aktivieren prüfen. Die `.off`-Dateien dokumentieren vorhandene Funktionen, ihre externen Dienste werden bei einer normalen Bot-Installation nicht automatisch eingerichtet.

## Einstellungen und Datenhaltung

| Speicherort | Zweck |
|---|---|
| `.env` | Lokale Tokens und Passwörter |
| `.env.example` | Leere Vorlage, die in Git enthalten sein darf |
| `data/settings.sqlite3` | Installationskonfiguration, Twitch-Liste, Status, Radiostand und GitHub-Fortschritt |
| `.runtime/control.sock` | Private lokale Modulsteuerung |
| `.runtime/backups/` | Sicherungen vor Webeditor-Änderungen |
| `cogs/*.py` | Beim Start geladene Module |
| `cogs/*.py.off` | Deaktivierte Module |

SQLite benötigt keinen zusätzlichen Datenbankserver. Der neue Datenbankordner wird privat angelegt; Datenbank und `.env` sollen nur für den Dienstbenutzer lesbar sein. Die Datenbank ist nicht verschlüsselt. Private Dateien, Sicherungen, Caches und virtuelle Umgebungen müssen von Git ausgeschlossen bleiben.

Die Einstellungsgruppen heißen `bot`, `github`, `twitch`, `stats`, `presence`, `docker`, `clear_chat`, `requests`, `ark`, `icarus` und `radio`. Kanal-IDs können leer bleiben, wenn eine Funktion nicht verwendet wird. Benutzerlisten enthalten vollständige Discord-Benutzer-IDs, keine Namen. Die Weboberfläche überträgt IDs als Text, damit große Zahlen nicht gerundet werden.

Alternativ zur Weboberfläche, lokal im Projektverzeichnis:

```bash
.venv/bin/python config_store.py --guild DEINE_SERVER_ID list
.venv/bin/python config_store.py --guild DEINE_SERVER_ID set github.repo_filter 'owner/repository'
.venv/bin/python config_store.py set presence.type 'watching'
.venv/bin/python config_store.py set presence.text 'deinen Stream'
```

`list` gibt private Einstellungen aus; diese Ausgabe nicht ungeprüft teilen. Die meisten Module lesen Einstellungen bei der nächsten Verwendung. Der normale Status wird bei direkter CLI-Änderung erst bei einem passenden Status-Refresh beziehungsweise mit `!status` aktualisiert; die Weboberfläche stößt dies selbst an. Für Tokens anderer Dienste ist gegebenenfalls Modulneuladen oder ein Neustart nötig. Der GitHub-Monitor liest einen neu in `.env` eingetragenen Lesetoken bei der nächsten Abfrage.

`migrate_config.py` dient bestehenden alten Installationen: Es importiert frühere Python-Literale, Kanalvariablen aus `.env` sowie die alten Status-/Twitch-JSON-Dateien. Der Import muss vor dem Ersetzen der alten Quellen erfolgen; vorher sichern. Bereits gesetzte SQLite-Werte werden beim erneuten Import nicht überschrieben. Neue Installationen benötigen diesen Schritt nicht.

## Wartung und Fehlerbehebung

### Sicherungen und Updates

Code, `.env` und Datenbank getrennt sichern. Bei laufendem SQLite die Backup-Funktion verwenden oder beide Dienste vor dem Kopieren stoppen; SQLite kann zusätzliche WAL-Dateien verwenden. Alte Sicherungen unter `.runtime/` können ebenfalls Zugangsdaten enthalten und dürfen nicht veröffentlicht werden.

Vor einem Codeupdate `git status` und `git diff` prüfen, eigene Änderungen sichern und danach Abhängigkeiten beziehungsweise Dienste passend aktualisieren. Keine fremden Änderungen ungeprüft über die laufende Installation kopieren. Ein öffentliches Git-Repository ist keine Sicherung der privaten Konfiguration.

### Typische Probleme

| Problem | Prüfen |
|---|---|
| `!`-Befehle reagieren nicht | Message Content Intent im Developer Portal, Textkanalrechte, geladenes Modul und exakte Schreibweise |
| `/ping` fehlt | Einladung mit `applications.commands`, Bot-Startprotokoll und Discord-Synchronisierung |
| Radio verbindet nicht | Normaler Voice-Kanal, Bot-Rechte Verbinden/Sprechen, Voice-Abhängigkeiten und Netzwerk/UDP |
| Radio verbindet, bleibt aber stumm | Lautstärke, Server-Stummschaltung, direkte Stream-URL, FFmpeg und libopus |
| `!radiotitel` zeigt nichts | Sender liefert keine ICY-Metadaten oder Metadaten sind noch nicht angekommen |
| Bot verlässt den Kanal | Zwei Minuten ohne menschliche Zuhörer; andere Bots halten ihn nicht im Kanal |
| Normaler Status ist unsichtbar | Während Radio läuft, hat die Radioanzeige Vorrang |
| Twitch meldet nichts | Kanal-ID, Streamerliste, Twitch-App-Zugangsdaten, Kanalrechte und Dienstprotokoll |
| GitHub meldet nichts | Repository-Filter, Tokenrechte bei privatem Repo, abgelaufener Token, API-/Kanalrechte; neue Einrichtung meldet erst künftige Änderungen |
| Webeditor kann nicht übernehmen | Bot ist noch nicht bereit, Socket fehlt, Syntax-/Ladefehler oder unterschiedliche Dienstbenutzer |
| Neustartknopf schlägt fehl | Dienstname `discordbot` und eng begrenzte sudo-Berechtigung |
| Ressourcen steigen stark | Bot plus Remote-Editor/Analyseprozesse gemeinsam betrachten; Voice benötigt zusätzliche Audioverarbeitung |

Die Weboberfläche zeigt Dienststatus und Logs. Unter systemd helfen zusätzlich die oben aufgeführten `journalctl`-Befehle. Ein gespeichertes Modul ist nur dann aktiv, wenn es erfolgreich geladen wurde; der Dateiname allein beweist keine erfolgreiche Initialisierung.

## Tests
In der vorbereiteten Python-Umgebung:
```bash
python -m unittest discover -s tests -v
```
Die enthaltenen Tests verwenden temporäre SQLite-Datenbanken und simulierte Discord-Interaktionen. Sie benötigen keinen echten Bot-Token und verändern keinen Discord-Server.
