import discord
from discord.ext import commands


class RadioHelp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='radio')
    @commands.guild_only()
    async def radio_help(self, ctx):
        embed = discord.Embed(
            title='📻 Radio – Befehle und Beispiele',
            description='Befehle als normale Nachricht in einen Textkanal schreiben. '
                        'Für die Wiedergabe zuerst einem Sprachkanal beitreten.',
            color=0x7C6AFF,
        )
        entries = [
            ('!radio', 'Zeigt diese Hilfe.\n**Eingabe:** `!radio`'),
            ('Radio per Klick', 'Im Radio-Bedienfeld Sender auswählen, beitreten, Lautstärke ändern und stoppen.\n**Einrichtung für Serververwalter:** `!radiopanel` im gewünschten Textkanal. Ein vorhandenes Bedienfeld wird wiederverwendet.'),
            ('!radiolist', 'Zeigt alle verfügbaren Sender.\n**Eingabe:** `!radiolist`'),
            ('!radiotitel', 'Zeigt Interpret und Titel, sofern der Sender diese mitsendet.\n**Eingabe:** `!radiotitel`'),
            ('!radiojoin', 'Der Bot kommt in deinen Sprachkanal und startet den zuletzt gewählten Sender.\n**Eingabe:** `!radiojoin`'),
            ('!radiosender <Sendername>', 'Wählt einen Sender aus der Senderliste. Den vollständigen Namen eingeben, auch mit Leerzeichen.\n**Beispiel:** `!radiosender Radio Paradise`'),
            ('!radiolautstärke <0–100>', 'Stellt die Lautstärke ein: 0 = stumm, 100 = volle Lautstärke.\n**Beispiel:** `!radiolautstärke 50`\n**Ohne Umlaut:** `!radiolautstaerke 50`'),
            ('!radiostop', 'Stoppt das Radio und lässt den Bot den Sprachkanal verlassen.\n**Eingabe:** `!radiostop`'),
        ]
        for name, value in entries:
            embed.add_field(name=name, value=value, inline=False)
        embed.add_field(
            name='So startest du',
            value='1. Sprachkanal betreten.\n2. `!radiolist`\n3. `!radiojoin`\n'
                  '4. `!radiosender Radio Paradise`\n5. `!radiolautstärke 30`',
            inline=False,
        )
        embed.set_footer(text='Platzhalter <…> ersetzen. Ohne menschliche Zuhörer verlässt der Bot nach 2 Minuten den Sprachkanal; Rückkehr bricht den Timer ab.')
        if self.bot.get_cog('Radio') is None:
            embed.description += '\n\n⚠️ Das Radio-Modul ist derzeit nicht geladen.'
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot):
    await bot.add_cog(RadioHelp(bot))
