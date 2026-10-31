import discord
from discord.ext import commands
from discord import app_commands

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Ein Slash-Command Test
    @app_commands.command(name="ping", description="Prüft die Latenz des Bots")
    async def ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f'🏓 Pong! ({latency}ms)')

async def setup(bot):
    await bot.add_cog(General(bot))