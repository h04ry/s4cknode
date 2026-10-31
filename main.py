from config_store import get_setting, store, CURRENT_GUILD
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / '.runtime/radio-deps'))
import discord
from guild_config import migrate_legacy_settings
import os
from pathlib import Path
from runtime_control import ModuleControl
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
TOKEN = os.getenv('DISCORD_TOKEN')

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=discord.Intents.all(),
            help_command=None
        )
        self.module_control = ModuleControl(self, Path(__file__).resolve().parent)

    async def setup_hook(self):
        await migrate_legacy_settings(self)
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f'Modul geladen: {filename}')
                except Exception as e:
                    print(f'Fehler beim Laden von {filename}: {e}')
        await self.tree.sync()
        await self.module_control.start()

    async def close(self):
        await self.module_control.close()
        await super().close()

    async def on_ready(self):
        store().sync_guilds(self.guilds)
        print(f'Eingeloggt als {self.user}; {len(self.guilds)} Server')
        for guild in self.guilds:
            channel = guild.get_channel(get_setting('bot.status_channel_id', guild.id))
            if channel:
                try:
                    await channel.send('🚀 **Bot ist online und bereit!**', allowed_mentions=discord.AllowedMentions.none())
                except discord.HTTPException:
                    pass

    async def on_guild_join(self, guild):
        store().sync_guilds(self.guilds)

    async def on_guild_remove(self, guild):
        store().sync_guilds(self.guilds)

bot = MyBot()

@bot.before_invoke
async def select_command_guild(ctx):
    CURRENT_GUILD.set(ctx.guild.id if ctx.guild else None)


# Hilfsfunktion für die Berechtigungsprüfung (Owner ODER Admin)
async def is_admin_or_owner(ctx):
    return await bot.is_owner(ctx.author)

@bot.command(name="restart")
@commands.guild_only()
@commands.check(is_admin_or_owner)
async def restart(ctx):
    if ctx.channel.id == get_setting("bot.status_channel_id", ctx.guild.id):
        await ctx.send("🔄 **Neustart wird ausgeführt...**")
        print(f"Bot wird durch !restart von {ctx.author} beendet.")
        
        # Erst die Verbindung zu Discord kappen
        await bot.close()
        
        # Dann den Python-Prozess komplett killen
        # (Dein Start-Skript oder Service sollte ihn dann automatisch neu starten)
        sys.exit() 
    else:
        await ctx.send(f"❌ Dieser Befehl ist hier nicht freigegeben. Statuskanal: {get_setting('bot.status_channel_id', ctx.guild.id)}")

bot.run(TOKEN)
