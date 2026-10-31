import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import asyncio
import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest.mock import MagicMock,AsyncMock,patch
import discord
from discord.ext import commands
import config_store as cfg
import cogs.community as module


class Role:
    def __init__(self,role_id,permissions=None):
        self.id=role_id
        self.permissions=permissions or discord.Permissions.none()
        self.managed=False
    def is_default(self):return False
    def __ge__(self,other):return self.id>=other.id


class Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.old=cfg._store
        cfg._store=cfg.SettingsStore(Path(self.temp.name)/'test.sqlite3')
        self.bot=commands.Bot(command_prefix='!',intents=discord.Intents.none())
        self.cog=module.Community(self.bot)
        self.roles={'member':Role(1),**{key:Role(i+2) for i,key in enumerate(module.TOPICS)}}
        self.otherrole=Role(15)
        self.guild=NS(id=10,owner_id=900,me=NS(top_role=Role(100),guild_permissions=NS(manage_roles=True)))
        self.guild.get_role=lambda rid:next((r for r in self.roles.values() if r.id==rid),None)
        self.channel=NS(id=30,overwrites={})
        self.channel.overwrites_for=lambda member:discord.PermissionOverwrite(**dict(self.channel.overwrites.get(member,discord.PermissionOverwrite())))
        async def set_permissions(member,overwrite,**kwargs):
            if overwrite is None:self.channel.overwrites.pop(member,None)
            else:self.channel.overwrites[member]=overwrite
        self.channel.set_permissions=AsyncMock(side_effect=set_permissions)
        self.guild.get_channel=lambda cid:self.channel if cid==30 else NS(mention='#rollen')
        self.member=MagicMock()
        self.member.id=50;self.member.guild=self.guild;self.member.roles=[self.otherrole]
        self.member.bot=False;self.member.pending=False;self.member.guild_permissions=NS(administrator=False)
        async def add(*roles,**kwargs):self.member.roles.extend(r for r in roles if r not in self.member.roles)
        async def remove(*roles,**kwargs):self.member.roles=[r for r in self.member.roles if r not in roles]
        self.member.add_roles=AsyncMock(side_effect=add)
        self.member.remove_roles=AsyncMock(side_effect=remove)
        self.guild.fetch_member=AsyncMock(return_value=self.member)
        self.config={'version':'v1','roles':{k:str(r.id) for k,r in self.roles.items()},
                     'channels':{'topics':'31','welcome':'32','rules':'33'},
                     'rules_message':'40','topics_message':'41','gated_channels':['30']}
        self.cog.save_config(10,self.config)

    async def asyncTearDown(self):
        await self.cog.cog_unload()
        await self.bot.close()
        cfg._store=self.old
        self.temp.cleanup()

    def interaction(self,message=40,guild=None,values=None):
        response=NS(defer=AsyncMock(),is_done=lambda:True,send_message=AsyncMock())
        return NS(guild=guild or self.guild,guild_id=(guild or self.guild).id,user=NS(id=50),
                  message=NS(id=message),response=response,followup=NS(send=AsyncMock()),data={'values':values or []})

    def mark_accepted(self):
        with cfg.store().connect() as db:
            db.execute('INSERT OR REPLACE INTO community_acceptance(guild,user,version) VALUES (?,?,?)',('10','50','v1'))
        if self.roles['member'] not in self.member.roles:self.member.roles.append(self.roles['member'])

    async def test_accept_adds_only_member_and_restores_gate(self):
        await self.cog.sync_gate(self.member,self.config)
        self.assertFalse(self.channel.overwrites_for(self.member).view_channel)
        await self.cog.accept(self.interaction())
        self.member.add_roles.assert_awaited_once_with(self.roles['member'],reason='Serverregeln ausdrücklich bestätigt',atomic=True)
        self.assertIn(self.otherrole,self.member.roles)
        self.assertTrue(self.cog.accepted(10,50,'v1'))
        self.assertIsNone(self.channel.overwrites_for(self.member).view_channel)

    async def test_stale_message_and_other_server_cannot_assign_roles(self):
        await self.cog.accept(self.interaction(message=999))
        await self.cog.accept(self.interaction(guild=NS(id=11)))
        self.member.add_roles.assert_not_awaited()
        self.assertFalse(self.cog.accepted(10,50,'v1'))

    async def test_native_pending_is_not_bypassed(self):
        self.member.pending=True
        await self.cog.accept(self.interaction())
        self.member.add_roles.assert_not_awaited()

    async def test_role_grant_failure_does_not_record_acceptance(self):
        self.member.add_roles.side_effect=ValueError('role grant failed')
        await self.cog.accept(self.interaction())
        self.assertFalse(self.cog.accepted(10,50,'v1'))

    async def test_privileged_role_misconfiguration_is_rejected(self):
        self.roles['member'].permissions=discord.Permissions(administrator=True)
        await self.cog.accept(self.interaction())
        self.member.add_roles.assert_not_awaited()
        self.roles['member'].permissions=discord.Permissions.none()
        self.guild.me.top_role=Role(1)
        await self.cog.accept(self.interaction())
        self.member.add_roles.assert_not_awaited()

    async def test_topics_require_actual_rules_acceptance(self):
        self.member.roles.append(self.roles['member'])
        await self.cog.select_topics(self.interaction(message=41),['coding'])
        self.member.add_roles.assert_not_awaited()

    async def test_topics_only_change_opt_in_roles_and_preserve_colleague_and_member(self):
        self.mark_accepted()
        self.member.roles.append(self.roles['gaming'])
        await self.cog.select_topics(self.interaction(message=41),['coding','security'])
        self.assertIn(self.roles['coding'],self.member.roles)
        self.assertIn(self.roles['security'],self.member.roles)
        self.assertNotIn(self.roles['gaming'],self.member.roles)
        self.assertIn(self.roles['member'],self.member.roles)
        self.assertIn(self.otherrole,self.member.roles)
        self.member.add_roles.assert_awaited_once()

    async def test_staff_and_colleagues_cannot_self_assign(self):
        self.mark_accepted()
        for value in ('colleagues','administrator','moderator','member'):
            await self.cog.select_topics(self.interaction(message=41),[value])
        self.member.add_roles.assert_not_awaited()
        self.member.remove_roles.assert_not_awaited()

    async def test_clearing_topics_preserves_manual_roles(self):
        self.mark_accepted()
        self.member.roles.append(self.roles['gaming'])
        await self.cog.select_topics(self.interaction(message=41),[])
        self.assertIn(self.otherrole,self.member.roles)
        self.assertIn(self.roles['member'],self.member.roles)
        self.assertNotIn(self.roles['gaming'],self.member.roles)

    async def test_gate_survives_reload_and_preserves_other_permission_changes(self):
        self.channel.overwrites[self.member]=discord.PermissionOverwrite(send_messages=False)
        await self.cog.sync_gate(self.member,self.config)
        self.channel.overwrites[self.member].attach_files=False
        restarted=module.Community(self.bot)
        self.mark_accepted()
        await restarted.sync_gate(self.member,self.config)
        ow=self.channel.overwrites_for(self.member)
        self.assertIsNone(ow.view_channel)
        self.assertFalse(ow.send_messages)
        self.assertFalse(ow.attach_files)
        await restarted.cog_unload()

    async def test_concurrent_acceptance_is_serialized_and_not_duplicate(self):
        await asyncio.gather(self.cog.accept(self.interaction()),self.cog.accept(self.interaction()))
        self.member.add_roles.assert_awaited_once()

    async def test_persistent_views_register_from_database(self):
        self.cog.register_views()
        self.assertEqual(len(self.cog.views),2)
        self.assertTrue(all(view.is_persistent() for view in self.cog.views))
        restarted=module.Community(self.bot)
        restarted.register_views()
        self.assertEqual(len(restarted.views),2)
        await restarted.cog_unload()

    async def test_database_failure_rolls_back_new_role(self):
        with patch.object(self.cog,'remember_acceptance',side_effect=ValueError('Speicherfehler')):
            await self.cog.accept(self.interaction())
        self.assertNotIn(self.roles['member'],self.member.roles)
        self.assertFalse(self.cog.accepted(10,50,'v1'))

    async def test_join_requires_new_confirmation_and_welcomes(self):
        self.mark_accepted()
        welcome=NS(send=AsyncMock())
        self.member.mention='<@50>'
        self.guild.get_channel=lambda cid:self.channel if cid==30 else welcome if cid==32 else NS(mention='#regeln')
        await self.cog.on_member_join(self.member)
        self.assertFalse(self.cog.accepted(10,50,'v1'))
        self.assertFalse(self.channel.overwrites_for(self.member).view_channel)
        welcome.send.assert_awaited_once()
        self.member.add_roles.assert_not_awaited()

    async def test_leave_removes_only_our_temporary_overwrite(self):
        self.channel.overwrites[self.member]=discord.PermissionOverwrite(send_messages=False)
        await self.cog.sync_gate(self.member,self.config)
        await self.cog.on_member_remove(self.member)
        ow=self.channel.overwrites_for(self.member)
        self.assertIsNone(ow.view_channel)
        self.assertFalse(ow.send_messages)
        with cfg.store().connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM community_gate_blocks').fetchone()[0],0)

    async def test_other_server_join_does_nothing(self):
        foreign=NS(guild=NS(id=20))
        await self.cog.on_member_join(foreign)
        self.member.add_roles.assert_not_awaited()

    async def test_bots_are_not_asked_to_accept_rules(self):
        self.member.bot=True
        await self.cog.on_member_join(self.member)
        self.channel.set_permissions.assert_not_awaited()
        self.member.add_roles.assert_not_awaited()


if __name__=='__main__':unittest.main(verbosity=2)
