import discord
import sqlite3
from collections import defaultdict
import re
import logging
import datetime

FEER_GUILD_ID = 491059327038259231

def get_rank(mmr: int) -> str:
    if mmr >= 1500: return "Rank S"
    elif mmr >= 1340: return "Rank X"
    elif mmr >= 1175: return "Rank A"
    elif mmr >= 986: return "Rank B"
    elif mmr >= 815: return "Rank C"
    else: return "Rank D"

# def create_queue_embed(description, mmrs) -> discord.Embed:
#     rank_counts = Counter([get_rank(m) for m in mmrs])

#     # Create anonymous embed
#     embed = discord.Embed(
#         title="🔒 Queue Updated",
#         description=f"{description}\n\n**Current Queue Status:**",
#         color=discord.Color.blurple()
#     )

#     for rank in ["Rank S", "Rank X", "Rank A", "Rank B", "Rank C", "Rank D"]:
#         count = rank_counts.get(rank, 0)
#         embed.add_field(name=rank, value=f"{count} queued", inline=True)

#     return embed

# Mapping of region codes to emoji flags
REGION_EMOJIS = {
    "EU": "🇪🇺",
    "NA": "🇺🇸",
    "SAM": "🇧🇷",
    "APAC": "🇯🇵",
    "MENA": "🇸🇦",
    "OCE": "🇦🇺",
}

def create_queue_embed(description) -> discord.Embed:
    # Connect to the database and fetch queued players
    conn = sqlite3.connect("mmr.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT mmr, queue_time, regions FROM players WHERE queue_status = 'IN_QUEUE'"
    )
    rows = cursor.fetchall()
    conn.close()

    now = datetime.datetime.now(datetime.UTC)

    embed = discord.Embed(
        title="🔒 Queue Updated",
        description=f"{description}\n\n**Current Queue Status:**",
        color=discord.Color.blurple()
    )

    if not rows:
        embed.description += "\n\nQueue is empty."
    else:
        lines = []
        for mmr, queue_time, region_roles in rows:
            try:
                # Ensure queue_time is parsed as UTC datetime if it's stored as a string
                if isinstance(queue_time, str):
                    queue_time = datetime.datetime.fromisoformat(queue_time)
                delta = now - queue_time

                rank = get_rank(mmr)
                queued_for = f"<t:{int(queue_time.timestamp())}:R>"

                region_list = sorted(filter(None, re.split(r"[,\s]+", region_roles.strip())))
                region_emojis = [REGION_EMOJIS.get(r, r) for r in region_list]
                region_str = "".join(region_emojis) if region_emojis else "🌍"

                lines.append(f"{region_str} - {rank} ({queued_for})")
            except Exception as e:
                logging.warning(f"Failed to format queue entry: {e}")

        embed.description += "\n\n" + "\n".join(lines)

    return embed
