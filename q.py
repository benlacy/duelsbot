import sqlite3
import discord
from discord.ext import commands
from collections import Counter
import datetime
import logging

from utils import get_rank, create_queue_embed
from matchmaker import run_matchmaking

REGION_ROLE_NAMES = ["NA", "EU", "SAM", "MENA", "APAC", "OCE"]

def register_queue_command(bot: commands.Bot):
    @bot.command(aliases=["queue"])
    async def q(ctx):
        if ctx.channel.name != "queue-here":
            logging.info(f"Ignored command from channel: {ctx.channel.name}")
            return

        user_id = str(ctx.author.id)
        logging.info(f"User {ctx.author} ({user_id}) used !q")

        # Connect to DB and set queue_status to IN_QUEUE
        conn = sqlite3.connect('mmr.db')
        cursor = conn.cursor()

        cursor.execute("SELECT queue_status FROM players WHERE discord_id = ?", (user_id,))
        row = cursor.fetchone()

        if not row:
            logging.info(f"User {user_id} not found in DB. Prompting registration.")
            await ctx.author.send("❌ You are not registered. Please use `!rankcheck` before queueing.")
            await ctx.message.delete()
            return

        status = row[0]
        logging.info(f"Current queue status for {user_id}: {status}")

        if status != "IDLE" and status is not None:
            logging.info(f"{user_id} attempted to queue while {status}")
            # Uncomment below to enforce status check
            # await ctx.author.send(f"❌ You are currently marked as `{status}`. You can only queue if you're `IDLE`. You either need to confirm your match or report it")
            # await ctx.message.delete()
            # return

        # Determine region roles from user
        region_roles = [role.name for role in ctx.author.roles if role.name in REGION_ROLE_NAMES]
        logging.info(f"Region roles for {user_id}: {region_roles}")
        if not region_roles:
            await ctx.channel.send(
                "❌ You need at least one region role to queue.\n"
                "Please head over to <#1362802610796630340> and react to choose the regions you play in."
            )
            return

        region_str = ",".join(region_roles)

        # Update their queue status, queue time, and regions
        now = datetime.datetime.now(datetime.UTC)
        logging.info(f"Setting {user_id} to IN_QUEUE at {now.isoformat()} for regions: {region_str}")
        cursor.execute(
            "UPDATE players SET queue_status = 'IN_QUEUE', queue_time = ?, regions = ? WHERE discord_id = ?",
            (now, region_str, user_id)
        )
        conn.commit()
        conn.close()

        # Create anonymous embed
        embed = create_queue_embed("A new player has joined the queue.")

        await ctx.message.delete()
        await ctx.author.send(f"✅ You’ve been added to the queue. Looking for opponents...\n\n**Regions you are queueing for**: {region_str}")
        await ctx.channel.send(embed=embed)

        logging.info(f"Running matchmaking for {user_id}...")
        await run_matchmaking(bot)
