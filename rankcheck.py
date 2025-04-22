import sqlite3
import discord
from discord.ext import commands
import aiohttp
import os
import datetime
import logging

from utils import get_rank

RLSTATS_API_KEY = os.getenv("RLSTATS_API_KEY")

# Maps for platform and playlist names to their IDs
PLATFORM_MAP = {
    "steam": 1,
    "ps4": 2,
    "xbox": 3,
    "switch": 4,
    "epic": 5
}

PLAYLIST_MAP = {
    "unranked": '0',
    "duel": '10',
    "doubles": '11',
    "solo standard": '12',
    "standard": '13',
    "hoops": '27',
    "rumble": '28',
    "dropshot": '29',
    "snow day": '30',
    "tournament": '34'
}

def register_rankcheck_command(bot: commands.Bot):
    @bot.command()
    async def rankcheck(ctx, platform: str, *, ign: str):
        if ctx.channel.name != "rank-check":
            return

        await ctx.message.add_reaction("⏳")

        if get_platform_id(platform) is None:
            await ctx.send(f"⚠️ Invalid rankcheck format. Ex: !rankcheck <platform> <id>")
            logging.info(f"Invalid platform `{platform}` on rankcheck triggered by {ctx.author.name} ({ctx.author.id})")
            return

        user_id = str(ctx.author.id)
        now = datetime.datetime.now(datetime.UTC)
        logging.info(f"Rankcheck command triggered by {ctx.author.name} ({ctx.author.id})")

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
                    logging.info(f"User {ctx.author.name} has recently checked their rank. Days remaining: {days_remaining}")
                    conn.close()
                    return

        logging.info(f"Fetching rank for {ign} on {platform}")
        # Fetch MMR from RLStats API
        rank = await get_player_mmr(platform, ign)
        if not rank:
            await ctx.send(f"⚠️ Couldn’t find stats for `{ign}` on `{platform}`.")
            logging.error(f"Failed to fetch stats for {ign} on {platform}.")
            conn.close()
            return

        rankcheck_date = now.isoformat()
        logging.info(f"Found MMR for {ign} on {platform}: {rank}")

        if existing:
            cursor.execute(
                'UPDATE players SET ign = ?, platform = ?, mmr = ?, rankcheck_date = ? WHERE discord_id = ?',
                (ign, platform, rank, rankcheck_date, user_id)
            )
            action = "updated"
            logging.info(f"Updated rankcheck for {ign} in database.")
        else:
            cursor.execute(
                'INSERT INTO players (discord_id, ign, platform, mmr, rankcheck_date) VALUES (?, ?, ?, ?, ?)',
                (user_id, ign, platform, rank, rankcheck_date)
            )
            action = "registered"
            logging.info(f"Registered new player {ign} in database.")

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
                logging.info(f"Removed old rank roles from {ctx.author.name}.")
            except discord.Forbidden:
                await ctx.message.add_reaction("⚠️")
                await ctx.send("⚠️ I don’t have permission to remove some roles.")
                logging.error(f"Permission error while removing rank roles from {ctx.author.name}.")

            try:
                await ctx.author.add_roles(role)
                await ctx.message.add_reaction("✅")
                await ctx.send(f"✅ {ctx.author.mention} {action}: `{ign}` on `{platform}` — 1v1 MMR: **{rank}** → Assigned **{role_name}**")
                logging.info(f"Assigned role {role_name} to {ctx.author.name}.")
            except discord.Forbidden:
                await ctx.message.add_reaction("⚠️")
                await ctx.send(f"⚠️ {ctx.author.mention} I don’t have permission to assign the role **{role_name}**.")
                logging.error(f"Permission error while assigning role {role_name} to {ctx.author.name}.")
        else:
            await ctx.message.add_reaction("✅")
            await ctx.send(f"✅ {ctx.author.mention} {action}: `{ign}` on `{platform}` — 1v1 MMR: **{rank}**\n⚠️ Role **{role_name}** not found on this server.")
            logging.warning(f"Role {role_name} not found for {ctx.author.name}.")



def get_platform_id(platform_name: str) -> int | None:
    return PLATFORM_MAP.get(platform_name.strip().lower())

def get_playlist_id(playlist_name: str) -> int | None:
    return PLAYLIST_MAP.get(playlist_name.strip().lower())


async def get_player_stats(platform_id, player_id):
    url = f"https://api.rlstats.net/v1/profile/stats"
    params = {
        "apikey": RLSTATS_API_KEY,
        "platformid": get_platform_id(platform_id),
        "playerid": player_id
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                logging.info(f"Successfully fetched stats for {player_id} on platform {platform_id}.")
                return await response.json()
            else:
                logging.error(f"Failed: {response.status}")
                logging.error(await response.text())
                return None

async def get_player_mmr(platform_id, player_id, playlist_id=PLAYLIST_MAP['duel']):
    data = await get_player_stats(platform_id, player_id)
    if not data:
        return None

    season_info = data.get('SeasonInfo')
    if not season_info:
        logging.error(f"No season info available for player {player_id}.")
        return None

    season_id = str(season_info.get('SeasonID'))
    if not season_id:
        logging.error(f"No season ID available for player {player_id}.")
        return None

    ranked_seasons = data.get('RankedSeasons', {})
    season_data = ranked_seasons.get(season_id)
    if not season_data:
        logging.error(f"No season data found for player {player_id} in season {season_id}.")
        return None

    playlist_data = season_data.get(playlist_id)
    if not playlist_data:
        logging.error(f"No playlist data found for player {player_id} in playlist {playlist_id}.")
        return None

    return playlist_data.get('SkillRating')
# asyncio.run(get_player_mmr("steam", "76561198251007520"))