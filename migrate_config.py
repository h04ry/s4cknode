"""One-time importer for existing installations. Never prints private values."""
import argparse
import ast
import json
from pathlib import Path
from dotenv import dotenv_values, set_key, unset_key
from config_store import SettingsStore

FIELDS = {
 'github_monitor': {'channel_id':'github.channel_id','github_user':'github.user','repo_filter':'github.repo_filter'},
 'clear_chat': {'target_channel_id':'clear_chat.channel_id','allowed_users':'clear_chat.allowed_users'},
 'media_requests': {'request_channel_id':'requests.channel_id','category_id':'requests.category_id'},
 'remote_docker': {'target_host':'docker.host','target_user':'docker.user','allowed_users':'docker.allowed_users','allowed_channel':'docker.channel_id'},
}
ENV_SETTINGS = {
 'DISCORD_NOTIFY_CHANNEL':'twitch.channel_id',
 'STATS_CHANNEL_ALL':'stats.channel_all',
 'STATS_CHANNEL_MEMBERS':'stats.channel_members',
 'STATS_CHANNEL_BOTS':'stats.channel_bots',
 'STATS_CHANNEL_BOOSTS':'stats.channel_boosts',
}


def literals(path):
    if not path.exists():
        return {}
    values = {}
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            name = target.attr if isinstance(target, ast.Attribute) else target.id if isinstance(target, ast.Name) else None
            if name:
                try:
                    values[name] = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    pass
    return values


def collect(root):
    settings, secrets = {}, {}
    main = literals(root / 'main.py')
    if 'STATUS_CHANNEL_ID' in main:
        settings['bot.status_channel_id'] = main['STATUS_CHANNEL_ID']
    for name, mapping in FIELDS.items():
        path = next((p for suffix in ('.py', '.py.off') if (p := root/'cogs'/(name+suffix)).exists()), None)
        values = literals(path) if path else {}
        for attribute, key in mapping.items():
            if attribute in values:
                settings[key] = '' if values[attribute] is None else values[attribute]
        if name == 'remote_docker':
            for container, value in values.get('containers', {}).items():
                settings['docker.container_' + container] = value
            if path:
                for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                    if isinstance(node, ast.keyword) and node.arg == 'key_filename':
                        try:
                            settings['docker.key_file'] = ast.literal_eval(node.value)
                        except ValueError:
                            pass
    env_path = root / '.env'
    env = dotenv_values(env_path) if env_path.exists() else {}
    for variable, key in ENV_SETTINGS.items():
        if env.get(variable):
            settings[key] = env[variable]
    # Old Twitch code had a default ID in getenv(), not a simple assignment.
    if 'twitch.channel_id' not in settings:
        for suffix in ('.py', '.py.off'):
            path = root / 'cogs' / ('twitch_notify' + suffix)
            if path.exists():
                for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                            and node.func.attr == 'getenv' and len(node.args) > 1
                            and isinstance(node.args[0], ast.Constant) and node.args[0].value == 'DISCORD_NOTIFY_CHANNEL'):
                        settings['twitch.channel_id'] = ast.literal_eval(node.args[1])
    path = root / 'status_config.json'
    if path.exists():
        status = json.loads(path.read_text())
        settings.update({'presence.type': status['type'], 'presence.text': status['text']})
    path = root / 'twitch_channels.json'
    if path.exists():
        settings['twitch.channels'] = json.loads(path.read_text())
    return settings, secrets


def migrate(root):
    settings, secrets = collect(root)
    database = SettingsStore(root / 'data/settings.sqlite3')
    # Existing database values win when rerunning the importer.
    database.set_many(settings, only_missing=True)
    env_path = root / '.env'
    env = dotenv_values(env_path) if env_path.exists() else {}
    for key, value in secrets.items():
        if not env.get(key):
            set_key(str(env_path), key, str(value))
    if env_path.exists():
        for variable in ENV_SETTINGS:
            if variable in env:
                unset_key(str(env_path), variable)
        env_path.chmod(0o600)
    return len(settings), len(secrets)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    count, credentials = migrate(args.root)
    print(f'Migration abgeschlossen: {count} Einstellungen geprüft; {credentials} Zugangsdatenfelder nach .env übernommen/geprüft. Keine Werte ausgegeben.')
