"""Persistent Discord controls sharing the existing Radio cog and SQLite state."""
import asyncio
import json
import logging

import discord
from discord.ext import commands, tasks
from config_store import get_setting, store

log = logging.getLogger(__name__)
PAGE_SIZE = 25


async def feedback(interaction, text):
    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True,
                                        allowed_mentions=discord.AllowedMentions.none())
    else:
        await interaction.response.send_message(text, ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())


class StationSelect(discord.ui.Select):
    def __init__(self, panel, stations):
        self.panel = panel
        # Values use names, not list indices: a web edit cannot select another station by accident.
        options = [discord.SelectOption(label=s['name'], value=s['name']) for s in stations]
        super().__init__(placeholder='Radiosender auswählen …', options=options or [
            discord.SelectOption(label='Keine Sender eingerichtet', value='')],
            disabled=not stations, custom_id='s4cknode:radio:station', row=0)

    async def callback(self, interaction):
        await self.panel.cog.operate(interaction, 'station', self.values[0])


class VolumeModal(discord.ui.Modal, title='Radio-Lautstärke'):
    value = discord.ui.TextInput(label='Lautstärke von 0 bis 100', min_length=1,
                                 max_length=3, placeholder='Zum Beispiel: 30')

    def __init__(self, cog, message_id, current):
        super().__init__(timeout=180)
        self.cog = cog
        self.message_id = message_id
        self.value.default = str(current)

    async def on_submit(self, interaction):
        try:
            value = int(str(self.value).strip())
        except ValueError:
            await feedback(interaction, 'Bitte eine ganze Zahl von 0 bis 100 eingeben.')
            return
        await self.cog.operate(interaction, 'volume', value, message_id=self.message_id)

    async def on_error(self, interaction, error):
        log.exception('Radio volume dialog failed', exc_info=error)
        await feedback(interaction, 'Die Lautstärke konnte nicht übernommen werden. Bitte erneut versuchen.')


