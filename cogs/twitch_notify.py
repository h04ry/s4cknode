import asyncio
import json
import datetime
import logging
import os
import aiohttp
import discord
from discord.ext import commands,tasks
from config_store import get_setting,store

logger=logging.getLogger(__name__)


class TwitchNotify(commands.Cog):
    def __init__(self,bot):
        self.bot=bot
        self.client_id=os.getenv('TWITCH_CLIENT_ID')
        self.client_secret=os.getenv('TWITCH_CLIENT_SECRET')
        self._token=None
        self._token_expires_at=None
        self.check_twitch.start()

    async def cog_unload(self):
        task=self.check_twitch.get_task()
        self.check_twitch.cancel()
        if task:
            await asyncio.gather(task,return_exceptions=True)

    def state(self,guild_id,channel_id,login):
        with store().connect() as db:
            row=db.execute('SELECT state FROM twitch_delivery WHERE guild=? AND channel=? AND login=?',
                (str(guild_id),str(channel_id),login)).fetchone()
        return json.loads(row[0]) if row else {'is_online':False,'msg_id':None,'last_game':'','start_time':None,'stream_id':None}

    def save_state(self,guild_id,channel_id,login,state):
        with store().connect() as db:
            db.execute('INSERT INTO twitch_delivery VALUES (?,?,?,?) ON CONFLICT(guild,channel,login) DO UPDATE SET state=excluded.state',
                (str(guild_id),str(channel_id),login,json.dumps(state)))

    async def get_twitch_token(self) -> str | None:
        now = datetime.datetime.now()
        if self._token and self._token_expires_at and now < self._token_expires_at:
            return self._token

        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, params=params) as resp:
                    resp.raise_for_status()
                    data = await resp.json()

            self._token = data.get("access_token")
            expires_in = data.get("expires_in", 3600)
            self._token_expires_at = now + datetime.timedelta(seconds=expires_in - 60)
            logger.info("Neuer Twitch-Token geholt (gültig für %ds).", expires_in)
            return self._token

        except Exception as e:
            logger.error("Fehler beim Abrufen des Twitch-Tokens: %s", type(e).__name__)
            return None

    async def get_game_box_art(
        self, session: aiohttp.ClientSession, headers: dict, game_id: str
    ) -> str | None:
        """Holt das Box-Art Cover-Bild der Kategorie von der Twitch API."""
        if not game_id:
            return None
        try:
            url = f"https://api.twitch.tv/helix/games?id={game_id}"
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                games = data.get("data", [])
                if not games:
                    return None
                # Twitch Cover-Format: 144x192 (3:4)
                box_art = games[0]["box_art_url"]
                return box_art.replace("{width}", "144").replace("{height}", "192")
        except Exception as e:
            logger.warning("Fehler beim Abrufen des Game-Covers: %s", e)
            return None

    def create_embed(
        self,
        stream_info: dict,
        start_time: datetime.datetime,
        box_art_url: str | None = None,
    ) -> discord.Embed:
        """Erstellt das formatierte Embed für den Stream-Alert."""
        name    = stream_info["user_name"]
        game    = stream_info["game_name"] or "Unbekannt"
        title   = stream_info["title"] or "Kein Titel"
        viewers = stream_info["viewer_count"]
        login   = stream_info["user_login"]

        embed = discord.Embed(
            title=title,
            url=f"https://twitch.tv/{login}",
            color=0x6441A5,
            timestamp=start_time,
        )
        embed.set_author(
            name=f"{name} ist live auf Twitch!",
            icon_url="https://pngimg.com/uploads/twitch/twitch_PNG48.png",
        )
        embed.add_field(name="🕹️ Kategorie", value=game, inline=True)
        embed.add_field(name="👥 Zuschauer", value=f"{viewers:,}", inline=True)

        # Kategorie-Cover als Thumbnail rechts oben
        if box_art_url:
            embed.set_thumbnail(url=box_art_url)

        # Stream-Screenshot groß unten (Cache-Buster verhindert Discord-Caching)
        thumb = (
            stream_info["thumbnail_url"]
            .replace("{width}", "1280")
            .replace("{height}", "720")
        )
        embed.set_image(url=f"{thumb}?t={int(datetime.datetime.now().timestamp())}")
        embed.set_footer(text="Stream gestartet")
        return embed


    async def deliver(self,session,headers,guild,channel,login,stream):
        cache=self.state(guild.id,channel.id,login)
        if stream:
            started=datetime.datetime.fromisoformat(stream['started_at'].replace('Z','+00:00'))
            box=await self.get_game_box_art(session,headers,stream.get('game_id',''))
            embed=self.create_embed(stream,started,box)
            mention=get_setting('twitch.mention_everyone',guild.id)
            if not cache['is_online'] or (cache.get('stream_id') and cache['stream_id']!=stream['id']):
                msg=await channel.send(content=f"🔴 **{discord.utils.escape_markdown(stream['user_name'])}** ist jetzt live!"+(' @everyone' if mention else ''),
                    embed=embed,allowed_mentions=discord.AllowedMentions(everyone=mention,users=False,roles=False))
                cache={'is_online':True,'msg_id':msg.id,'last_game':stream['game_name'],
                       'start_time':started.isoformat(),'stream_id':stream['id']}
                self.save_state(guild.id,channel.id,login,cache)
            elif stream['game_name']!=cache['last_game']:
                try:
                    msg=await channel.fetch_message(cache['msg_id'])
                    await msg.edit(embed=embed,allowed_mentions=discord.AllowedMentions.none())
                except discord.NotFound:
                    msg=await channel.send(content=f'🔴 **{login}** ist noch live!',embed=embed,
                        allowed_mentions=discord.AllowedMentions.none())
                cache.update(msg_id=msg.id,last_game=stream['game_name'],stream_id=stream['id'])
                self.save_state(guild.id,channel.id,login,cache)
        elif cache['is_online']:
            duration=''
            if cache.get('start_time'):
                start=datetime.datetime.fromisoformat(cache['start_time'])
                elapsed=max(0,int((datetime.datetime.now(datetime.timezone.utc)-start).total_seconds()))
                hours,remainder=divmod(elapsed,3600)
                duration=f' (Dauer: {hours}h {remainder//60:02d}m)'
            await channel.send(f'🏁 **{login}** hat den Stream beendet.{duration}',allowed_mentions=discord.AllowedMentions.none())
            self.save_state(guild.id,channel.id,login,{'is_online':False,'msg_id':None,'last_game':'','start_time':None,'stream_id':None})

    @tasks.loop(minutes=2)
    async def check_twitch(self):
        if not self.client_id or not self.client_secret:
            return
        token=await self.get_twitch_token()
        if not token:
            return
        headers={'Client-ID':self.client_id,'Authorization':f'Bearer {token}'}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            for guild in list(self.bot.guilds):
                channel=guild.get_channel(get_setting('twitch.channel_id',guild.id))
                names=get_setting('twitch.channels',guild.id)
                if not isinstance(channel,discord.TextChannel) or not names:
                    continue
                try:
                    async with session.get('https://api.twitch.tv/helix/streams',params=[('user_login',n) for n in names],headers=headers) as response:
                        if response.status!=200:
                            logger.warning('Twitch HTTP %s',response.status)
                            continue
                        active={s['user_login'].lower():s for s in (await response.json()).get('data',[])}
                    for login in names:
                        try:
                            await self.deliver(session,headers,guild,channel,login,active.get(login))
                        except Exception as exc:
                            logger.warning('Twitch-Zustellung fehlgeschlagen: %s',type(exc).__name__)
                except Exception as exc:
                    logger.warning('Twitch-Abfrage für einen Server fehlgeschlagen: %s',type(exc).__name__)

    @check_twitch.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    @commands.group(name='twitch',invoke_without_command=True)
    @commands.guild_only()
    async def twitch_group(self,ctx):
        await ctx.send('`!twitch list` – eigene Liste; Serververwalter: `!twitch add Name`, `!twitch del Name`. Zielkanal über `!server` einrichten.')

    @twitch_group.command(name='add')
    @commands.has_guild_permissions(manage_guild=True)
    async def add_channel(self,ctx,name:str):
        store().update_names('twitch.channels',name.lower(),True,ctx.guild.id)
        await ctx.send('✅ Twitch-Account für diesen Server gespeichert.')

    @twitch_group.command(name='del')
    @commands.has_guild_permissions(manage_guild=True)
    async def del_channel(self,ctx,name:str):
        store().update_names('twitch.channels',name.lower(),False,ctx.guild.id)
        await ctx.send('✅ Twitch-Account aus der Liste dieses Servers entfernt.')

    @twitch_group.command(name='list')
    async def list_channels(self,ctx):
        names=get_setting('twitch.channels',ctx.guild.id)
        text='\n'.join('• '+n for n in names) or 'Die Twitch-Liste dieses Servers ist leer.'
        for offset in range(0,len(text),1900):
            await ctx.send(text[offset:offset+1900],allowed_mentions=discord.AllowedMentions.none())

    async def cog_command_error(self,ctx,error):
        original=getattr(error,'original',error)
        text=str(original) if isinstance(original,ValueError) else 'Twitch-Befehl fehlgeschlagen. Für Listenänderungen brauchst du „Server verwalten“.'
        await ctx.send(text,allowed_mentions=discord.AllowedMentions.none())


async def setup(bot):
    await bot.add_cog(TwitchNotify(bot))
