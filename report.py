from discord.ext import commands
import discord
import sqlite3

def register_report_command(bot: commands.Bot):
    @bot.command()
    async def report(ctx, match_id: int, result: str):
        # Only respond if used in #score-report
        if ctx.channel.name != "score-report":
            return

        await ctx.message.add_reaction("⏳")

        # Validate result
        result = result.upper()
        if result not in ["W", "L"]:
            await ctx.send("⚠️ Invalid result. Use `W` for win or `L` for loss.")
            await ctx.message.add_reaction("⚠️")
            return

        user_id = str(ctx.author.id)

        # Fetch match
        conn = sqlite3.connect("mmr.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT player1_id, player2_id, winner_id FROM matches WHERE match_id = ? AND status = 'CONFIRMED'",
            (match_id,)
        )
        row = cursor.fetchone()

        if not row:
            await ctx.send("❌ Match ID not found, or not active")
            await ctx.message.add_reaction("❌")
            conn.close()
            return

        p1_id, p2_id, winner_id = row

        if str(p1_id) != user_id and str(p2_id) != user_id:
            await ctx.send("❌ You are not a participant in this match.")
            await ctx.message.add_reaction("❌")
            conn.close()
            return

        if winner_id is not None:
            await ctx.send("⚠️ This match has already been reported.")
            await ctx.message.add_reaction("⚠️")
            conn.close()
            return

        if result == "W":
            new_winner_id = user_id
            new_loser_id = str(p1_id) if str(p2_id) == user_id else str(p2_id)
        else:  # result == "L"
            new_loser_id = user_id
            new_winner_id = str(p1_id) if str(p2_id) == user_id else str(p2_id)

        # Update match result
        cursor.execute(
            "UPDATE matches SET winner_id = ?, status = 'REPORTED' WHERE match_id = ?",
            (new_winner_id, match_id)
        )

        # Get current MMRs
        cursor.execute("SELECT mmr FROM players WHERE discord_id = ?", (new_winner_id,))
        winner_mmr = cursor.fetchone()[0]

        cursor.execute("SELECT mmr FROM players WHERE discord_id = ?", (new_loser_id,))
        loser_mmr = cursor.fetchone()[0]

        # Calculate new MMRs
        new_winner_mmr, new_loser_mmr = calculate_elo(winner_mmr, loser_mmr)

        # Update MMRs
        cursor.execute("UPDATE players SET mmr = ? WHERE discord_id = ?", (new_winner_mmr, new_winner_id))
        cursor.execute("UPDATE players SET mmr = ? WHERE discord_id = ?", (new_loser_mmr, new_loser_id))


        # Set both players' status to IDLE
        cursor.execute(
            "UPDATE players SET queue_status = 'IDLE' WHERE discord_id IN (?, ?)",
            (p1_id, p2_id)
        )

        conn.commit()
        conn.close()

        await ctx.send(f"✅ Result for match `{match_id}` recorded: <@{new_winner_id}> wins!")
        await ctx.message.add_reaction("✅")

        leaderboard_channel = discord.utils.get(bot.get_all_channels(), name="leaderboard")
        if leaderboard_channel:
            await post_leaderboard(leaderboard_channel)

def calculate_elo(winner_mmr, loser_mmr, k=32):
    expected_win = 1 / (1 + 10 ** ((loser_mmr - winner_mmr) / 400))
    new_winner_mmr = winner_mmr + k * (1 - expected_win)
    new_loser_mmr = loser_mmr + k * (0 - (1 - expected_win))
    return round(new_winner_mmr), round(new_loser_mmr)


MAX_CHARS = 1900  # For safety buffer from Discord's 2000 char limit

async def clear_all_bot_messages(channel):
    def is_bot_message(m):
        return m.author == channel.guild.me
    deleted = await channel.purge(check=is_bot_message)
    print(f"🧹 Cleared {len(deleted)} leaderboard messages.")

async def post_leaderboard(channel):
    # Step 1: Clear old leaderboard messages
    await clear_all_bot_messages(channel)

    # Step 2: Fetch current player MMRs from the database
    conn = sqlite3.connect("mmr.db")
    cursor = conn.cursor()
    cursor.execute("SELECT discord_id, mmr FROM players")
    players = cursor.fetchall()
    conn.close()

    # Step 3: Sort by MMR descending
    players.sort(key=lambda x: x[1], reverse=True)

    # Step 4: Format as a table-style string
    lines = []
    lines.append(f"{'Rank':<5} {'MMR':<5} {'Player':<20}")
    lines.append("-" * 35)

    for idx, (discord_id, mmr) in enumerate(players, start=1):
        user = await channel.guild.fetch_member(int(discord_id))
        name = user.display_name if user else f"User {discord_id}"
        lines.append(f"{idx:<5} {mmr:<5} {name:<20}")

    # Step 5: Chunk messages and send
    message = "```\n"
    for line in lines:
        if len(message) + len(line) + 1 > MAX_CHARS:
            message += "```"
            await channel.send(message)
            message = "```\n"
        message += line + "\n"
    message += "```"
    await channel.send(message)