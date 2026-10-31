"""Explicit guild selection, one-time migration and cross-guild validation."""
import discord
from config_store import SPECS, GUILD_KEYS, get_setting, store


async def migrate_legacy_settings(bot):
    settings = store()
    if settings.migration_done():
        return
    legacy = settings.legacy_values()
    for key in ('bot.status_channel_id', 'github.channel_id', 'twitch.channel_id', 'stats.channel_all'):
        if not legacy.get(key):
            continue
        try:
            channel = await bot.fetch_channel(legacy[key])
        except discord.NotFound:
            continue
        settings.migrate_legacy(channel.guild.id)
        return
    # A genuinely fresh installation has no old server configuration to assign.
    if not legacy:
        with settings.connect() as db:
            db.execute("INSERT OR IGNORE INTO settings_meta VALUES ('guild_migration','fresh')")
        return
    raise RuntimeError('Alte Konfiguration konnte keinem Server zugeordnet werden; Migration zuerst gezielt ausführen.')


def validate_guild_values(guild, values):
    if not isinstance(values, dict):
        raise ValueError('Einstellungen müssen ein Objekt sein.')
    from config_store import normalize
    normalized = {key: normalize(key,value) for key,value in values.items()}
    if set(normalized) - GUILD_KEYS:
        raise ValueError('Diese Einstellung gehört zum globalen Betreiberbereich.')
    for key,value in normalized.items():
        kind = SPECS[key][0]
        if value is None:
            continue
        if kind == 'id':
            if key.endswith('role_id'):
                if not guild.get_role(value):
                    raise ValueError('Die Rolle muss zum ausgewählten Server gehören.')
            else:
                channel = guild.get_channel(value)
                if not channel:
                    raise ValueError('Der Kanal muss zum ausgewählten Server gehören.')
                if key.startswith('stats.') and not isinstance(channel,discord.VoiceChannel):
                    raise ValueError('Statistikkanäle müssen normale Sprachkanäle sein.')
                if key in ('bot.status_channel_id','github.channel_id','twitch.channel_id') and not isinstance(channel,discord.TextChannel):
                    raise ValueError('Für Meldungen einen normalen Textkanal auswählen.')
        elif kind == 'ids' and any(guild.get_member(member_id) is None for member_id in value):
            raise ValueError('Erlaubte Benutzer müssen Mitglieder dieses Servers sein.')
    repo = normalized.get('github.repo_filter')
    if repo and repo.lower() not in get_setting('github.allowed_repos'):
        raise ValueError('Dieses Repository muss der Bot-Betreiber zuerst unter github.allowed_repos freigeben.')
    return normalized
