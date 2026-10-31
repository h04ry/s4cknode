import asyncio
import json
import logging
import discord
from discord.ext import commands, tasks
from config_store import get_setting, set_settings

log = logging.getLogger(__name__)


class Presence(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lock = asyncio.Lock()
        self.last_signature = None
        self.base_activity = self.make_saved_activity()
        self.radio_status_watch.start()

    def save_status(self, activity_type, text):
        set_settings({'presence.type': activity_type, 'presence.text': text})

    def load_status(self):
        text = get_setting('presence.text')
        return {'type': get_setting('presence.type'), 'text': text} if text else None

    @staticmethod
    def make_activity(activity_type, text):
        types = {'playing': discord.ActivityType.playing,
                 'watching': discord.ActivityType.watching,
                 'listening': discord.ActivityType.listening,
                 'streaming': discord.ActivityType.streaming}
        return discord.Activity(type=types.get(activity_type.lower(), discord.ActivityType.playing), name=text)

    def make_saved_activity(self):
        saved = self.load_status()
        return self.make_activity(saved['type'], saved['text']) if saved else self.bot.activity

    def radio_activity(self):
        radio = self.bot.get_cog('Radio')
        if radio is None:
            return None
        playing = [vc for vc in self.bot.voice_clients if vc.is_connected() and vc.is_playing()]
        if len(self.bot.guilds) > 1 and playing:
            return discord.CustomActivity(name=f'📻 Radio auf {len(playing)} Server(n)')
        for vc in playing:
            if vc.is_connected() and vc.is_playing():
                station = radio.state(vc.guild.id)['station']
                stream = getattr(getattr(vc, 'source', None), 'stream', None)
                title = getattr(stream, 'title', '')
                text = f'📻 Streamt {station}' + (f' – {title}' if title else '')
                # Custom text avoids a fake Twitch/YouTube stream link.
                return discord.CustomActivity(name=text[:128])
        return None

    async def refresh(self, force=False):
        async with self.lock:
            activity = self.radio_activity() or self.base_activity
            signature = json.dumps(activity.to_dict() if activity else None, sort_keys=True)
            if force or signature != self.last_signature:
                await self.bot.change_presence(activity=activity)
                self.last_signature = signature

    @tasks.loop(seconds=10)
    async def radio_status_watch(self):
        try:
            await self.refresh()
        except Exception:
            log.exception('Radio status update failed')

    @radio_status_watch.before_loop
    async def before_radio_status_watch(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.refresh(force=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if self.bot.user and member.id == self.bot.user.id and before.channel != after.channel:
            await self.refresh()

    async def set_presence_internal(self, activity_type, text):
        self.base_activity = self.make_activity(activity_type, text)
        await self.refresh()

    async def cog_unload(self):
        task = self.radio_status_watch.get_task()
        self.radio_status_watch.cancel()
        if task:
            await asyncio.gather(task, return_exceptions=True)
        if self.bot.is_ready():
            await self.bot.change_presence(activity=self.base_activity)

    @commands.command(name='status')
    @commands.is_owner()
    async def status(self, ctx, activity_type: str, *, text: str):
        activity_type = activity_type.lower()
        if activity_type not in ('playing', 'watching', 'listening', 'streaming'):
            await ctx.send('❌ Typen: `playing`, `watching`, `listening`, `streaming`')
            return
        await self.set_presence_internal(activity_type, text)
        self.save_status(activity_type, text)
        await ctx.send('✅ Status gespeichert. Während Radio läuft, bleibt dessen Anzeige aktiv.'
                       if self.radio_activity() else f'✅ Status gesetzt und gespeichert: **{activity_type} {text}**')


async def setup(bot):
    await bot.add_cog(Presence(bot))
