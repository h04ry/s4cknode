"""Per-guild rules acceptance and optional topic roles; no automatic server provisioning."""
import asyncio
import json
import logging
import discord
from discord.ext import commands
from config_store import store

log=logging.getLogger(__name__)
TOPICS={'tech':'Tech & IT','internet':'Internet & Netzwerke','security':'IT-Security',
        'coding':'Coding','gaming':'Gaming'}
DANGEROUS=('administrator','manage_guild','manage_roles','manage_channels','kick_members',
           'ban_members','moderate_members','manage_messages','manage_webhooks','mention_everyone')


class RulesView(discord.ui.View):
    def __init__(self,cog):
        super().__init__(timeout=None)
        self.cog=cog

    @discord.ui.button(label='Regeln gelesen und akzeptiert',emoji='✅',
        style=discord.ButtonStyle.success,custom_id='s4cknode:community:accept:v1')
    async def accept(self,interaction,button):
        await self.cog.accept(interaction)


class TopicSelect(discord.ui.Select):
    def __init__(self,cog):
        self.cog=cog
        super().__init__(placeholder='Deine Themen auswählen (Mehrfachauswahl möglich)',
            custom_id='s4cknode:community:topics:v1',min_values=0,max_values=len(TOPICS),
            options=[discord.SelectOption(label=label,value=key) for key,label in TOPICS.items()])

    async def callback(self,interaction):
        # Read this interaction's data rather than a shared View's mutable selection.
        selected=list((interaction.data or {}).get('values',[]))
        await self.cog.select_topics(interaction,selected)


class TopicsView(discord.ui.View):
    def __init__(self,cog):
        super().__init__(timeout=None)
        self.add_item(TopicSelect(cog))


