"""Private installation settings. Defaults in this file contain no personal values."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar

CURRENT_GUILD = ContextVar("settings_guild", default=None)

@contextmanager
def guild_context(guild_id):
    token = CURRENT_GUILD.set(guild_id)
    try:
        yield
    finally:
        CURRENT_GUILD.reset(token)
from urllib.parse import urlparse
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')

# key: (type, default, label)
SPECS = {
    'github.allowed_repos': ('repos', [], 'GitHub: durch Betreiber freigegebene Repositorys'),
    'twitch.mention_everyone': ('bool', False, 'Twitch: @everyone erlauben'),
    'radio.stations': ('stations', [
        {'name': 'Radio Paradise', 'url': 'https://stream.radioparadise.com/mp3-192'},
        {'name': 'SomaFM Groove Salad', 'url': 'https://ice1.somafm.com/groovesalad-128-mp3'},
    ], 'Radio: Sender'),
    'bot.status_channel_id': ('id', None, 'Bot: Status- und Neustartkanal'),
    'github.channel_id': ('id', None, 'GitHub: Benachrichtigungskanal'),
    'github.user': ('text', '', 'GitHub: Account'),
    'github.repo_filter': ('text', '', 'GitHub: Repository-Filter (owner/repo, leer = alle)'),
    'twitch.channel_id': ('id', None, 'Twitch: Benachrichtigungskanal'),
    'twitch.channels': ('names', [], 'Twitch: Überwachte Loginnamen'),
    'stats.channel_all': ('id', None, 'Statistik: Alle Mitglieder'),
    'stats.channel_members': ('id', None, 'Statistik: Menschen'),
    'stats.channel_bots': ('id', None, 'Statistik: Bots'),
    'stats.channel_boosts': ('id', None, 'Statistik: Boosts'),
    'presence.type': ('activity', 'playing', 'Bot-Status: Aktivitätstyp'),
    'presence.text': ('text', '', 'Bot-Status: Text'),
    'docker.host': ('text', '', 'Docker: SSH-Ziel'),
    'docker.user': ('text', '', 'Docker: SSH-Benutzer'),
    'docker.key_file': ('text', '', 'Docker: Privater Schlüsselpfad auf dem Bot-Server'),
    'docker.allowed_users': ('ids', [], 'Docker: Erlaubte Discord-Benutzer'),
    'docker.channel_id': ('id', None, 'Docker: Steuerkanal'),
    'docker.container_twitch': ('text', '', 'Docker: Twitch-Containername'),
    'docker.container_landing': ('text', '', 'Docker: Landingpage-Containername'),
    'docker.container_portainer': ('text', '', 'Docker: Portainer-Containername'),
    'clear_chat.channel_id': ('id', None, 'Chat-Löschung: Zielkanal'),
    'clear_chat.allowed_users': ('ids', [], 'Chat-Löschung: Erlaubte Benutzer'),
    'requests.channel_id': ('id', None, 'Medienanfragen: Eingangskanal'),
    'requests.category_id': ('id', None, 'Medienanfragen: Kategorie'),
}


def normalize(key, value):
    if key not in SPECS:
        raise ValueError('Unbekannte Einstellung: ' + key)
    kind = SPECS[key][0]
    if kind == 'bool':
        if type(value) is not bool:
            raise ValueError(key + ': true oder false erforderlich')
    elif kind == 'repos':
        if not isinstance(value, list) or len(value) > 100 or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', v) for v in value):
            raise ValueError('Liste gültiger owner/repo-Namen erforderlich')
        value = list(dict.fromkeys(v.lower() for v in value))
    elif kind == 'stations':
        if not isinstance(value, list) or len(value) > 100:
            raise ValueError('Höchstens 100 Radiosender erlaubt.')
        names = set()
        for entry in value:
            if not isinstance(entry, dict) or set(entry) != {'name', 'url'}:
                raise ValueError('Sender benötigt Name und Stream-URL.')
            name, url = entry['name'], entry['url']
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or name.casefold() in names:
                raise ValueError('Sendernamen müssen eindeutig sein und 1–80 Zeichen enthalten.')
            names.add(name.casefold())
            parsed = urlparse(url) if isinstance(url, str) else None
            if not parsed or parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or len(url) > 2000 or any(c.isspace() for c in url):
                raise ValueError('Bitte eine direkte HTTP-/HTTPS-Stream-URL ohne Zugangsdaten eingeben.')
    elif kind == 'id':
        if value is None or value == '':
            return None
        if isinstance(value, str) and value.isascii() and value.isdigit():
            value = int(value)
        if type(value) is not int or not 0 < value < 2**64:
            raise ValueError(key + ': gültige positive Discord-ID erforderlich')
    elif kind == 'ids':
        if not isinstance(value, list):
            raise ValueError(key + ': Liste von Discord-IDs erforderlich')
        value = [normalize('bot.status_channel_id', item) for item in value]
        if None in value or len(value) > 1000:
            raise ValueError(key + ': ungültige Benutzerliste')
        value = list(dict.fromkeys(value))
    elif kind == 'names':
        if not isinstance(value, list) or len(value) > 100:
            raise ValueError(key + ': höchstens 100 Twitch-Loginnamen')
        if any(not isinstance(item, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,25}', item) for item in value):
            raise ValueError(key + ': ungültiger Twitch-Loginname')
        value = list(dict.fromkeys(item.lower() for item in value))
    elif kind == 'port':
        if isinstance(value, str) and value.isdigit():
            value = int(value)
        if type(value) is not int or not 1 <= value <= 65535:
            raise ValueError(key + ': Port zwischen 1 und 65535 erforderlich')
    else:
        if not isinstance(value, str) or len(value) > 2000:
            raise ValueError(key + ': Text mit höchstens 2000 Zeichen erforderlich')
        value = value.strip()
        if key.startswith('docker.container_') and value and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', value):
            raise ValueError(key + ': ungültiger Containername')
        if key == 'github.user' and value and not re.fullmatch(r'[A-Za-z0-9-]+', value):
            raise ValueError('Ungültiger GitHub-Account')
        if key == 'github.repo_filter' and value and not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', value):
            raise ValueError('Repository-Filter muss owner/repo entsprechen')
        if kind == 'url' and value:
            parsed = urlparse(value)
            if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError(key + ': HTTP-/HTTPS-Adresse ohne Zugangsdaten erforderlich')
        if kind == 'activity' and value not in ('playing', 'watching', 'listening', 'streaming'):
            raise ValueError('Ungültiger Aktivitätstyp')
    return value


GLOBAL_KEYS = {'presence.type', 'presence.text', 'github.allowed_repos',
               'docker.host', 'docker.user', 'docker.key_file',
               'docker.container_twitch', 'docker.container_landing', 'docker.container_portainer'}
GUILD_KEYS = set(SPECS) - GLOBAL_KEYS


def guild_key(value):
    if value is None:
        raise ValueError('Discord-Server muss ausdrücklich ausgewählt werden.')
    normalized = normalize('bot.status_channel_id', value)
    if normalized is None:
        raise ValueError('Discord-Server darf nicht leer sein.')
    return str(normalized)


class SettingsStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS guild_settings (guild TEXT NOT NULL,key TEXT NOT NULL,value TEXT NOT NULL,PRIMARY KEY(guild,key))')
            db.execute('CREATE TABLE IF NOT EXISTS settings_meta (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS guild_registry (guild TEXT PRIMARY KEY,name TEXT NOT NULL,active INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS github_guild_progress (guild TEXT,channel TEXT,source TEXT,cursor TEXT NOT NULL,PRIMARY KEY(guild,channel,source))')
            db.execute('CREATE TABLE IF NOT EXISTS twitch_delivery (guild TEXT,channel TEXT,login TEXT,state TEXT NOT NULL,PRIMARY KEY(guild,channel,login))')
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def legacy_values(self):
        with self.connect() as db:
            return {k: json.loads(v) for k,v in db.execute('SELECT key,value FROM settings') if k in GUILD_KEYS}

    def migration_done(self):
        with self.connect() as db:
            return db.execute("SELECT value FROM settings_meta WHERE key='guild_migration'").fetchone() is not None

    def migrate_legacy(self, guild_id):
        guild = guild_key(guild_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM settings_meta WHERE key='guild_migration'").fetchone():
                return
            rows = list(db.execute('SELECT key,value FROM settings'))
            old = {k: json.loads(v) for k,v in rows}
            db.executemany('INSERT OR IGNORE INTO guild_settings VALUES (?,?,?)',
                           [(guild,k,v) for k,v in rows if k in GUILD_KEYS])
            # Preserve the old notification policy only on the original guild.
            db.execute('INSERT OR IGNORE INTO guild_settings VALUES (?,?,?)',
                       (guild,'twitch.mention_everyone','true'))
            repo = old.get('github.repo_filter')
            if repo:
                allowed = old.get('github.allowed_repos', [])
                allowed = list(dict.fromkeys([*allowed, repo.lower()]))
                db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                           ('github.allowed_repos',json.dumps(allowed)))
            table = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='github_progress'").fetchone()
            if table and old.get('github.channel_id'):
                db.execute('INSERT OR IGNORE INTO github_guild_progress SELECT ?,?,source,cursor FROM github_progress',
                           (guild,str(old['github.channel_id'])))
            db.execute("INSERT INTO settings_meta VALUES ('guild_migration',?)", (guild,))

    def sync_guilds(self, guilds):
        with self.connect() as db:
            db.execute('UPDATE guild_registry SET active=0')
            db.executemany('INSERT INTO guild_registry VALUES (?,?,1) ON CONFLICT(guild) DO UPDATE SET name=excluded.name,active=1',
                           [(str(g.id),g.name) for g in guilds])

    def get(self, key, guild_id=None):
        if key not in SPECS:
            raise ValueError('Unbekannte Einstellung: ' + key)
        with self.connect() as db:
            if key in GLOBAL_KEYS:
                row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
            else:
                row = db.execute('SELECT value FROM guild_settings WHERE guild=? AND key=?', (guild_key(guild_id),key)).fetchone()
        return json.loads(row[0]) if row else copy.deepcopy(SPECS[key][1])

    def set_many(self, values, *, guild_id=None, only_missing=False):
        if not isinstance(values, dict):
            raise ValueError('Einstellungen müssen ein Objekt sein')
        normalized = {key: normalize(key,value) for key,value in values.items()}
        if guild_id is None:
            if any(k not in GLOBAL_KEYS for k in normalized):
                raise ValueError('Für diese Einstellungen einen Discord-Server auswählen.')
            insert = 'INSERT OR IGNORE INTO settings VALUES (?,?)' if only_missing else 'INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value'
            rows = [(k,json.dumps(v,ensure_ascii=False)) for k,v in normalized.items()]
        else:
            guild = guild_key(guild_id)
            if any(k not in GUILD_KEYS for k in normalized):
                raise ValueError('Globale Einstellungen können nicht als Server-Einstellung gespeichert werden.')
            insert = 'INSERT OR IGNORE INTO guild_settings VALUES (?,?,?)' if only_missing else 'INSERT INTO guild_settings VALUES (?,?,?) ON CONFLICT(guild,key) DO UPDATE SET value=excluded.value'
            rows = [(guild,k,json.dumps(v,ensure_ascii=False)) for k,v in normalized.items()]
        with self.connect() as db:
            db.executemany(insert,rows)

    def update_names(self, key, name, add, guild_id):
        guild = guild_key(guild_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT value FROM guild_settings WHERE guild=? AND key=?',(guild,key)).fetchone()
            values = json.loads(row[0]) if row else []
            values = list(dict.fromkeys(values+[name])) if add else [v for v in values if v!=name]
            values = normalize(key,values)
            db.execute('INSERT INTO guild_settings VALUES (?,?,?) ON CONFLICT(guild,key) DO UPDATE SET value=excluded.value',
                       (guild,key,json.dumps(values)))

    def describe(self, guild_id=None):
        entries = []
        for key,(kind,_,label) in SPECS.items():
            if kind=='stations' or ((guild_id is None) != (key in GLOBAL_KEYS)):
                continue
            value = self.get(key,guild_id)
            if kind=='id':
                value = '' if value is None else str(value)
            elif kind=='ids':
                value = [str(item) for item in value]
            entries.append({'key':key,'type':kind,'label':label,'value':value})
        return entries


_store = None


def store():
    global _store
    if _store is None:
        _store = SettingsStore(os.getenv('BOT_CONFIG_DB',str(ROOT/'data/settings.sqlite3')))
    return _store


def get_setting(key,guild_id=None):
    return store().get(key,guild_id)


def set_settings(values,guild_id=None):
    store().set_many(values,guild_id=guild_id)


def setting(key):
    return property(lambda self:get_setting(key,getattr(self,'guild_id',CURRENT_GUILD.get())),
                    lambda self,value:set_settings({key:value},getattr(self,'guild_id',CURRENT_GUILD.get())))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Bot-Einstellungen: globale Werte oder ausdrücklicher Discord-Server')
    parser.add_argument('--guild',help='Discord-Server-ID für Server-Einstellungen')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('list')
    setter=sub.add_parser('set')
    setter.add_argument('key')
    setter.add_argument('value')
    args=parser.parse_args()
    if args.command=='list':
        print(json.dumps(store().describe(args.guild),indent=2,ensure_ascii=False))
    else:
        try:
            value=json.loads(args.value)
        except ValueError:
            value=args.value
        set_settings({args.key:value},args.guild)
        print('Gespeichert:',args.key)
