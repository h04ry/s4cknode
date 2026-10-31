import json
import asyncio
import discord
from discord.ext import commands
from config_store import SPECS, get_setting, set_settings
from guild_config import validate_guild_values

EDITABLE = {'bot.status_channel_id','twitch.channel_id','twitch.channels',
            'twitch.mention_everyone','github.channel_id','github.user','github.repo_filter'}


class ServerConfig(commands.Cog):
    def __init__(self,bot):
        self.bot=bot
        self.setup_lock=asyncio.Lock()

    @commands.group(name='server',invoke_without_command=True)
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def server(self,ctx):
        embed=discord.Embed(title='⚙️ Einstellungen für diesen Server',color=0x7C6AFF,
            description='Alle folgenden Einstellungen gelten nur hier. Kanalnamen als #Erwähnung oder Kanal-ID angeben.')
        embed.add_field(name='Meldungen einrichten',inline=False,value=
            '`!server set bot.status_channel_id #bot-status`\n'
            '`!server set twitch.channel_id #twitch`\n'
            '`!server set github.channel_id #github`\n'
            '`!server set github.repo_filter owner/repo`\n'
            '`!server set twitch.mention_everyone false`')
        embed.add_field(name='Weitere Funktionen',inline=False,value=
            '`!server setup` – fehlende Bot-Bereiche einrichten\n'
            '`!server info` – eigene Konfiguration\n`!server invite` – Bot einladen\n'
            '`!twitch add Name` / `!twitch del Name` / `!twitch list`\n'
            '`!radiopanel` – Radio-Bedienfeld im aktuellen Kanal\n'
            '`!stats setup` – Statistikkanäle einrichten oder reparieren\n'
            '`!server set <Schlüssel> aus` – Zielkanal/Repository deaktivieren')
        await ctx.send(embed=embed,allowed_mentions=discord.AllowedMentions.none())

    async def setup_guild(self,guild):
        async with self.setup_lock:
            return await self._setup_guild(guild)

    async def _setup_guild(self,guild):
        category=discord.utils.get(guild.categories,name='🤖 BOT')
        result={}
        for key,name in [('bot.status_channel_id','bot-status'),('twitch.channel_id','twitch'),
                         ('github.channel_id','github'),(None,'📻・radio')]:
            panel=self.bot.get_cog('RadioPanel')
            record=panel.record(guild.id) if key is None and panel else None
            channel=guild.get_channel(get_setting(key,guild.id)) if key else guild.get_channel(int(record[1])) if record else None
            if not isinstance(channel,discord.TextChannel):
                channel=discord.utils.get(guild.text_channels,name=name)
            if not channel:
                if not category:
                    category=await guild.create_category('🤖 BOT',reason='Bot-Bereiche für diesen Server einrichten')
                channel=await guild.create_text_channel(name,category=category,
                    overwrites={guild.default_role:discord.PermissionOverwrite(send_messages=False),
                        guild.me:discord.PermissionOverwrite(view_channel=True,send_messages=True,
                            embed_links=True,read_message_history=True)},reason='Bot-Bereich einrichten')
            if key:
                set_settings({key:channel.id},guild.id)
            elif panel:
                message=await panel.ensure_panel(channel)
                result['radio_url']=message.jump_url
            result[name]=str(channel.id)
        stats=self.bot.get_cog('ServerStats')
        if stats:
            await stats.ensure_guild(guild)
        return result

    @server.command(name='setup')
    @commands.has_guild_permissions(manage_guild=True)
    async def setup_server(self,ctx):
        await self.setup_guild(ctx.guild)
        await ctx.send('✅ Bot-Bereiche für diesen Server eingerichtet. Twitch-Accounts und GitHub-Quelle lassen sich mit `!server` einstellen. Vorhandene Kanäle wurden beibehalten.')

    @server.command(name='set')
    @commands.has_guild_permissions(manage_guild=True)
    async def set_value(self,ctx,key:str,*,value:str):
        if key not in EDITABLE:
            raise commands.BadArgument('Unbekannter oder nicht freigegebener Schlüssel. Hilfe: !server')
        kind=SPECS[key][0]
        if kind=='id':
            value=None if value.lower()=='aus' else value.strip('<#> ')
        elif kind=='bool':
            if value.lower() not in ('true','false'):
                raise commands.BadArgument('Bitte true oder false eingeben.')
            value=value.lower()=='true'
        elif kind=='names':
            value=value.replace(',',' ').split() if value.lower()!='aus' else []
        elif value.lower()=='aus':
            value=''
        values=validate_guild_values(ctx.guild,{key:value})
        set_settings(values,ctx.guild.id)
        await ctx.send(f'✅ `{key}` für diesen Server gespeichert.',allowed_mentions=discord.AllowedMentions.none())

    @server.command(name='info')
    @commands.has_guild_permissions(manage_guild=True)
    async def info(self,ctx):
        lines=[]
        for key in sorted(EDITABLE):
            value=get_setting(key,ctx.guild.id)
            lines.append(f'{key}: {json.dumps(value,ensure_ascii=False)}')
        text='\n'.join(lines)
        for offset in range(0,len(text),1900):
            await ctx.send('```\n'+text[offset:offset+1900]+'\n```',allowed_mentions=discord.AllowedMentions.none())

    @server.command(name='invite')
    @commands.has_guild_permissions(manage_guild=True)
    async def invite(self,ctx):
        permissions=discord.Permissions(view_channel=True,send_messages=True,embed_links=True,
            read_message_history=True,connect=True,speak=True,manage_channels=True,attach_files=True)
        url=discord.utils.oauth_url(self.bot.application_id,permissions=permissions,scopes=('bot','applications.commands'))
        await ctx.send(url)

    async def cog_command_error(self,ctx,error):
        original=getattr(error,'original',error)
        if isinstance(error,commands.MissingPermissions):
            text='Dafür brauchst du „Server verwalten“.'
        elif isinstance(original,(commands.BadArgument,ValueError)):
            text=str(original)
        else:
            text='Server-Konfiguration fehlgeschlagen. Hilfe: !server'
        await ctx.send(text,allowed_mentions=discord.AllowedMentions.none())


async def setup(bot):
    await bot.add_cog(ServerConfig(bot))