class Community(commands.Cog):
    def __init__(self,bot):
        self.bot=bot
        self.views=[]
        self.member_locks={}
        self.ready_task=None
        with store().connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS community_config (guild TEXT PRIMARY KEY,data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS community_acceptance (guild TEXT,user TEXT,version TEXT,accepted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(guild,user))')
            db.execute('CREATE TABLE IF NOT EXISTS community_gate_blocks (guild TEXT,user TEXT,channel TEXT,original TEXT,PRIMARY KEY(guild,user,channel))')

    def config(self,guild_id):
        with store().connect() as db:
            row=db.execute('SELECT data FROM community_config WHERE guild=?',(str(guild_id),)).fetchone()
        return json.loads(row[0]) if row else None

    def save_config(self,guild_id,data):
        with store().connect() as db:
            db.execute('INSERT INTO community_config VALUES (?,?) ON CONFLICT(guild) DO UPDATE SET data=excluded.data',
                       (str(guild_id),json.dumps(data)))

    def configurations(self):
        with store().connect() as db:
            return [(int(g),json.loads(d)) for g,d in db.execute('SELECT guild,data FROM community_config')]

    def accepted(self,guild_id,user_id,version):
        with store().connect() as db:
            row=db.execute('SELECT version FROM community_acceptance WHERE guild=? AND user=?',
                           (str(guild_id),str(user_id))).fetchone()
        return bool(row and row[0]==version)

    def remember_acceptance(self,guild_id,user_id,version):
        with store().connect() as db:
            db.execute('INSERT INTO community_acceptance(guild,user,version) VALUES (?,?,?) '
                'ON CONFLICT(guild,user) DO UPDATE SET version=excluded.version,accepted_at=CURRENT_TIMESTAMP',
                (str(guild_id),str(user_id),version))

    def lock_for(self,guild_id,user_id):
        return self.member_locks.setdefault((guild_id,user_id),asyncio.Lock())

    def verified(self,member,config):
        return (any(r.id==int(config['roles']['member']) for r in member.roles)
                and self.accepted(member.guild.id,member.id,config['version']))

    def checked_role(self,guild,config,key):
        role=guild.get_role(int(config['roles'][key]))
        if not role or role.managed or role.is_default() or any(getattr(role.permissions,p) for p in DANGEROUS):
            raise ValueError('Die Freischaltrolle ist nicht sicher eingerichtet. Bitte ein Teammitglied informieren.')
        if not guild.me.guild_permissions.manage_roles or role>=guild.me.top_role:
            raise ValueError('Der Bot benötigt „Rollen verwalten“ und muss über den freizugebenden Rollen stehen.')
        return role

    async def cog_load(self):
        self.register_views()
        self.ready_task=asyncio.create_task(self.reconcile_after_ready())

    async def cog_unload(self):
        if self.ready_task:
            self.ready_task.cancel()
            await asyncio.gather(self.ready_task,return_exceptions=True)
        for view in self.views:
            view.stop()
        self.views.clear()

    def register_views(self):
        for view in self.views:
            view.stop()
        self.views=[]
        for guild,config in self.configurations():
            for key,cls in [('rules_message',RulesView),('topics_message',TopicsView)]:
                if config.get(key):
                    view=cls(self)
                    self.bot.add_view(view,message_id=int(config[key]))
                    self.views.append(view)

    def check_origin(self,interaction,key):
        config=self.config(interaction.guild_id)
        if not interaction.guild or not config or str(getattr(interaction.message,'id',''))!=str(config.get(key,'')):
            raise ValueError('Dieses Bedienfeld ist nicht mehr aktiv.')
        return config

    async def fresh_member(self,interaction):
        member=await interaction.guild.fetch_member(interaction.user.id)
        if member.bot:
            raise ValueError('Die Freischaltung ist für menschliche Mitglieder vorgesehen.')
        if member.pending:
            raise ValueError('Bitte zuerst die von Discord angezeigte Mitgliedschaftsprüfung abschließen.')
        return member

    async def reply_error(self,interaction,error):
        text=str(error) if isinstance(error,ValueError) else 'Die Freischaltung ist fehlgeschlagen. Bitte erneut versuchen oder das Team informieren.'
        if not isinstance(error,ValueError):
            log.exception('Community interaction failed',exc_info=error)
        if interaction.response.is_done():
            await interaction.followup.send(text,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
        else:
            await interaction.response.send_message(text,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())

    async def accept(self,interaction):
        await interaction.response.defer(ephemeral=True,thinking=True)
        try:
            config=self.check_origin(interaction,'rules_message')
            async with self.lock_for(interaction.guild_id,interaction.user.id):
                member=await self.fresh_member(interaction)
                role=self.checked_role(interaction.guild,config,'member')
                newly_granted=not any(r.id==role.id for r in member.roles)
                if newly_granted:
                    await member.add_roles(role,reason='Serverregeln ausdrücklich bestätigt',atomic=True)
                try:
                    self.remember_acceptance(interaction.guild_id,member.id,config['version'])
                except Exception:
                    if newly_granted:
                        try:
                            await member.remove_roles(role,reason='Regelbestätigung konnte nicht gespeichert werden',atomic=True)
                        except Exception:
                            log.exception('Could not roll back unrecorded member role')
                    raise
                # Refresh after adding the role; preserve all other roles.
                member=await interaction.guild.fetch_member(member.id)
                await self.sync_gate(member,config)
            channel=interaction.guild.get_channel(int(config['channels']['topics']))
            hint=f' Wähle in {channel.mention} deine Themen, um weitere Bereiche zu sehen.' if channel else ''
            await interaction.followup.send('✅ Regeln bestätigt – du bist freigeschaltet.'+hint,
                ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
        except Exception as exc:
            await self.reply_error(interaction,exc)

    async def select_topics(self,interaction,selected):
        await interaction.response.defer(ephemeral=True,thinking=True)
        try:
            config=self.check_origin(interaction,'topics_message')
            if not isinstance(selected,list) or len(selected)!=len(set(selected)) or set(selected)-set(TOPICS):
                raise ValueError('Bitte nur die angebotenen Themen auswählen.')
            async with self.lock_for(interaction.guild_id,interaction.user.id):
                member=await self.fresh_member(interaction)
                if not self.verified(member,config):
                    raise ValueError('Bitte zuerst die Serverregeln bestätigen.')
                roles={key:self.checked_role(interaction.guild,config,key) for key in TOPICS}
                current={r.id for r in member.roles}
                add=[role for key,role in roles.items() if key in selected and role.id not in current]
                remove=[role for key,role in roles.items() if key not in selected and role.id in current]
                if add:
                    await member.add_roles(*add,reason='Themen selbst ausgewählt',atomic=True)
                if remove:
                    await member.remove_roles(*remove,reason='Themen selbst abgewählt',atomic=True)
            text=', '.join(TOPICS[key] for key in TOPICS if key in selected) or 'keine Themenbereiche'
            await interaction.followup.send('✅ Deine Themen: '+text+'. Allgemeine und manuell zugewiesene Rollen bleiben erhalten.',
                ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
        except Exception as exc:
            await self.reply_error(interaction,exc)

    async def sync_gate(self,member,config):
        # A member deny wins over a topic/colleague role allow. This prevents
        # manual role assignment from bypassing the required rules acceptance.
        if member.bot or member.guild_permissions.administrator or member.id==member.guild.owner_id:
            return
        verified=self.verified(member,config)
        for channel_id in config.get('gated_channels',[]):
            channel=member.guild.get_channel(int(channel_id))
            if not channel:
                continue
            with store().connect() as db:
                row=db.execute('SELECT original FROM community_gate_blocks WHERE guild=? AND user=? AND channel=?',
                    (str(member.guild.id),str(member.id),str(channel.id))).fetchone()
            if not verified:
                if row is None:
                    overwrite=channel.overwrites_for(member)
                    original={'exists':member in channel.overwrites,'allow':overwrite.pair()[0].value,'deny':overwrite.pair()[1].value}
                    with store().connect() as db:
                        db.execute('INSERT OR IGNORE INTO community_gate_blocks VALUES (?,?,?,?)',
                            (str(member.guild.id),str(member.id),str(channel.id),json.dumps(original)))
                overwrite=channel.overwrites_for(member)
                if overwrite.view_channel is not False:
                    overwrite.view_channel=False
                    await channel.set_permissions(member,overwrite=overwrite,reason='Regelbestätigung steht noch aus')
            elif row is not None:
                original=json.loads(row[0])
                # Restore only the view flag we manage; retain concurrent changes to other permissions.
                original_ow=discord.PermissionOverwrite.from_pair(discord.Permissions(original['allow']),discord.Permissions(original['deny']))
                overwrite=channel.overwrites_for(member)
                if overwrite.view_channel is False:
                    overwrite.view_channel=original_ow.view_channel
                    await channel.set_permissions(member,overwrite=None if overwrite.is_empty() else overwrite,
                        reason='Regeln bestätigt – bisherigen Zugriff wiederherstellen')
                with store().connect() as db:
                    db.execute('DELETE FROM community_gate_blocks WHERE guild=? AND user=? AND channel=?',
                        (str(member.guild.id),str(member.id),str(channel.id)))

    async def reconcile_after_ready(self):
        await self.bot.wait_until_ready()
        for guild_id,config in self.configurations():
            guild=self.bot.get_guild(guild_id)
            if guild:
                for member in list(guild.members):
                    try:
                        async with self.lock_for(guild.id,member.id):
                            await self.sync_gate(member,config)
                    except Exception:
                        log.exception('Could not reconcile rules gate')

    @commands.Cog.listener()
    async def on_member_join(self,member):
        config=self.config(member.guild.id)
        if not config or member.bot:
            return
        try:
            # A new membership requires explicit acceptance again, even after leaving/rejoining.
            with store().connect() as db:
                db.execute('DELETE FROM community_acceptance WHERE guild=? AND user=?',(str(member.guild.id),str(member.id)))
            async with self.lock_for(member.guild.id,member.id):
                await self.sync_gate(member,config)
            channel=member.guild.get_channel(int(config['channels']['welcome']))
            if channel:
                rules=member.guild.get_channel(int(config['channels']['rules']))
                await channel.send(f'Willkommen {member.mention}! Bitte lies und bestätige die Regeln in {rules.mention}. Danach kannst du deine Themenbereiche auswählen.',
                    allowed_mentions=discord.AllowedMentions(users=[member],roles=False,everyone=False))
        except Exception:
            log.exception('Community welcome or rules gate failed')

    @commands.Cog.listener()
    async def on_member_update(self,before,after):
        config=self.config(after.guild.id)
        if config and before.roles!=after.roles:
            try:
                async with self.lock_for(after.guild.id,after.id):
                    await self.sync_gate(after,config)
            except Exception:
                log.exception('Community role update failed')

    @commands.Cog.listener()
    async def on_member_remove(self,member):
        if self.config(member.guild.id):
            with store().connect() as db:
                blocks=list(db.execute('SELECT channel,original FROM community_gate_blocks WHERE guild=? AND user=?',
                    (str(member.guild.id),str(member.id))))
            for channel_id,encoded in blocks:
                channel=member.guild.get_channel(int(channel_id))
                if channel:
                    try:
                        original=json.loads(encoded)
                        overwrite=channel.overwrites_for(member)
                        original_ow=discord.PermissionOverwrite.from_pair(discord.Permissions(original['allow']),discord.Permissions(original['deny']))
                        if overwrite.view_channel is False:
                            overwrite.view_channel=original_ow.view_channel
                            await channel.set_permissions(member,overwrite=None if overwrite.is_empty() else overwrite,
                                reason='Temporäre Regel-Sperre nach Austritt aufräumen')
                    except Exception:
                        log.exception('Could not remove departed member gate overwrite')
                        continue
                with store().connect() as db:
                    db.execute('DELETE FROM community_gate_blocks WHERE guild=? AND user=? AND channel=?',
                        (str(member.guild.id),str(member.id),channel_id))
            with store().connect() as db:
                db.execute('DELETE FROM community_acceptance WHERE guild=? AND user=?',(str(member.guild.id),str(member.id)))
            self.member_locks.pop((member.guild.id,member.id),None)


async def setup(bot):
    await bot.add_cog(Community(bot))
