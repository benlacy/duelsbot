import sqlite3
import discord
from discord.ext import commands
import datetime
import logging

from utils import get_rank, create_queue_embed
from matchmaker import run_matchmaking

REGION_ROLE_NAMES = ["NA", "EU", "SAM", "MENA", "APAC", "OCE"]

def register_queue_command(bot: commands.Bot):
    @bot.command(aliases=["queue"])
    async def q(ctx):
        location = f"DMs" if isinstance(ctx.channel, discord.DMChannel) else f"#{ctx.channel.name}"
        logging.info(f"User {ctx.author} ({ctx.author.id}) used !q from {location}")

        user_id = str(ctx.author.id)

        # Get the guild and member object for role-checking
        guild = discord.utils.get(bot.guilds)  # assumes bot is only in one server
        member = guild.get_member(ctx.author.id)
        if not member:
            await ctx.author.send("❌ Could not verify your roles. Please try again later.")
            return

        # Determine region roles from user
        region_roles = [role.name for role in member.roles if role.name in REGION_ROLE_NAMES]
        logging.info(f"Region roles for {user_id}: {region_roles}")
        if not region_roles:
            await ctx.author.send(
                "❌ You need at least one region role to queue.\n"
                "Please head over to <#1362802610796630340> and react to choose the regions you play in."
            )
            return

        # Connect to DB and set queue_status to IN_QUEUE
        conn = sqlite3.connect('mmr.db')
        cursor = conn.cursor()

        cursor.execute("SELECT queue_status FROM players WHERE discord_id = ?", (user_id,))
        row = cursor.fetchone()

        if not row:
            logging.info(f"User {user_id} not found in DB. Prompting registration.")
            await ctx.author.send("❌ You are not registered. Please use `!rankcheck` before queueing.")
            if not isinstance(ctx.channel, discord.DMChannel):
                await ctx.message.delete()
            return

        status = row[0]
        logging.info(f"Current queue status for {user_id}: {status}")

        if status != "IDLE" and status is not None:
            logging.info(f"{user_id} attempted to queue while {status}")
            # You can uncomment this to enforce status logic
            # await ctx.author.send(f"❌ You are currently marked as `{status}`. You can only queue if you're `IDLE`. You either need to confirm your match or report it.")
            # if not isinstance(ctx.channel, discord.DMChannel):
            #     await ctx.message.delete()
            # return

        region_str = ",".join(region_roles)

        now = datetime.datetime.now(datetime.UTC)
        logging.info(f"Setting {user_id} to IN_QUEUE at {now.isoformat()} for regions: {region_str}")
        cursor.execute(
            "UPDATE players SET queue_status = 'IN_QUEUE', queue_time = ?, regions = ? WHERE discord_id = ?",
            (now, region_str, user_id)
        )
        conn.commit()
        conn.close()

        embed = create_queue_embed("A new player has joined the queue.")

        if not isinstance(ctx.channel, discord.DMChannel):
            await ctx.message.delete()
            await ctx.channel.send(embed=embed)
        else:
            # Try to send embed to queue channel
            queue_channel = discord.utils.get(guild.text_channels, name="queue-here")
            if queue_channel:
                await queue_channel.send(embed=embed)

        await ctx.author.send(f"✅ You’ve been added to the queue. Looking for opponents...\n\n**Regions you are queueing for**: {region_str}")

        logging.info(f"Running matchmaking for {user_id}...")
        await run_matchmaking(bot)
