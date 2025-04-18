import discord
from discord.ext import commands
import sqlite3
import os
import datetime

from rankcheck import get_player_mmr
from q import register_queue_command
from report import register_report_command
from utils import get_rank

DISCORD_BOT_TOKEN = os.getenv("FEER_DUELS_TOKEN")
RLSTATS_API_KEY = os.getenv("RLSTATS_API_KEY")

FEER_RANK_CHECK_CHANNEL = 764692331441422347

intents = discord.Intents.default()
intents.message_content = True  # Needed to respond to messages
intents.messages = True
intents.reactions = True
intents.dm_messages = True
intents.guilds = True
intents.members = True  # if you use fetch_user or access member info

bot = commands.Bot(command_prefix="!", intents=intents)
register_queue_command(bot)
register_report_command(bot)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user.name} (ID: {bot.user.id})")

@bot.command()
async def rankcheck(ctx, platform: str, *, ign: str):
    if ctx.channel.name != "rank-check":
        return

    user_id = str(ctx.author.id)
    now = datetime.datetime.now(datetime.UTC)

    conn = sqlite3.connect('mmr.db')
    cursor = conn.cursor()

    cursor.execute('SELECT ign, platform, mmr, rankcheck_date FROM players WHERE discord_id = ?', (user_id,))
    existing = cursor.fetchone()

    if existing:
        last_check_str = existing[3]
        if last_check_str:
            last_check = datetime.datetime.fromisoformat(last_check_str)
            if (now - last_check).days < 14:
                days_remaining = 14 - (now - last_check).days
                await ctx.send(f"⏳ {ctx.author.mention}, you can check your rank again in {days_remaining} day(s).")
                conn.close()
                return

    # Fetch MMR from RLStats API
    rank = await get_player_mmr(platform, ign)
    if not rank:
        await ctx.send(f"⚠️ Couldn’t find stats for `{ign}` on `{platform}`.")
        conn.close()
        return

    rankcheck_date = now.isoformat()

    if existing:
        cursor.execute(
            'UPDATE players SET ign = ?, platform = ?, mmr = ?, rankcheck_date = ? WHERE discord_id = ?',
            (ign, platform, rank, rankcheck_date, user_id)
        )
        action = "updated"
    else:
        cursor.execute(
            'INSERT INTO players (discord_id, ign, platform, mmr, rankcheck_date) VALUES (?, ?, ?, ?, ?)',
            (user_id, ign, platform, rank, rankcheck_date)
        )
        action = "registered"

    conn.commit()
    conn.close()

    # Role assignment
    role_name = get_rank(rank)
    guild = ctx.guild
    role = discord.utils.get(guild.roles, name=role_name)

    if role:
        # Remove existing "Rank " roles before adding the new one
        rank_roles = [r for r in ctx.author.roles if r.name.startswith("Rank ")]
        try:
            await ctx.author.remove_roles(*rank_roles)
        except discord.Forbidden:
            await ctx.send("⚠️ I don’t have permission to remove some roles.")

        try:
            await ctx.author.add_roles(role)
            await ctx.send(f"✅ {ctx.author.mention} {action}: `{ign}` on `{platform}` — 1v1 MMR: **{rank}** → Assigned **{role_name}**")
        except discord.Forbidden:
            await ctx.send(f"⚠️ {ctx.author.mention} I don’t have permission to assign the role **{role_name}**.")
    else:
        await ctx.send(f"✅ {ctx.author.mention} {action}: `{ign}` on `{platform}` — 1v1 MMR: **{rank}**\n⚠️ Role **{role_name}** not found on this server.")



@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

bot.run(DISCORD_BOT_TOKEN)
