"""Local module management, executed on the Discord bot's event loop."""
import asyncio
import importlib
import importlib.util
import json
import keyword
import os
from pathlib import Path
import tempfile
import uuid
from config_store import get_setting, set_settings
from guild_config import validate_guild_values


class ModuleControl:
    def __init__(self, bot, root):
        self.bot = bot
        self.root = Path(root)
        self.cogs = self.root / 'cogs'
        self.runtime = self.root / '.runtime'
        self.socket_path = self.runtime / 'control.sock'
        self.lock = asyncio.Lock()
        self.server = None

    async def start(self):
        self.runtime.mkdir(mode=0o700, exist_ok=True)
        self.runtime.chmod(0o700)
        self.socket_path.unlink(missing_ok=True)
        self.server = await asyncio.start_unix_server(
            self.handle, path=str(self.socket_path), limit=1024 * 1024)
        self.socket_path.chmod(0o600)

    async def close(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.socket_path.unlink(missing_ok=True)

    async def handle(self, reader, writer):
        try:
            line = await asyncio.wait_for(reader.readline(), 10)
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError('Ungültige Anfrage')
            async with self.lock:
                result = await self.execute(request)
        except Exception as exc:
            result = {'ok': False, 'error': str(exc), 'status': 400}
        try:
            writer.write((json.dumps(result) + '\n').encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    def validate_name(self, name):
        if (not isinstance(name, str) or not name.isascii()
                or not name.isidentifier() or keyword.iskeyword(name)
                or name.startswith('_') or len(name) > 40):
            raise ValueError('Modulname: Buchstaben, Zahlen und Unterstriche; nicht mit einer Zahl beginnen.')
        return name

    def path_for(self, name):
        for suffix in ('.py', '.py.off'):
            path = self.cogs / (name + suffix)
            if path.is_symlink():
                raise ValueError('Verknüpfungen werden nicht unterstützt')
            if path.exists():
                return path
        return None

    def write_source(self, path, source):
        # Atomic replacement also avoids half-written files after interruption.
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.module-')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(source)
            os.chmod(temporary, path.stat().st_mode & 0o777 if path.exists() else 0o644)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        if path.suffix == '.py':
            Path(importlib.util.cache_from_source(str(path))).unlink(missing_ok=True)
        importlib.invalidate_caches()

    def backup(self, path):
        directory = self.runtime / 'backups'
        directory.mkdir(mode=0o700, exist_ok=True)
        target = directory / (path.name + '.' + uuid.uuid4().hex + '.bak')
        target.write_bytes(path.read_bytes())
        target.chmod(0o600)

    async def sync_commands(self, before):
        # Avoid an API call for edits that do not change slash command definitions.
        after = [c.to_dict(self.bot.tree) for c in self.bot.tree.get_commands()]
        if before != after:
            try:
                await self.bot.tree.sync()
            except Exception as exc:
                return f'Modul übernommen; Discord-Befehlssynchronisierung fehlgeschlagen: {exc}'
        return None

    async def execute(self, request):
        action = request.get('action')
        if action == 'guilds':
            return {'ok': True, 'guilds': [{'id': str(g.id), 'name': g.name} for g in self.bot.guilds]}
        if action == 'guild_settings':
            guild = self.bot.get_guild(int(request.get('guild', 0)))
            if guild is None:
                raise ValueError('Dieser Discord-Server ist nicht mit dem Bot verbunden.')
            values = validate_guild_values(guild, request.get('settings'))
            set_settings(values, guild.id)
            return {'ok': True}
        if isinstance(action, str) and action.startswith('radio_'):
            radio = self.bot.get_cog('Radio')
            if radio is None:
                raise ValueError('Das Radio-Modul ist nicht geladen.')
            return await radio.handle(request)
        if action == 'refresh_settings':
            changed = request.get('changed', [])
            warning = None
            if any(key in changed for key in ('presence.type', 'presence.text')):
                presence = self.bot.get_cog('Presence')
                if presence and self.bot.is_ready():
                    try:
                        await presence.set_presence_internal(get_setting('presence.type'), get_setting('presence.text'))
                    except Exception as exc:
                        warning = f'Einstellungen gespeichert; Bot-Status konnte nicht aktualisiert werden: {exc}'
            return {'ok': True, 'warning': warning}
        if action == 'list':
            modules = []
            for path in sorted(self.cogs.iterdir()):
                suffix = '.py.off' if path.name.endswith('.py.off') else '.py'
                if not path.name.endswith(suffix) or path.name.startswith('_'):
                    continue
                name = path.name[:-len(suffix)]
                modules.append({'name': name, 'file': path.name,
                                'enabled': suffix == '.py',
                                'loaded': 'cogs.' + name in self.bot.extensions})
            return {'ok': True, 'cogs': modules}
        if action not in {'save', 'create', 'toggle', 'delete'}:
            raise ValueError('Unbekannte Aktion')
        if not self.bot.is_ready():
            return {'ok': False, 'error': 'Bot ist noch nicht mit Discord verbunden. Bitte erneut versuchen.', 'status': 503}
        name = self.validate_name(request.get('name'))
        path = self.path_for(name)
        extension = 'cogs.' + name
        loaded = extension in self.bot.extensions
        before = [c.to_dict(self.bot.tree) for c in self.bot.tree.get_commands()]
        if action == 'create':
            if path:
                raise ValueError('Modul existiert bereits')
            source = ('from discord.ext import commands\n\n'
                      f'class Module_{name}(commands.Cog):\n'
                      '    def __init__(self, bot):\n        self.bot = bot\n\n'
                      f'async def setup(bot):\n    await bot.add_cog(Module_{name}(bot))\n')
            path = self.cogs / (name + '.py')
            self.write_source(path, source)
            try:
                await self.bot.load_extension(extension)
            except Exception:
                path.unlink(missing_ok=True)
                raise
        else:
            if path is None:
                return {'ok': False, 'error': 'Modul nicht gefunden', 'status': 404}
            if action == 'save':
                source = request.get('content')
                if not isinstance(source, str):
                    raise ValueError('Quellcode fehlt')
                compile(source, str(path), 'exec')
                old_source = path.read_text(encoding='utf-8')
                self.backup(path)
                self.write_source(path, source)
                try:
                    if path.suffix == '.py':
                        if loaded:
                            await self.bot.reload_extension(extension)
                        else:
                            await self.bot.load_extension(extension)
                except Exception:
                    # discord.py restores the previous extension on reload failure.
                    self.write_source(path, old_source)
                    raise
            elif action == 'toggle':
                enabled = request.get('enabled')
                if not isinstance(enabled, bool):
                    raise ValueError('Gewünschter Status fehlt')
                target = self.cogs / (name + ('.py' if enabled else '.py.off'))
                if target != path and target.exists():
                    raise ValueError('Beide Moduldateien existieren bereits')
                if enabled:
                    compile(path.read_text(encoding='utf-8'), str(path), 'exec')
                    path.rename(target)
                    importlib.invalidate_caches()
                    try:
                        if not loaded:
                            await self.bot.load_extension(extension)
                    except Exception:
                        target.rename(path)
                        raise
                else:
                    if loaded:
                        await self.bot.unload_extension(extension)
                    try:
                        path.rename(target)
                    except Exception:
                        if loaded:
                            await self.bot.load_extension(extension)
                        raise
                path = target
            elif action == 'delete':
                self.backup(path)
                if loaded:
                    await self.bot.unload_extension(extension)
                try:
                    path.unlink()
                except Exception:
                    if loaded:
                        await self.bot.load_extension(extension)
                    raise
        warning = await self.sync_commands(before)
        return {'ok': True, 'name': name, 'file': path.name,
                'enabled': path.suffix == '.py',
                'loaded': extension in self.bot.extensions, 'warning': warning}
