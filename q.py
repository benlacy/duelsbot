import sqlite3
import discord
from discord.ext import commands
from collections import Counter
import datetime

from utils import get_rank
from matchmaker import run_matchmaking

def register_queue_command(bot: commands.Bot):
    @bot.command()
    async def q(ctx):
        if ctx.channel.name != "queue-here":
            return

        user_id = str(ctx.author.id)

        # Connect to DB and set queue_status to IN_QUEUE
        conn = sqlite3.connect('mmr.db')
        cursor = conn.cursor()

        cursor.execute("SELECT mmr FROM players WHERE discord_id = ?", (user_id,))
        row = cursor.fetchone()

        if not row:
            await ctx.author.send("❌ You are not registered. Please use `!rankcheck` before queueing.")
            await ctx.message.delete()
            return

        mmr = row[0]

        # Update their queue status and queue time
        now = datetime.datetime.now(datetime.UTC)
        cursor.execute(
            "UPDATE players SET queue_status = 'IN_QUEUE', queue_time = ? WHERE discord_id = ?",
            (now, user_id)
        )
        conn.commit()

        # Get current queue counts per tier
        cursor.execute("SELECT mmr FROM players WHERE queue_status = 'IN_QUEUE'")
        mmrs = [r[0] for r in cursor.fetchall()]
        conn.close()

        rank_counts = Counter([get_rank(m) for m in mmrs])

        # Create anonymous embed
        embed = discord.Embed(
            title="🔒 Queue Updated",
            description="A new player has joined the queue.\n\n**Current Queue Status:**",
            color=discord.Color.blurple()
        )

        for rank in ["Rank S", "Rank X", "Rank A", "Rank B", "Rank C", "Rank D"]:
            count = rank_counts.get(rank, 0)
            embed.add_field(name=rank, value=f"{count} queued", inline=True)

        await ctx.message.delete()
        await ctx.author.send(f"✅ You’ve been added to the queue. Looking for opponents...")
        await ctx.channel.send(embed=embed)

        await run_matchmaking(bot)
