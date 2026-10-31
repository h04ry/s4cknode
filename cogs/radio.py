import asyncio
import logging
import shutil
import re
import time
from pathlib import Path
from urllib.request import Request, urlopen
import discord
from discord.ext import commands, tasks
from config_store import get_setting, store

log = logging.getLogger(__name__)


class RadioStream:
    """Python handles HTTPS/DNS; the decoder reads audio through a pipe."""
    def __init__(self, url):
        self.url = url
        self.closed = False
        self.title = ''
        self.response = self.open()

    def open(self):
        response = urlopen(Request(self.url, headers={'User-Agent': 'S4CKNode-Radio/1.0', 'Icy-MetaData': '1'}), timeout=12)
        try:
            self.meta_interval = max(0, int(response.headers.get('icy-metaint', '0')))
        except ValueError:
            self.meta_interval = 0
        self.remaining = self.meta_interval
        self.title = ''
        return response

    def exact(self, size):
        data = bytearray()
        while len(data) < size:
            part = self.response.read(size - len(data))
            if not part:
                raise OSError('Stream ended')
            data.extend(part)
        return bytes(data)

    def audio_read(self, size):
        if not self.meta_interval:
            return self.response.read(size)
        audio = self.exact(min(size, self.remaining))
        self.remaining -= len(audio)
        if self.remaining == 0:
            length = self.exact(1)[0] * 16
            metadata = self.exact(length) if length else b''
            try:
                text = metadata.rstrip(b'\0').decode('utf-8')
            except UnicodeDecodeError:
                text = metadata.rstrip(b'\0').decode('latin-1')
            match = re.search(r"StreamTitle='(.*?)';", text, re.DOTALL)
            if match:
                self.title = match.group(1).strip()[:500]
            self.remaining = self.meta_interval
        return audio

    def read(self, size):
        for attempt in range(3):
            if self.closed:
                return b''
            try:
                data = self.audio_read(size)
                if data:
                    return data
            except OSError:
                pass
            if self.closed:
                return b''
            self.response.close()
            try:
                self.response = self.open()
            except OSError:
                continue
        return b''

    def close(self):
        self.closed = True
        self.response.close()


class RadioAudio(discord.PCMVolumeTransformer):
    def __init__(self, stream, executable, volume):
        self.stream = stream
        try:
            decoder = discord.FFmpegPCMAudio(stream, pipe=True, executable=executable,
                before_options='-nostdin -probesize 32768 -analyzeduration 1000000',
                options='-vn -threads 1 -loglevel error')
            super().__init__(decoder, volume=volume / 100)
        except Exception:
            stream.close()
            raise

    def cleanup(self):
        self.stream.close()
        super().cleanup()


