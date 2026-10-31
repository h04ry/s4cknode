from flask import Flask, render_template, jsonify, request
from pathlib import Path
import json
import keyword
import socket
import subprocess
import sys

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config_store import store, set_settings, get_setting, guild_key

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 512 * 1024
BOT_DIR = Path(__file__).resolve().parent.parent
COGS_DIR = BOT_DIR / 'cogs'
SOCKET_PATH = BOT_DIR / '.runtime' / 'control.sock'


def control(action, **values):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(60)
            client.connect(str(SOCKET_PATH))
            client.sendall((json.dumps({'action': action, **values}) + '\n').encode())
            with client.makefile('rb') as stream:
                response = stream.readline(1024 * 1024)
            if not response:
                raise OSError('Keine Antwort')
            return json.loads(response)
    except (OSError, ValueError) as exc:
        return {'ok': False, 'status': 503,
                'error': f'Modulverwaltung nicht erreichbar ({exc}). Status vor erneutem Versuch prüfen.'}


def result(data):
    return jsonify(data), 200 if data.get('ok') else data.get('status', 400)


@app.route('/radio')
def radio_page():
    return render_template('radio.html')


@app.route('/api/radio', methods=['GET', 'POST'])
def radio_api():
    if request.method == 'GET':
        return result(control('radio_status'))
    data = request.get_json()
    if not isinstance(data, dict):
        return jsonify({'ok': False, 'error': 'Ungültige Anfrage'}), 400
    action = data.get('action')
    if action == 'stations':
        try:
            guild = guild_key(data.get('guild'))
            return result(control('guild_settings', guild=guild, settings={'radio.stations': data.get('stations')}))
        except ValueError as exc:
            return jsonify({'ok': False, 'error': str(exc)}), 400
        return jsonify({'ok': True})
    if action not in ('join', 'play', 'volume', 'stop'):
        return jsonify({'ok': False, 'error': 'Unbekannte Aktion'}), 400
    return result(control('radio_' + action, **{k: v for k, v in data.items() if k != 'action'}))


@app.route('/api/guilds')
def guilds_api():
    return result(control('guilds'))


@app.route('/api/settings')
def get_settings():
    guild = request.args.get('guild')
    try:
        if guild:
            guild = guild_key(guild)
            connected = control('guilds')
            if not connected.get('ok') or guild not in {g['id'] for g in connected.get('guilds', [])}:
                return jsonify({'ok': False, 'error': 'Server nicht verbunden.'}), 400
        elif request.args.get('scope') != 'global':
            raise ValueError('Einen Discord-Server oder den globalen Bereich auswählen.')
        return jsonify({'ok': True, 'guild': guild, 'settings': store().describe(guild)})
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400


@app.route('/api/settings', methods=['POST'])
def save_settings():
    data = request.get_json()
    if not isinstance(data, dict) or not isinstance(data.get('settings'), dict):
        return jsonify({'ok': False, 'error': 'Einstellungen fehlen'}), 400
    values = data['settings']
    if data.get('guild') is not None:
        try:
            guild = guild_key(data['guild'])
        except ValueError as exc:
            return jsonify({'ok': False, 'error': str(exc)}), 400
        return result(control('guild_settings', guild=guild, settings=values))
    if data.get('scope') != 'global':
        return jsonify({'ok': False, 'error': 'Server oder globalen Bereich auswählen.'}), 400
    try:
        set_settings(values)
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    refreshed = control('refresh_settings', changed=list(values)) if values else {'ok': True}
    warning = refreshed.get('warning')
    if not refreshed.get('ok'):
        warning = 'Gespeichert. Bot gerade nicht erreichbar; Werte gelten bei der nächsten Verwendung. Bot-Status gegebenenfalls später erneut setzen.'
    return jsonify({'ok': True, 'warning': warning})


def cog_path(name):
    if (not name.isascii() or not name.isidentifier() or keyword.iskeyword(name)
            or name.startswith('_') or len(name) > 40):
        return None
    for suffix in ('.py', '.py.off'):
        path = COGS_DIR / (name + suffix)
        if path.is_file() and not path.is_symlink():
            return path
    return None


@app.route('/api/cogs')
def list_cogs():
    data = control('list')
    if data.get('ok'):
        return jsonify(data['cogs'])
    cogs = []
    for path in sorted(COGS_DIR.iterdir()):
        suffix = '.py.off' if path.name.endswith('.py.off') else '.py'
        if path.name.endswith(suffix) and not path.name.startswith('_'):
            cogs.append({'name': path.name[:-len(suffix)], 'file': path.name,
                         'enabled': suffix == '.py', 'loaded': None})
    return jsonify(cogs)


@app.route('/api/cog/<name>')
def get_cog(name):
    path = cog_path(name)
    if path is None:
        return jsonify({'error': 'Modul nicht gefunden'}), 404
    data = control('list')
    loaded = next((c['loaded'] for c in data.get('cogs', []) if c['name'] == name), None)
    return jsonify({'content': path.read_text(encoding='utf-8'),
                    'enabled': path.suffix == '.py', 'loaded': loaded, 'file': path.name})


@app.route('/api/cog/<name>', methods=['POST'])
def save_cog(name):
    return result(control('save', name=name, content=(request.get_json() or {}).get('content')))


@app.route('/api/cog', methods=['POST'])
def create_cog():
    name = (request.get_json() or {}).get('name', '')
    if isinstance(name, str):
        name = name.strip().lower().replace(' ', '_')
    return result(control('create', name=name))


@app.route('/api/cog/<name>/toggle', methods=['POST'])
def toggle_cog(name):
    return result(control('toggle', name=name, enabled=(request.get_json() or {}).get('enabled')))


@app.route('/api/cog/<name>', methods=['DELETE'])
def delete_cog(name):
    return result(control('delete', name=name))


@app.route('/api/main')
def get_main():
    return jsonify({'content': (BOT_DIR / 'main.py').read_text(encoding='utf-8')})


@app.route('/api/main', methods=['POST'])
def save_main():
    content = (request.get_json() or {}).get('content')
    try:
        if not isinstance(content, str):
            raise ValueError('Quellcode fehlt')
        compile(content, 'main.py', 'exec')
        import sys
        if str(BOT_DIR) not in sys.path:
            sys.path.insert(0, str(BOT_DIR))
        from runtime_control import ModuleControl
        manager = ModuleControl(None, BOT_DIR)
        manager.runtime.mkdir(mode=0o700, exist_ok=True)
        path = BOT_DIR / 'main.py'
        manager.backup(path)
        manager.write_source(path, content)
    except (ValueError, SyntaxError, OSError) as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    return jsonify({'ok': True, 'restart_required': True})


@app.route('/api/status')
def bot_status():
    state = subprocess.run(['systemctl', 'is-active', 'discordbot'], capture_output=True, text=True)
    uptime = subprocess.run(['systemctl', 'show', 'discordbot', '--property=ActiveEnterTimestamp'],
                            capture_output=True, text=True).stdout.strip().replace('ActiveEnterTimestamp=', '')
    return jsonify({'status': state.stdout.strip(), 'since': uptime})


@app.route('/api/restart', methods=['POST'])
def restart_bot():
    process = subprocess.run(['sudo', '-n', 'systemctl', 'restart', 'discordbot'], capture_output=True, text=True)
    return jsonify({'ok': process.returncode == 0, 'err': process.stderr})


@app.route('/api/logs')
def get_logs():
    process = subprocess.run(['journalctl', '-u', 'discordbot', '-n', '150', '--no-pager', '--output=short'],
                             capture_output=True, text=True)
    return jsonify({'logs': process.stdout})


@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
