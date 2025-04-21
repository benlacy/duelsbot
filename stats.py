import discord
from discord.ext import commands
import datetime
import sqlite3

def register_stats_command(bot: commands.Bot):
    @bot.command()
    async def stats(ctx, *, target: discord.Member = None):
        target = target or ctx.author
        user_id = str(target.id)

        conn = sqlite3.connect("mmr.db")
        cursor = conn.cursor()

        # Fetch the 5 most recent matches involving the user
        cursor.execute("""
            SELECT player1_id, player2_id, winner_id, created_at
            FROM matches
            WHERE player1_id = ? OR player2_id = ?
            ORDER BY created_at DESC
            LIMIT 5
        """, (user_id, user_id))

        matches = cursor.fetchall()
        conn.close()

        if not matches:
            await ctx.send(f"❌ {target.display_name} has no recent matches.")
            return

        embed = discord.Embed(
            title=f"{target.display_name}'s Recent Matches",
            color=discord.Color.blue()
        )

        lines = []
        for match in matches:
            p1, p2, winner, timestamp = match
            opponent_id = p2 if p1 == user_id else p1
            result = "✅ Win" if winner == user_id else "❌ Loss"

            timestamp = datetime.datetime.fromisoformat(timestamp)
            relative_time = get_relative_time(timestamp)

            display = "Unknown"
            try:
                opponent = ctx.guild.get_member(int(opponent_id))
                if opponent:
                    rank_role = next((r.name for r in opponent.roles if r.name.startswith("Rank ")), None)
                    display = f"{opponent.display_name} ({rank_role})" if rank_role else opponent.display_name
                else:
                    display = "Unknown"
            except:
                display = "Unknown"

            lines.append(f"{result} - {display} ({relative_time})")

        embed.description = "\n".join(lines)
        await ctx.send(embed=embed)

def get_relative_time(past: datetime.datetime) -> str:
    now = datetime.datetime.now(datetime.UTC)
    diff = now - past

    seconds = diff.total_seconds()
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24
    weeks = days // 7
    months = days // 30.44  # average
    years = days // 365.25

    if seconds < 60:
        return f"{int(seconds)}s ago"
    elif minutes < 60:
        return f"{int(minutes)}m ago"
    elif hours < 24:
        return f"{int(hours)}h ago"
    elif days < 7:
        return f"{int(days)}d ago"
    elif weeks < 5:
        return f"{int(weeks)}w ago"
    elif months < 12:
        return f"{int(months)}mo ago"
    else:
        return f"{int(years)}y ago"