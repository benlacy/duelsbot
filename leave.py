from discord.ext import commands
import sqlite3
import logging
from utils import create_queue_embed

def register_leave_command(bot: commands.Bot):
    @bot.command(aliases=["l"])
    async def leave(ctx):
        logging.info(f"[LEAVE] Command invoked by user {ctx.author} ({ctx.author.id}) in #{ctx.channel.name}")

        if ctx.channel.name != "queue-here":
            logging.info("[LEAVE] Command used in wrong channel.")
            return

        user_id = str(ctx.author.id)

        conn = sqlite3.connect("mmr.db")
        cursor = conn.cursor()
        logging.info(f"[LEAVE] Checking queue status for user_id={user_id}")

        # Check if the player is currently in queue
        cursor.execute("SELECT queue_status FROM players WHERE discord_id = ?", (user_id,))
        row = cursor.fetchone()

        if not row:
            logging.info("[LEAVE] User not found in database.")
            await ctx.message.delete()
            await ctx.author.send("❌ You are not registered in the system.")
            conn.close()
            return

        queue_status = row[0]
        logging.info(f"[LEAVE] Current queue_status for {user_id}: {queue_status}")

        if queue_status != "IN_QUEUE":
            logging.info("[LEAVE] User is not in queue.")
            await ctx.message.delete()
            await ctx.author.send("ℹ️ You are not currently in the queue.")
            conn.close()
            return

        # Update player to IDLE
        logging.info(f"[LEAVE] Updating user {user_id} to IDLE.")
        cursor.execute("UPDATE players SET queue_status = 'IDLE' WHERE discord_id = ?", (user_id,))
        conn.commit()
        conn.close()

        # Create anonymous embed
        embed = create_queue_embed("A player has left the queue")
        logging.info(f"[LEAVE] Sending queue update embed to channel #{ctx.channel.name}")

        await ctx.message.delete()
        await ctx.author.send("✅ You have left the queue.")
        await ctx.channel.send(embed=embed)
        logging.info(f"[LEAVE] User {user_id} has successfully left the queue.")
