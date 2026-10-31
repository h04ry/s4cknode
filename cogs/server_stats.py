import asyncio
import logging
import discord
from discord.ext import commands,tasks
from config_store import get_setting,set_settings

log=logging.getLogger(__name__)
COUNTERS={'all':'👥 Alle Member','members':'🧑 Member','bots':'🤖 Bots','boosts':'✨ Boosts'}


class ServerStats(commands.Cog):
    def __init__(self,bot):
        self.bot=bot
        self.lock=asyncio.Lock()
        self.update_stats.start()

    async def cog_unload(self):
        task=self.update_stats.get_task()
        self.update_stats.cancel()
        if task:
            await asyncio.gather(task,return_exceptions=True)

    async def update_guild(self,guild):
        count=guild.member_count or len(guild.members)
        bots=sum(m.bot for m in guild.members)
        values={'all':count,'members':count-bots,'bots':bots,'boosts':guild.premium_subscription_count or 0}
        for key,label in COUNTERS.items():
            channel=guild.get_channel(get_setting('stats.channel_'+key,guild.id))
            name=f'{label}: {values[key]}'
            if isinstance(channel,discord.VoiceChannel) and channel.name!=name:
                await channel.edit(name=name,reason='Eigene Serverstatistik aktualisieren')

    @tasks.loop(minutes=10)
    async def update_stats(self):
        async with self.lock:
            for guild in self.bot.guilds:
                try:
                    await self.update_guild(guild)
                except Exception:
                    log.exception('Statistik für einen Server konnte nicht aktualisiert werden')

    @update_stats.before_loop
    async def before_update(self):
        await self.bot.wait_until_ready()

    @commands.group(name='stats',invoke_without_command=True)
    @commands.guild_only()
    @commands.has_guild_permissions(administrator=True)
    async def stats_group(self,ctx):
        await ctx.send('`!stats setup` – Statistik einrichten/reparieren (ohne Duplikate)\n'
                       '`!stats update` – nur diesen Server aktualisieren\n`!stats info` – eigene Kanal-IDs')

    @stats_group.command(name='setup')
    @commands.has_guild_permissions(administrator=True)
    async def setup_channels(self,ctx):
        await self.ensure_guild(ctx.guild)
        await ctx.send('✅ Statistik für diesen Server eingerichtet. Vorhandene Statistikkanäle wurden wiederverwendet.')

    async def ensure_guild(self,guild):
        async with self.lock:
            category=discord.utils.get(guild.categories,name='📊 SERVER STATS')
            channels={key:guild.get_channel(get_setting('stats.channel_'+key,guild.id)) for key in COUNTERS}
            if not category:
                category=next((c.category for c in channels.values() if c and c.category),None)
            if not category:
                category=await guild.create_category('📊 SERVER STATS',overwrites={
                    guild.default_role:discord.PermissionOverwrite(view_channel=True,connect=False),
                    guild.me:discord.PermissionOverwrite(view_channel=True,manage_channels=True)},
                    reason='Serverstatistik einrichten')
            for key,label in COUNTERS.items():
                channel=channels[key]
                if not isinstance(channel,discord.VoiceChannel):
                    channel=next((c for c in category.voice_channels if c.name.startswith(label+':')),None)
                if not channel:
                    channel=await guild.create_voice_channel(label+': ...',category=category)
                set_settings({'stats.channel_'+key:channel.id},guild.id)
            await self.update_guild(guild)

    @stats_group.command(name='update')
    @commands.has_guild_permissions(administrator=True)
    async def force_update(self,ctx):
        async with self.lock:
            await self.update_guild(ctx.guild)
        await ctx.send('✅ Statistik dieses Servers aktualisiert.')

    @stats_group.command(name='info')
    @commands.has_guild_permissions(administrator=True)
    async def info(self,ctx):
        text='\n'.join(f'{key}: {get_setting("stats.channel_"+key,ctx.guild.id) or "nicht eingerichtet"}' for key in COUNTERS)
        await ctx.send(text,allowed_mentions=discord.AllowedMentions.none())

    async def cog_command_error(self,ctx,error):
        await ctx.send('Statistikaktion fehlgeschlagen. Administratorrechte und Bot-Recht „Kanäle verwalten“ prüfen.')


async def setup(bot):
    await bot.add_cog(ServerStats(bot))
