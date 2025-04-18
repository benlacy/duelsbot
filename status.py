# status.py

from discord.ext import commands
import discord
import sqlite3
from utils import create_queue_embed

def register_status_command(bot: commands.Bot):
    @bot.command(aliases=['s'])
    async def status(ctx):
        if ctx.channel.name != "queue-here":
            return
            
        # Create anonymous embed
        embed = create_queue_embed("Updated Queue Status")

        await ctx.message.delete()
        await ctx.channel.send(embed=embed)