class Radio(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lock = asyncio.Lock()
        self.errors = {}
        self.empty_since = {}
        self.empty_timeout = 120
        self.clock = time.monotonic
        with store().connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS radio_state (guild TEXT PRIMARY KEY, station TEXT NOT NULL, volume INTEGER NOT NULL)')
        self.empty_watch.start()

    async def check_empty(self):
        async with self.lock:
            connected = set()
            for vc in list(self.bot.voice_clients):
                if not vc.is_connected():
                    continue
                guild_id = vc.guild.id
                connected.add(guild_id)
                if any(not member.bot for member in vc.channel.members):
                    self.empty_since.pop(guild_id, None)
                    continue
                previous = self.empty_since.get(guild_id)
                if previous is None or previous[0] != vc.channel.id:
                    self.empty_since[guild_id] = (vc.channel.id, self.clock())
                elif self.clock() - previous[1] >= self.empty_timeout:
                    # Recheck after waiting: a returning listener cancels departure.
                    if not any(not member.bot for member in vc.channel.members):
                        await vc.disconnect(force=True)
                    self.empty_since.pop(guild_id, None)
            for guild_id in list(self.empty_since):
                if guild_id not in connected:
                    self.empty_since.pop(guild_id, None)

    @tasks.loop(seconds=10)
    async def empty_watch(self):
        try:
            await self.check_empty()
        except Exception:
            log.exception('Radio empty-channel check failed')

    @empty_watch.before_loop
    async def before_empty_watch(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel != after.channel:
            await self.check_empty()

    def state(self, guild_id):
        with store().connect() as db:
            row = db.execute('SELECT station,volume FROM radio_state WHERE guild=?', (str(guild_id),)).fetchone()
        stations = get_setting('radio.stations', guild_id)
        return {'station': row[0] if row else (stations[0]['name'] if stations else ''), 'volume': row[1] if row else 30}

    def save(self, guild_id, **changes):
        state = self.state(guild_id)
        state.update(changes)
        with store().connect() as db:
            db.execute('INSERT INTO radio_state VALUES (?,?,?) ON CONFLICT(guild) DO UPDATE SET station=excluded.station,volume=excluded.volume',
                       (str(guild_id), state['station'], state['volume']))
        return state

    def source(self, url, volume):
        if not discord.opus.is_loaded():
            import ctypes.util
            library = ctypes.util.find_library('opus')
            if not library:
                library = str(Path(__file__).resolve().parents[1] / '.runtime/radio-system/usr/lib/x86_64-linux-gnu/libopus.so.0')
            discord.opus.load_opus(library)
        executable = shutil.which('ffmpeg')
        if not executable:
            import imageio_ffmpeg
            executable = imageio_ffmpeg.get_ffmpeg_exe()
        return RadioAudio(RadioStream(url), executable, volume)

    async def play(self, guild, name):
        station = next((s for s in get_setting('radio.stations', guild.id) if s['name'].casefold() == name.casefold()), None)
        if not station:
            raise ValueError('Sender nicht gefunden. Bitte zuerst einen Sender anlegen oder auswählen.')
        vc = guild.voice_client
        if not vc or not vc.is_connected():
            raise ValueError('Bitte zuerst !radiojoin verwenden oder im Web einen Sprachkanal verbinden.')
        source = await asyncio.to_thread(self.source, station['url'], self.state(guild.id)['volume'])
        try:
            vc.stop()
            def finished(error):
                if error:
                    self.errors[guild.id] = 'Stream abgebrochen. Bitte Sender erneut starten.'
                    log.warning('Radio playback failed in guild %s: %s', guild.id, type(error).__name__)
            vc.play(source, after=finished)
        except Exception:
            source.cleanup()
            raise
        self.errors.pop(guild.id, None)
        self.save(guild.id, station=station['name'])

    async def join(self, channel, station_name=None):
        if not isinstance(channel, discord.VoiceChannel):
            raise ValueError('Bitte einen normalen Sprachkanal auswählen.')
        permissions = channel.permissions_for(channel.guild.me)
        if not permissions.connect or not permissions.speak:
            raise ValueError('Dem Bot fehlen die Rechte Verbinden oder Sprechen in diesem Kanal.')
        vc = channel.guild.voice_client
        if vc and vc.is_connected():
            await vc.move_to(channel)
        else:
            await channel.connect(timeout=25, reconnect=True, self_deaf=True)
        selected = station_name or self.state(channel.guild.id)['station']
        if selected:
            await self.play(channel.guild, selected)

    async def volume(self, guild, value):
        if type(value) is not int or not 0 <= value <= 100:
            raise ValueError('Die Lautstärke muss zwischen 0 und 100 liegen.')
        self.save(guild.id, volume=value)
        if guild.voice_client and isinstance(guild.voice_client.source, discord.PCMVolumeTransformer):
            guild.voice_client.source.volume = value / 100

    async def cog_unload(self):
        watcher = self.empty_watch.get_task()
        self.empty_watch.cancel()
        if watcher:
            await asyncio.gather(watcher, return_exceptions=True)
        self.empty_since.clear()
        for vc in list(self.bot.voice_clients):
            await vc.disconnect(force=True)

    def status(self):
        return {'ok': True, 'guilds': [
            {'id': str(g.id), 'name': g.name, 'stations': get_setting('radio.stations', g.id), **self.state(g.id),
             'connected': bool(g.voice_client and g.voice_client.is_connected()),
             'playing': bool(g.voice_client and g.voice_client.is_playing()),
             'channel': g.voice_client.channel.name if g.voice_client else '',
             'error': self.errors.get(g.id, ''),
             'channels': [{'id': str(c.id), 'name': c.name, 'members': len(c.members)} for c in g.voice_channels
                          if c != g.afk_channel and c.id not in {get_setting('stats.channel_all', g.id), get_setting('stats.channel_members', g.id), get_setting('stats.channel_bots', g.id), get_setting('stats.channel_boosts', g.id)}
                          and c.permissions_for(g.me).connect and c.permissions_for(g.me).speak]}
            for g in self.bot.guilds]}

    async def handle(self, request):
        async with self.lock:
            if request['action'] == 'radio_status':
                return self.status()
            guild = self.bot.get_guild(int(request.get('guild', 0)))
            if not guild:
                raise ValueError('Discord-Server auswählen.')
            action = request['action']
            if action == 'radio_join':
                await self.join(guild.get_channel(int(request.get('channel', 0))), request.get('station'))
            elif action == 'radio_play':
                await self.play(guild, request.get('station', ''))
            elif action == 'radio_volume':
                await self.volume(guild, request.get('volume'))
            elif action == 'radio_stop':
                if guild.voice_client:
                    await guild.voice_client.disconnect(force=True)
            else:
                raise ValueError('Unbekannte Radioaktion')
            return self.status()

    async def respond(self, ctx, operation, allow_move=False):
        try:
            member_channel = getattr(getattr(ctx.author, 'voice', None), 'channel', None)
            if not member_channel:
                raise ValueError('Du musst dich in einem Sprachkanal befinden.')
            vc = ctx.guild.voice_client
            if vc and vc.channel != member_channel and not allow_move:
                raise ValueError('Bitte dem Sprachkanal des Bots beitreten, um das Radio zu steuern.')
            async with self.lock:
                await operation(member_channel)
            await ctx.send('Radio-Einstellung übernommen.')
        except Exception as exc:
            log.warning('Radio command failed: %s', type(exc).__name__)
            message = str(exc) if isinstance(exc, ValueError) else 'Voice-Verbindung oder Wiedergabe fehlgeschlagen. Bitte Bot-Rechte und Stream prüfen.'
            await ctx.send(message)

    async def cog_command_error(self, ctx, error):
        if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send('Bitte vollständig eingeben: !radiosender <Sendername> oder !radiolautstärke <0–100>.')
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send('Radiobefehle funktionieren nur auf einem Discord-Server.')
        else:
            log.error('Radio command error: %s', type(error).__name__)
            await ctx.send('Radiobefehl fehlgeschlagen. Bitte erneut versuchen.')

    @commands.command(name='radiolist')
    @commands.guild_only()
    async def radiolist(self, ctx):
        stations = get_setting('radio.stations', ctx.guild.id)
        text = '\n'.join(f"• {s['name']}" for s in stations) or 'Noch keine Sender eingerichtet. Öffne Radio im Webinterface.'
        chunks = []
        for line in text.splitlines():
            if not chunks or len(chunks[-1]) + len(line) + 1 > 1900:
                chunks.append(line)
            else:
                chunks[-1] += '\n' + line
        for chunk in chunks:
            await ctx.send(chunk, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='radiotitel')
    @commands.guild_only()
    async def radiotitle(self, ctx):
        vc = ctx.guild.voice_client
        if not vc or not vc.is_connected() or not vc.is_playing():
            await ctx.send('Gerade läuft kein Radio. Starte es mit !radiojoin.')
            return
        stream = getattr(getattr(vc, 'source', None), 'stream', None)
        title = getattr(stream, 'title', '')
        station = self.state(ctx.guild.id)['station']
        text = f'📻 **{discord.utils.escape_markdown(station)}**\n'
        text += ('🎵 ' + discord.utils.escape_markdown(title)) if title else 'Der Sender liefert gerade keine Titelinformationen. Bitte nach einigen Sekunden erneut versuchen.'
        await ctx.send(text, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='radiojoin')
    @commands.guild_only()
    async def radiojoin(self, ctx):
        await self.respond(ctx, self.join, allow_move=True)

    @commands.command(name='radiolautstärke', aliases=['radiolautstaerke'])
    @commands.guild_only()
    async def radiovolume(self, ctx, lautstaerke: int):
        await self.respond(ctx, lambda channel: self.volume(ctx.guild, lautstaerke))

    @commands.command(name='radiosender')
    @commands.guild_only()
    async def radiostation(self, ctx, *, sender: str):
        await self.respond(ctx, lambda channel: self.play(ctx.guild, sender))

    @commands.command(name='radiostop')
    @commands.guild_only()
    async def radiostop(self, ctx):
        async def stop(channel):
            if ctx.guild.voice_client:
                await ctx.guild.voice_client.disconnect(force=True)
        await self.respond(ctx, stop)


async def setup(bot):
    await bot.add_cog(Radio(bot))
