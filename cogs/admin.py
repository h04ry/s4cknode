import discord
from discord.ext import commands

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="load")
    @commands.is_owner() # Nur du kannst das!
    async def load(self, ctx, extension):
        await self.bot.load_extension(f'cogs.{extension}')
        await ctx.send(f'✅ Modul `{extension}` geladen.')

    @commands.command(name="unload")
    @commands.is_owner()
    async def unload(self, ctx, extension):
        await self.bot.unload_extension(f'cogs.{extension}')
        await ctx.send(f'⏏️ Modul `{extension}` entladen.')

async def setup(bot):
    await bot.add_cog(Admin(bot))