class RadioView(discord.ui.View):
    def __init__(self, cog, stations, page=0):
        super().__init__(timeout=None)
        self.cog = cog
        self.add_item(StationSelect(self, stations[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]))
        pages = max(1, (len(stations) + PAGE_SIZE - 1) // PAGE_SIZE)
        self.previous.disabled = page == 0
        self.next_page.disabled = page + 1 >= pages
        if pages == 1:
            self.remove_item(self.previous)
            self.remove_item(self.next_page)

    async def interaction_check(self, interaction):
        try:
            self.cog.check_panel(interaction)
            return True
        except ValueError as exc:
            await feedback(interaction, str(exc))
            return False

    async def on_error(self, interaction, error, item):
        log.exception('Radio panel callback failed', exc_info=error)
        await feedback(interaction, 'Die Aktion ist fehlgeschlagen. Bitte erneut versuchen.')

    @discord.ui.button(label='Vorherige Sender', custom_id='s4cknode:radio:previous', row=1)
    async def previous(self, interaction, button):
        await self.cog.turn_page(interaction, -1)

    @discord.ui.button(label='Weitere Sender', custom_id='s4cknode:radio:next', row=1)
    async def next_page(self, interaction, button):
        await self.cog.turn_page(interaction, 1)

    @discord.ui.button(label='In meinen Voicekanal kommen', emoji='▶️',
                       style=discord.ButtonStyle.success, custom_id='s4cknode:radio:join', row=2)
    async def join(self, interaction, button):
        await self.cog.operate(interaction, 'join')

    @discord.ui.button(label='Stoppen & verlassen', emoji='⏹️',
                       style=discord.ButtonStyle.danger, custom_id='s4cknode:radio:stop', row=2)
    async def stop_radio(self, interaction, button):
        await self.cog.operate(interaction, 'stop')

    @discord.ui.button(label='−10 %', emoji='🔉', custom_id='s4cknode:radio:quieter', row=3)
    async def quieter(self, interaction, button):
        await self.cog.operate(interaction, 'delta', -10)

    @discord.ui.button(label='+10 %', emoji='🔊', custom_id='s4cknode:radio:louder', row=3)
    async def louder(self, interaction, button):
        await self.cog.operate(interaction, 'delta', 10)

    @discord.ui.button(label='Wert eingeben', emoji='🎚️', custom_id='s4cknode:radio:volume', row=3)
    async def exact_volume(self, interaction, button):
        try:
            radio, channel = self.cog.authorize(interaction, 'volume')
            await interaction.response.send_modal(VolumeModal(
                self.cog, interaction.message.id, radio.state(interaction.guild_id)['volume']))
        except ValueError as exc:
            await feedback(interaction, str(exc))


class RadioPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lock = asyncio.Lock()
        self.views = {}
        self.signatures = {}
        self.messages = {}
        with store().connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS radio_panels ('
                       'guild TEXT PRIMARY KEY, channel TEXT NOT NULL, '
                       'message TEXT NOT NULL, page INTEGER NOT NULL DEFAULT 0)')

    def records(self):
        with store().connect() as db:
            return list(db.execute('SELECT guild,channel,message,page FROM radio_panels'))

    def record(self, guild_id):
        return next((r for r in self.records() if r[0] == str(guild_id)), None)

    def write_record(self, guild_id, channel_id, message_id, page=0):
        with store().connect() as db:
            db.execute('INSERT INTO radio_panels VALUES (?,?,?,?) ON CONFLICT(guild) '
                       'DO UPDATE SET channel=excluded.channel,message=excluded.message,page=excluded.page',
                       (str(guild_id), str(channel_id), str(message_id), page))

    async def cog_load(self):
        for guild, channel, message, page in self.records():
            view = self.make_view(int(guild), page)
            self.bot.add_view(view, message_id=int(message))
            self.views[int(guild)] = view
        self.watch.start()

    async def cog_unload(self):
        task = self.watch.get_task()
        self.watch.cancel()
        if task:
            await asyncio.gather(task, return_exceptions=True)
        for view in self.views.values():
            view.stop()
        self.views.clear()
        self.messages.clear()

    def make_view(self, guild_id, page):
        stations = get_setting('radio.stations', guild_id)
        last_page = max(0, (len(stations) - 1) // PAGE_SIZE)
        return RadioView(self, stations, min(max(0, page), last_page))

    def check_panel(self, interaction, message_id=None):
        record = self.record(interaction.guild_id)
        origin = message_id or getattr(interaction.message, 'id', None)
        if not interaction.guild or not record or str(origin) != record[2]:
            raise ValueError('Dieses Bedienfeld ist nicht mehr aktiv. Bitte das aktuelle Radio-Bedienfeld verwenden.')
        return record

    def authorize(self, interaction, action, message_id=None):
        self.check_panel(interaction, message_id)
        radio = self.bot.get_cog('Radio')
        if radio is None:
            raise ValueError('Das Radio-Modul ist gerade nicht geladen.')
        channel = getattr(getattr(interaction.user, 'voice', None), 'channel', None)
        if not isinstance(channel, discord.VoiceChannel):
            raise ValueError('Bitte zuerst einem normalen Sprachkanal beitreten.')
        vc = interaction.guild.voice_client
        if vc and vc.is_connected() and vc.channel != channel:
            # Never pull the radio away from listeners in another voice channel.
            if action != 'join' or any(not m.bot for m in vc.channel.members):
                raise ValueError('Bitte dem Sprachkanal des Bots beitreten, um das Radio zu steuern.')
        return radio, channel

    async def operate(self, interaction, action, value=None, message_id=None):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            radio, channel = self.authorize(interaction, action, message_id)
            async with radio.lock:
                # Voice membership can change while another operation holds the lock.
                radio, channel = self.authorize(interaction, action, message_id)
                guild = interaction.guild
                if action == 'join':
                    await radio.join(channel)
                elif action == 'station':
                    station = next((s for s in get_setting('radio.stations', interaction.guild_id) if s['name'] == value), None)
                    if not station:
                        raise ValueError('Dieser Sender wurde entfernt. Bitte einen aktuellen Sender auswählen.')
                    vc = guild.voice_client
                    if vc and vc.is_connected():
                        await radio.play(guild, station['name'])
                    else:
                        radio.save(guild.id, station=station['name'])
                elif action in ('delta', 'volume'):
                    target = (max(0, min(100, radio.state(guild.id)['volume'] + value))
                              if action == 'delta' else value)
                    await radio.volume(guild, target)
                elif action == 'stop':
                    if guild.voice_client:
                        await guild.voice_client.disconnect(force=True)
                else:
                    raise ValueError('Unbekannte Radioaktion.')
            # The deferred response is explicitly ephemeral/thinking, so deleting it
            # removes only this click's acknowledgement, never the public panel.
            # Keep the channel clear instead of accumulating private confirmations.
            try:
                await interaction.delete_original_response()
            except discord.NotFound:
                pass
            except discord.HTTPException:
                log.warning('Could not clear the radio interaction acknowledgement')
            try:
                await self.refresh(interaction.guild)
            except Exception:
                # Audio already changed successfully; the periodic watcher retries the display.
                log.exception('Radio changed, but panel update failed')
        except ValueError as exc:
            await feedback(interaction, str(exc))
        except Exception:
            log.exception('Radio panel operation failed: %s', action)
            await feedback(interaction, 'Voice-Verbindung oder Wiedergabe fehlgeschlagen. Bitte Bot-Rechte und Stream prüfen.')

    async def turn_page(self, interaction, delta):
        await interaction.response.defer()
        async with self.lock:
            guild, channel, message, page = self.check_panel(interaction)
            last = max(0, (len(get_setting('radio.stations', interaction.guild_id)) - 1) // PAGE_SIZE)
            self.write_record(guild, channel, message, max(0, min(last, page + delta)))
            await self._refresh(interaction.guild)

    def render(self, guild, page):
        radio = self.bot.get_cog('Radio')
        vc = guild.voice_client
        connected = bool(vc and vc.is_connected())
        playing = bool(connected and vc.is_playing())
        state = radio.state(guild.id) if radio else {'station': '—', 'volume': 0}
        title = getattr(getattr(getattr(vc, 'source', None), 'stream', None), 'title', '')
        embed = discord.Embed(title='📻 S4CKNode Radio', color=0x7C6AFF,
            description=('Sender auswählen und den Bot per Knopfdruck in deinen Sprachkanal holen. '
                         'Zum Steuern bitte dem Sprachkanal des Bots beitreten.'))
        embed.add_field(name='Sender', value=discord.utils.escape_markdown(state['station'] or 'Keiner')[:1024])
        embed.add_field(name='Lautstärke', value=f"{state['volume']} %")
        embed.add_field(name='Status', value=('Radio-Modul nicht geladen' if not radio else
            ('Spielt' if playing else 'Verbunden · keine Wiedergabe') if connected else 'Nicht verbunden'))
        embed.add_field(name='Voicekanal', value=discord.utils.escape_markdown(vc.channel.name) if connected else '—')
        embed.add_field(name='Aktueller Titel', inline=False,
            value=discord.utils.escape_markdown(title)[:1024] if playing and title else
                  ('Der Sender liefert gerade keine Titelinformationen.' if playing else '—'))
        if radio and radio.errors.get(guild.id):
            embed.add_field(name='Hinweis', value=radio.errors[guild.id][:1024], inline=False)
        pages = max(1, (len(get_setting('radio.stations', guild.id)) + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(page, pages - 1)
        embed.set_footer(text=f'Senderseite {page + 1}/{pages} · Ohne Zuhörer nach 2 Minuten verlassen · !radio zeigt die Befehle')
        view = self.make_view(guild.id, page)
        signature = json.dumps([embed.to_dict(), view.to_components()], sort_keys=True)
        return embed, view, signature

    async def refresh(self, guild):
        async with self.lock:
            await self._refresh(guild)

    async def _refresh(self, guild):
        record = self.record(guild.id)
        if not record:
            return
        embed, view, signature = self.render(guild, record[3])
        if self.signatures.get(guild.id) == signature:
            view.stop()
            return
        try:
            channel = guild.get_channel(int(record[1]))
            if not isinstance(channel, discord.TextChannel):
                view.stop()
                return
            message = self.messages.get(guild.id)
            if not message or message.id != int(record[2]):
                message = await channel.fetch_message(int(record[2]))
                self.messages[guild.id] = message
            await message.edit(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            view.stop()
            raise
        old = self.views.get(guild.id)
        if old:
            old.stop()
        # Message.edit registers the replacement; stop the old view before explicitly
        # re-registering, since both use the same stable component IDs.
        self.bot.add_view(view, message_id=message.id)
        self.views[guild.id] = view
        self.signatures[guild.id] = signature

    @tasks.loop(seconds=10)
    async def watch(self):
        for guild_id, channel, message, page in self.records():
            guild = self.bot.get_guild(int(guild_id))
            if guild:
                try:
                    await self.refresh(guild)
                except (discord.NotFound, discord.Forbidden):
                    # An admin can repair a deleted message with !radiopanel.
                    self.messages.pop(guild.id, None)
                except Exception:
                    log.exception('Could not update radio panel')

    @watch.before_loop
    async def before_watch(self):
        await self.bot.wait_until_ready()

    async def ensure_panel(self, channel):
        """Idempotent setup; retains a working existing panel on this guild."""
        async with self.lock:
            guild = channel.guild
            record = self.record(guild.id)
            if record:
                old_channel = guild.get_channel(int(record[1]))
                if isinstance(old_channel, discord.TextChannel):
                    try:
                        message = await old_channel.fetch_message(int(record[2]))
                    except discord.NotFound:
                        pass
                    else:
                        await self._refresh(guild)
                        return message
            permissions = channel.permissions_for(guild.me)
            if not all((permissions.view_channel, permissions.send_messages,
                        permissions.embed_links, permissions.read_message_history)):
                raise ValueError('Dem Bot fehlen Kanal anzeigen, Nachrichten senden, Links einbetten oder Nachrichtenverlauf anzeigen.')
            embed, view, signature = self.render(guild, 0)
            try:
                message = await channel.send(embed=embed, view=view,
                    allowed_mentions=discord.AllowedMentions.none())
                self.write_record(guild.id, channel.id, message.id)
            except Exception:
                view.stop()
                raise
            old = self.views.get(guild.id)
            if old:
                old.stop()
            self.bot.add_view(view, message_id=message.id)
            self.views[guild.id] = view
            self.messages[guild.id] = message
            self.signatures[guild.id] = signature
            return message

    @commands.command(name='radiopanel')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def radiopanel(self, ctx):
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send('Bitte !radiopanel in einem normalen Textkanal eingeben.')
            return
        message = await self.ensure_panel(ctx.channel)
        await ctx.send(f'📻 Radio-Bedienfeld: {message.jump_url}',
                       allowed_mentions=discord.AllowedMentions.none())

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            text = 'Zum Einrichten des Bedienfelds brauchst du die Berechtigung „Server verwalten“.'
        elif isinstance(error, commands.NoPrivateMessage):
            text = 'Das Radio-Bedienfeld funktioniert nur auf einem Discord-Server.'
        else:
            log.error('Radio panel setup failed: %s', type(error).__name__)
            text = 'Das Bedienfeld konnte nicht eingerichtet werden. Bitte die Bot-Rechte im Kanal prüfen.'
        await ctx.send(text)


async def setup(bot):
    await bot.add_cog(RadioPanel(bot))
