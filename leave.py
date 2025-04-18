from discord.ext import commands
import sqlite3
from utils import create_queue_embed

def register_leave_command(bot: commands.Bot):
    @bot.command(aliases=["l"])
    async def leave(ctx):
        if ctx.channel.name != "queue-here":
            return

        user_id = str(ctx.author.id)

        conn = sqlite3.connect("mmr.db")
        cursor = conn.cursor()

        # Check if the player is currently in queue
        cursor.execute("SELECT queue_status FROM players WHERE discord_id = ?", (user_id,))
        row = cursor.fetchone()

        if not row:
            await ctx.message.delete()
            await ctx.author.send("❌ You are not registered in the system.")
            conn.close()
            return

        queue_status = row[0]

        if queue_status != "IN_QUEUE":
            await ctx.message.delete()
            await ctx.author.send("ℹ️ You are not currently in the queue.")
            conn.close()
            return

        # Update player to IDLE
        cursor.execute("UPDATE players SET queue_status = 'IDLE' WHERE discord_id = ?", (user_id,))
        conn.commit()
        conn.close()

        # Create anonymous embed
        embed = create_queue_embed("A player has left the queue")

        await ctx.message.delete()
        await ctx.author.send("✅ You have left the queue.")
        await ctx.channel.send(embed=embed)
