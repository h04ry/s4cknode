from config_store import get_setting, store, ROOT
import asyncio
import os
import logging
import aiohttp
import discord
from dotenv import dotenv_values
from discord.ext import commands, tasks

log = logging.getLogger(__name__)


class GitHubMonitor(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.last_error = None
        with store().connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS github_progress (source TEXT PRIMARY KEY, cursor TEXT NOT NULL)')
        self.check_github.start()

    async def cog_unload(self):
        task=self.check_github.get_task()
        self.check_github.cancel()
        if task:
            await asyncio.gather(task,return_exceptions=True)

    def cursor(self, source, channel):
        with store().connect() as db:
            row = db.execute('SELECT cursor FROM github_guild_progress WHERE guild=? AND channel=? AND source=?', (str(channel.guild.id),str(channel.id),source)).fetchone()
        return row[0] if row else None

    def remember(self, source, value, channel):
        with store().connect() as db:
            db.execute('INSERT INTO github_guild_progress VALUES (?,?,?,?) ON CONFLICT(guild,channel,source) DO UPDATE SET cursor=excluded.cursor', (str(channel.guild.id),str(channel.id),source,value))

    async def fetch(self, session, path, **params):
        token = os.getenv('GITHUB_TOKEN') or dotenv_values(ROOT / '.env').get('GITHUB_TOKEN')
        headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'S4CKNode-GitHubMonitor'}
        public=params.pop('public',False)
        if token and not public:
            headers['Authorization'] = f'Bearer {token}'
        async with session.get('https://api.github.com/' + path, params=params, headers=headers) as response:
            if response.status != 200:
                message = f'GitHub HTTP {response.status}: Repository-/Tokenrechte prüfen.'
                if message != self.last_error:
                    log.warning(message)
                self.last_error = message
                return None
            self.last_error = None
            data = await response.json()
            return data if isinstance(data, list) else None

    async def poll_repository(self, session, channel):
        repo = get_setting('github.repo_filter',channel.guild.id)
        if repo.lower() not in get_setting('github.allowed_repos'):
            return
        source = 'commits:' + repo
        cursor = self.cursor(source,channel)
        commits = await self.fetch(session, f'repos/{repo}/commits', per_page=100)
        if not commits:
            return
        if cursor is None:
            self.remember(source, commits[0]['sha'],channel)
            return
        pending = []
        found = False
        for page in range(1, 11):
            if page > 1:
                commits = await self.fetch(session, f'repos/{repo}/commits', per_page=100, page=page)
                if commits is None:
                    return
            for commit in commits:
                if commit['sha'] == cursor:
                    found = True
                    break
                pending.append(commit)
            if found or len(commits) < 100:
                break
        if not found:
            # A force-push or very large backlog: report the latest state once.
            pending = pending[:1]
        for commit in reversed(pending):
            message = commit.get('commit', {}).get('message') or 'Änderung ohne Beschreibung'
            lines = message.splitlines()
            embed = discord.Embed(title=('🆕 ' + lines[0])[:256],
                                  description=('\n'.join(lines[1:]).strip() or message)[:3500],
                                  url=commit.get('html_url') or f'https://github.com/{repo}/commit/{commit["sha"]}', color=0x7C6AFF)
            embed.set_author(name='Bot-Neuerungen · ' + repo)
            embed.add_field(name='Anleitung', value=f'[Alle Funktionen und Einrichtung](https://github.com/{repo}#readme)', inline=False)
            embed.set_footer(text='Commit ' + commit['sha'][:7])
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            # Failed Discord sends are retried instead of silently losing updates.
            self.remember(source, commit['sha'],channel)

    async def poll_account(self, session, channel):
        user=get_setting('github.user',channel.guild.id)
        source = 'events:' + user
        events = await self.fetch(session, f'users/{user}/events/public', per_page=100, public=True)
        if not events:
            return
        cursor = self.cursor(source,channel)
        if cursor is None:
            self.remember(source, events[0]['id'],channel)
            return
        pending = []
        for event in events:
            if event['id'] == cursor:
                break
            pending.append(event)
        for event in reversed(pending):
            embed = self.create_event_embed(event)
            if embed:
                await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            self.remember(source, event['id'],channel)

    @tasks.loop(minutes=2)
    async def check_github(self):
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            for guild in list(self.bot.guilds):
                channel=guild.get_channel(get_setting('github.channel_id',guild.id))
                if not isinstance(channel,discord.TextChannel):
                    continue
                try:
                    if get_setting('github.repo_filter',guild.id):
                        await self.poll_repository(session,channel)
                    elif get_setting('github.user',guild.id):
                        await self.poll_account(session,channel)
                except Exception as exc:
                    log.warning('GitHub-Zustellung für einen Server fehlgeschlagen: %s',type(exc).__name__)

    @check_github.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    def create_event_embed(self, event):
        event_type = event.get("type")
        repo_name = event.get("repo", {}).get("name")
        actor = event.get("actor", {}).get("login")
        payload = event.get("payload", {})

        embed = discord.Embed(color=0x24292e)
        embed.set_author(name=f"GitHub: {repo_name}", url=f"https://github.com/{repo_name}")
        embed.set_footer(text=f"Aktion von {actor}")

        # 1. Releases
        if event_type == "ReleaseEvent":
            release = payload.get("release", {})
            tag = release.get("tag_name", "Release")
            title = release.get("name") or tag
            embed.color = 0x28a745  # Grün für Releases
            embed.title = f"🚀 Neues Release veröffentlicht: {title}"
            embed.url = release.get("html_url")
            body = release.get("body", "")
            embed.description = body[:500] if body else "*Keine Release-Notes angegeben.*"

        # 2. Pushes / Commits
        elif event_type == "PushEvent":
            commits = payload.get("commits", [])
            if not commits:
                return None
            branch = payload.get("ref", "").split("/")[-1]
            desc = "\n".join([
                f"[`{c['sha'][:7]}`](https://github.com/{repo_name}/commit/{c['sha']}) {c.get('message', '').splitlines()[0]}"
                for c in commits[:5]
            ])
            embed.title = f"Neuer Push auf Branch `{branch}` ({len(commits)} Commit(s))"
            embed.description = desc

        # 3. Issues
        elif event_type == "IssuesEvent":
            action = payload.get("action")
            issue = payload.get("issue", {})
            embed.title = f"Issue #{issue.get('number')} {action}: {issue.get('title')}"
            embed.url = issue.get("html_url")
            embed.description = issue.get("body", "")[:300] or "*Keine Beschreibung vorhanden.*"

        # 4. Issue- und PR-Kommentare
        elif event_type == "IssueCommentEvent":
            action = payload.get("action")
            comment = payload.get("comment", {})
            issue = payload.get("issue", {})
            embed.title = f"Neuer Kommentar zu Issue #{issue.get('number')}"
            embed.url = comment.get("html_url")
            embed.description = comment.get("body", "")[:300] or "*Kein Inhalt.*"

        # 5. Pull Requests
        elif event_type == "PullRequestEvent":
            action = payload.get("action")
            pr = payload.get("pull_request", {})
            embed.title = f"Pull Request #{pr.get('number')} {action}: {pr.get('title')}"
            embed.url = pr.get("html_url")
            embed.description = pr.get("body", "")[:300] or "*Keine Beschreibung.*"

        else:
            return None

        return embed

async def setup(bot):
    await bot.add_cog(GitHubMonitor(bot))
