import discord
from discord.ext import commands
import sqlite3
import logging
from utils import create_queue_embed

def register_leave_command(bot: commands.Bot):
    @bot.command(aliases=["l"])
    async def leave(ctx):
        location = f"DMs" if isinstance(ctx.channel, discord.DMChannel) else f"#{ctx.channel.name}"
        logging.info(f"[LEAVE] Command invoked by user {ctx.author} ({ctx.author.id}) in {location}")

        if not isinstance(ctx.channel, discord.DMChannel) and ctx.channel.name != "queue-here":
            logging.info("[LEAVE] Command used in wrong channel.")
            return

        user_id = str(ctx.author.id)

        conn = sqlite3.connect("mmr.db")
        cursor = conn.cursor()
        logging.info(f"[LEAVE] Checking queue status for user_id={user_id}")

        cursor.execute("SELECT queue_status FROM players WHERE discord_id = ?", (user_id,))
        row = cursor.fetchone()

        if not row:
            logging.info("[LEAVE] User not found in database.")
            if ctx.guild:  # Only try deleting if not DM
                await ctx.message.delete()
            await ctx.author.send("❌ You are not registered in the system.")
            conn.close()
            return

        queue_status = row[0]
        logging.info(f"[LEAVE] Current queue_status for {user_id}: {queue_status}")

        if queue_status != "IN_QUEUE":
            logging.info("[LEAVE] User is not in queue.")
            if ctx.guild:
                await ctx.message.delete()
            await ctx.author.send("ℹ️ You are not currently in the queue.")
            conn.close()
            return

        logging.info(f"[LEAVE] Updating user {user_id} to IDLE.")
        cursor.execute("UPDATE players SET queue_status = 'IDLE' WHERE discord_id = ?", (user_id,))
        conn.commit()
        conn.close()

        embed = create_queue_embed("A player has left the queue")
        logging.info(f"[LEAVE] Sending queue update embed")

        if ctx.guild:
            await ctx.message.delete()
            await ctx.channel.send(embed=embed)
        else:
            # Try to send to the queue channel if invoked in DMs
            queue_channel = discord.utils.get(bot.get_all_channels(), name="queue-here")
            if queue_channel:
                await queue_channel.send(embed=embed)

        await ctx.author.send("✅ You have left the queue.")
        logging.info(f"[LEAVE] User {user_id} has successfully left the queue.")
