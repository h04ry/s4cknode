import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import asyncio
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands
import cogs.radio_panel as rp


class Radio:
    def __init__(self, guild):
        self.guild = guild
        self.lock = asyncio.Lock()
        self.errors = {}
        self.saved = {'station': 'First Station', 'volume': 30}
        self.plays = []

    def state(self, guild):
        return dict(self.saved)

    def save(self, guild, **changes):
        self.saved.update(changes)

    async def volume(self, guild, value):
        if type(value) is not int or not 0 <= value <= 100:
            raise ValueError('Die Lautstärke muss zwischen 0 und 100 liegen.')
        self.save(guild.id, volume=value)

    async def play(self, guild, name):
        self.plays.append(name)
        self.save(guild.id, station=name)

    async def join(self, channel):
        self.guild.voice_client = NS(is_connected=lambda: True, is_playing=lambda: True,
            source=NS(stream=NS(title='A title')), channel=channel, disconnect=AsyncMock())


class Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / 'test.sqlite3'
        self.stations = [{'name': 'First Station', 'url': 'https://example.com/audio'}]
        @contextmanager
        def connection():
            db = sqlite3.connect(self.db)
            try:
                with db:
                    yield db
            finally:
                db.close()
        self.patches = [patch.object(rp, 'store', lambda: NS(connect=connection)),
                        patch.object(rp, 'get_setting', lambda k, guild_id=None: self.stations)]
        for p in self.patches:
            p.start()
        self.guild = NS(id=1, voice_client=None, me=NS())
        self.channel = MagicMock(spec=discord.VoiceChannel)
        self.channel.id = 10
        self.channel.name = 'Music'
        self.channel.members = []
        self.channel.guild = self.guild
        self.guild.get_channel = lambda channel: self.text if channel == 20 else None
        self.text = MagicMock(spec=discord.TextChannel)
        self.text.id = 20
        self.text.guild = self.guild
        self.message = NS(id=100, edit=AsyncMock(), jump_url='https://example.com/message')
        self.text.fetch_message = AsyncMock(return_value=self.message)
        self.text.send = AsyncMock(return_value=self.message)
        self.text.permissions_for.return_value = NS(view_channel=True, send_messages=True,
            embed_links=True, read_message_history=True)
        self.radio = Radio(self.guild)
        self.bot = commands.Bot(command_prefix='!', intents=discord.Intents.none())
        self.bot.get_cog = lambda name: self.radio if name == 'Radio' else None
        self.panel = rp.RadioPanel(self.bot)
        self.panel.write_record(1, 20, 100)

    async def asyncTearDown(self):
        for view in self.panel.views.values():
            view.stop()
        await self.bot.close()
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def interaction(self, channel=True, message_id=100):
        response = NS(is_done=MagicMock(return_value=False), send_message=AsyncMock(),
                      defer=AsyncMock(), send_modal=AsyncMock())
        async def defer(**kwargs):
            response.is_done.return_value = True
        response.defer.side_effect = defer
        return NS(guild=self.guild, guild_id=1, message=NS(id=message_id),
                  user=NS(voice=NS(channel=self.channel if channel else None)),
                  delete_original_response=AsyncMock(),
                  response=response, followup=NS(send=AsyncMock()))

    async def test_success_clears_acknowledgement_without_new_message(self):
        interaction = self.interaction()
        await self.panel.operate(interaction, 'volume', 45)
        interaction.delete_original_response.assert_awaited_once()
        interaction.followup.send.assert_not_awaited()
        interaction.response.send_message.assert_not_awaited()
        self.assertEqual(self.radio.saved['volume'], 45)

    async def test_error_stays_visible_without_deleting_panel(self):
        interaction = self.interaction(channel=False)
        await self.panel.operate(interaction, 'volume', 45)
        interaction.delete_original_response.assert_not_awaited()
        interaction.followup.send.assert_awaited_once()

    async def test_station_selection_before_join_uses_same_state(self):
        await self.panel.operate(self.interaction(), 'station', 'First Station')
        self.assertEqual(self.radio.plays, [])
        await self.panel.operate(self.interaction(), 'join')
        await self.panel.operate(self.interaction(), 'station', 'First Station')
        self.assertEqual(self.radio.plays, ['First Station'])
        self.assertTrue(self.guild.voice_client.is_connected())

    async def test_no_voice_and_stale_message_do_not_change_state(self):
        for interaction in (self.interaction(channel=False), self.interaction(message_id=99)):
            await self.panel.operate(interaction, 'volume', 90)
            self.assertTrue(interaction.followup.send.called)
        self.assertEqual(self.radio.saved['volume'], 30)

    async def test_wrong_voice_cannot_control_or_steal_listeners(self):
        other = NS(members=[NS(bot=False)], name='Other', id=11)
        self.guild.voice_client = NS(channel=other, is_connected=lambda: True)
        for action, value in [('volume', 80), ('station', 'First Station'), ('stop', None), ('join', None)]:
            interaction = self.interaction()
            await self.panel.operate(interaction, action, value)
            self.assertIn('Sprachkanal des Bots', interaction.followup.send.call_args.args[0])
        self.assertEqual(self.radio.saved['volume'], 30)
        self.assertEqual(self.radio.plays, [])

    async def test_volume_bounds_and_simultaneous_relative_clicks(self):
        self.radio.saved['volume'] = 95
        await self.panel.operate(self.interaction(), 'delta', 10)
        self.assertEqual(self.radio.saved['volume'], 100)
        self.radio.saved['volume'] = 5
        await self.panel.operate(self.interaction(), 'delta', -10)
        self.assertEqual(self.radio.saved['volume'], 0)
        await self.panel.operate(self.interaction(), 'volume', 101)
        self.assertEqual(self.radio.saved['volume'], 0)
        await asyncio.gather(*(self.panel.operate(self.interaction(), 'delta', 10) for _ in range(3)))
        self.assertEqual(self.radio.saved['volume'], 30)

    async def test_permission_recheck_after_waiting_for_radio_lock(self):
        interaction = self.interaction()
        await self.radio.lock.acquire()
        task = asyncio.create_task(self.panel.operate(interaction, 'volume', 70))
        await asyncio.sleep(0)
        interaction.user.voice.channel = None
        self.radio.lock.release()
        await task
        self.assertEqual(self.radio.saved['volume'], 30)

    async def test_modal_rechecks_voice_and_parses_values(self):
        modal = rp.VolumeModal(self.panel, 100, 30)
        modal.value._value = '42'
        interaction = self.interaction()
        interaction.message = None
        await modal.on_submit(interaction)
        self.assertEqual(self.radio.saved['volume'], 42)
        interaction = self.interaction(channel=False)
        interaction.message = None
        modal.value._value = '60'
        await modal.on_submit(interaction)
        self.assertEqual(self.radio.saved['volume'], 42)
        modal.value._value = 'abc'
        interaction = self.interaction()
        await modal.on_submit(interaction)
        interaction.response.send_message.assert_awaited_once()

    async def test_100_stations_pagination_and_web_removal(self):
        self.stations[:] = [{'name': f'Station {i}', 'url': 'https://example.com'} for i in range(100)]
        await self.panel.turn_page(self.interaction(), 1)
        self.assertEqual(self.panel.record(1)[3], 1)
        dropdown = next(c for c in self.panel.views[1].children if isinstance(c, rp.StationSelect))
        self.assertEqual(dropdown.options[0].value, 'Station 25')
        self.assertEqual(len(dropdown.options), 25)
        self.stations[:] = []
        await self.panel.refresh(self.guild)
        dropdown = next(c for c in self.panel.views[1].children if isinstance(c, rp.StationSelect))
        self.assertTrue(dropdown.disabled)
        await self.panel.operate(self.interaction(), 'station', 'Station 25')
        self.assertEqual(self.radio.plays, [])

    async def test_refresh_only_changed_state_and_external_updates(self):
        await self.panel.refresh(self.guild)
        self.message.edit.assert_awaited_once()
        await self.panel.refresh(self.guild)
        self.message.edit.assert_awaited_once()
        self.radio.save(1, volume=61)
        await self.panel.refresh(self.guild)
        self.assertEqual(self.message.edit.await_count, 2)
        self.assertIn('61 %', str(self.message.edit.call_args.kwargs['embed'].to_dict()))
        self.assertTrue(self.panel.views[1].is_persistent())
        registered = self.bot._connection._view_store._views[100]
        self.assertTrue(all(item.view is self.panel.views[1] for item in registered.values()))

    async def test_setup_reuses_existing_panel_and_repairs_missing_message(self):
        await self.panel.ensure_panel(self.text)
        self.text.send.assert_not_awaited()
        self.text.fetch_message.side_effect = discord.NotFound(NS(status=404, reason='missing'), 'gone')
        await self.panel.ensure_panel(self.text)
        self.text.send.assert_awaited_once()

    async def test_restart_registers_persistent_buttons_from_sqlite(self):
        restarted = rp.RadioPanel(self.bot)
        with patch.object(rp.RadioPanel.watch, 'start'):
            await restarted.cog_load()
        self.assertEqual(len(restarted.views), 1)
        self.assertTrue(restarted.views[1].is_persistent())
        custom_ids = {c.custom_id for c in restarted.views[1].children}
        self.assertIn('s4cknode:radio:join', custom_ids)
        restarted.check_panel(self.interaction())
        await restarted.cog_unload()


if __name__ == '__main__':
    unittest.main(verbosity=2)

