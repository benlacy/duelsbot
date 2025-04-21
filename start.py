import discord
from discord.ext import commands
import os
import logging
from logging.handlers import RotatingFileHandler

# 🆕 Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        RotatingFileHandler("bot.log", encoding="utf-8", maxBytes=1_000_000, backupCount=5),  # 1MB per file, keep 5 old logs
        logging.StreamHandler()
    ]
)

from q import register_queue_command
from leave import register_leave_command
from report import register_report_command
from report import register_leaderboard_command
from rankcheck import register_rankcheck_command
from status import register_status_command
from matchmaker import matchmaking_loop
from stats import register_stats_command

DISCORD_BOT_TOKEN = os.getenv("FEER_DUELS_TOKEN")
RLSTATS_API_KEY = os.getenv("RLSTATS_API_KEY")

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
register_rankcheck_command(bot)
register_leave_command(bot)
register_status_command(bot)
register_leaderboard_command(bot)
register_stats_command(bot)

@bot.event
async def on_ready():
    logging.info(f"✅ Logged in as {bot.user.name} (ID: {bot.user.id})")
    bot.loop.create_task(matchmaking_loop(bot))

@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")
    logging.info(f"Ping command used by {ctx.author} (ID: {ctx.author.id})")

bot.run(DISCORD_BOT_TOKEN)
