from discord.ext import commands
import discord
import sqlite3
import logging
from utils import get_rank

def register_report_command(bot: commands.Bot):
    @bot.command()
    async def report(ctx, match_id: int, result: str):
        logging.info(f"📥 Received report command from {ctx.author} for match {match_id} with result '{result}'")

        # Only respond if used in #score-report
        if ctx.channel.name != "score-report":
            logging.info("🚫 Command not used in #score-report channel.")
            return

        await ctx.message.add_reaction("⏳")

        # Validate result
        result = result.upper()
        if result not in ["W", "L", "C"]:
            logging.warning("⚠️ Invalid result provided.")
            await ctx.send("⚠️ Invalid result. Use `W` for win or `L` for loss. `C` cancels the match")
            await ctx.message.add_reaction("⚠️")
            return

        user_id = str(ctx.author.id)
        logging.info(f"🔍 Looking up match {match_id} in database.")

        # Fetch match
        conn = sqlite3.connect("mmr.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT player1_id, player2_id, winner_id FROM matches WHERE match_id = ? AND status = 'CONFIRMED'",
            (match_id,)
        )
        row = cursor.fetchone()

        if not row:
            logging.warning("❌ No match found or match not in CONFIRMED status.")
            await ctx.send("❌ Match ID not found, or not active")
            await ctx.message.add_reaction("❌")
            conn.close()
            return

        p1_id, p2_id, winner_id = row
        logging.info(f"✅ Match found: p1={p1_id}, p2={p2_id}, winner={winner_id}")

        # Check if user is a participant or a moderator (only for cancellation)
        is_participant = str(p1_id) == user_id or str(p2_id) == user_id
        is_moderator = discord.utils.get(ctx.author.roles, name="Moderator") is not None

        if not is_participant and not (result == "C" and is_moderator):
            logging.warning("❌ User is not a participant in this match and not authorized to cancel.")
            await ctx.send("❌ You are not a participant in this match.")
            await ctx.message.add_reaction("❌")
            conn.close()
            return
        
        if winner_id is not None:
            logging.warning("⚠️ Match already reported.")
            await ctx.send("⚠️ This match has already been reported.")
            await ctx.message.add_reaction("⚠️")
            conn.close()
            return

        if result == "C":
            # Update match result
            logging.info("🛑 Cancelling match.")
            cursor.execute(
                "UPDATE matches SET status = 'CANCELED' WHERE match_id = ?",
                (match_id,)
            )
            # Set both players' status to IDLE
            cursor.execute(
                "UPDATE players SET queue_status = 'IDLE' WHERE discord_id IN (?, ?)",
                (p1_id, p2_id)
            )
            await ctx.send(f"✅ Cancellation for match `{match_id}` recorded: <@{p1_id}> <@{p2_id}> status reset")
            await ctx.message.add_reaction("✅")
            conn.commit()
            conn.close()

            # Fetch and delete match channel
            match_channel_id = None
            try:
                conn = sqlite3.connect("mmr.db")
                cursor = conn.cursor()
                cursor.execute("SELECT channel_id FROM matches WHERE match_id = ?", (match_id,))
                result = cursor.fetchone()
                if result:
                    match_channel_id = result[0]
                    logging.info(f"📺 Found match channel ID: {match_channel_id}")
                conn.close()
            except Exception as e:
                logging.error(f"⚠️ Error fetching match channel for deletion: {e}")

            if match_channel_id:
                match_channel = bot.get_channel(match_channel_id)
                if match_channel:
                    try:
                        await match_channel.delete(reason="Match reported")
                        logging.info("🗑️ Match channel deleted.")
                    except discord.Forbidden:
                        logging.error("⚠️ Missing permissions to delete match channel.")
            return

        if result == "W":
            new_winner_id = user_id
            new_loser_id = str(p1_id) if str(p2_id) == user_id else str(p2_id)
        else: # result == "L"
            new_loser_id = user_id
            new_winner_id = str(p1_id) if str(p2_id) == user_id else str(p2_id)
        logging.info(f"🏆 Winner: {new_winner_id}, Loser: {new_loser_id}")

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
        logging.info(f"📊 MMRs: Winner={winner_mmr}, Loser={loser_mmr}")

        # Calculate new MMRs
        new_winner_mmr, new_loser_mmr = calculate_elo(winner_mmr, loser_mmr)
        logging.info(f"📈 New MMRs: Winner={new_winner_mmr}, Loser={new_loser_mmr}")

        # Update MMRs, Wins, and Losses
        cursor.execute("""
            UPDATE players
            SET mmr = ?, wins = wins + 1
            WHERE discord_id = ?
        """, (new_winner_mmr, new_winner_id))

        cursor.execute("""
            UPDATE players
            SET mmr = ?, losses = losses + 1
            WHERE discord_id = ?
        """, (new_loser_mmr, new_loser_id))

        # Set both players' status to IDLE
        cursor.execute(
            "UPDATE players SET queue_status = 'IDLE' WHERE discord_id IN (?, ?)",
            (p1_id, p2_id)
        )

        conn.commit()
        conn.close()
        logging.info("💾 Match and player stats updated in database.")

        await ctx.send(f"✅ Result for match `{match_id}` recorded: <@{new_winner_id}> wins!")
        await ctx.message.add_reaction("✅")

        # Fetch and delete match channel
        match_channel_id = None
        try:
            conn = sqlite3.connect("mmr.db")
            cursor = conn.cursor()
            cursor.execute("SELECT channel_id FROM matches WHERE match_id = ?", (match_id,))
            result = cursor.fetchone()
            if result:
                match_channel_id = result[0]
                logging.info(f"📺 Found match channel ID: {match_channel_id}")
            conn.close()
        except Exception as e:
            logging.error(f"⚠️ Error fetching match channel for deletion: {e}")

        if match_channel_id:
            match_channel = bot.get_channel(match_channel_id)
            if match_channel:
                try:
                    await match_channel.delete(reason="Match reported")
                    logging.info("🗑️ Match channel deleted.")
                except discord.Forbidden:
                    logging.error("⚠️ Missing permissions to delete match channel.")

        await update_player_role(ctx, new_winner_id, new_winner_mmr)
        await update_player_role(ctx, new_loser_id, new_loser_mmr)

        leaderboard_channel = discord.utils.get(bot.get_all_channels(), name="leaderboard")
        if leaderboard_channel:
            logging.info("📢 Posting updated leaderboard...")
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
    logging.info(f"🧹 Cleared {len(deleted)} leaderboard messages.")

def register_leaderboard_command(bot: commands.Bot):
    @bot.command()
    async def leaderboard(ctx):
        if ctx.channel.name != "leaderboard":
            return
        
        await post_leaderboard(ctx.channel)
        

async def post_leaderboard(channel):
    await clear_all_bot_messages(channel)

    conn = sqlite3.connect("mmr.db")
    cursor = conn.cursor()
    cursor.execute("SELECT discord_id, mmr, wins, losses FROM players WHERE wins > 0 OR losses > 0")
    players = cursor.fetchall()
    conn.close()

    # Sort by MMR descending
    players.sort(key=lambda x: x[1], reverse=True)

    # Group players by rank
    from collections import defaultdict
    rank_groups = defaultdict(list)
    for player in players:
        rank = get_rank(player[1])
        rank_groups[rank].append(player)

    # Define rank display order
    rank_order = ["Rank S", "Rank X", "Rank A", "Rank B", "Rank C", "Rank D"]

    lines = []
    lines.append(f"{'Rank':<5} {'MMR':<5} {'W':<3} {'L':<3} {'Player':<20}")
    lines.append("-" * 45)
    for rank in rank_order:
        group = rank_groups.get(rank)
        if not group:
            continue

        lines.append(f"--------------{rank}--------------")
        
        for idx, (discord_id, mmr, wins, losses) in enumerate(group, start=1):
            try:
                user = await channel.guild.fetch_member(int(discord_id))
                name = user.display_name if user else f"User {discord_id}"
                lines.append(f"{idx:<5} {mmr:<5} {wins:<3} {losses:<3} {name:<20}")
            except:
                logging.warning(f"{discord_id} user doesn't exist anymore")

    # Send chunked messages
    message = "```\n"
    for line in lines:
        if len(message) + len(line) + 1 > MAX_CHARS:
            message += "```"
            await channel.send(message)
            message = "```\n"
        message += line + "\n"
    message += "```"
    await channel.send(message)

async def update_player_role(ctx, player_id, player_mmr):
    # Determine new rank
    new_rank = get_rank(player_mmr)
    guild = ctx.guild
    member = guild.get_member(int(player_id)) or await guild.fetch_member(int(player_id))

    if not member:
        return

    # Find the current rank role
    current_rank_role = next((r for r in member.roles if r.name.startswith("Rank ")), None)

    # If the rank hasn't changed, bail
    if current_rank_role and current_rank_role.name == new_rank:
        return  # No update needed

    # Find the new rank role object
    new_rank_role = discord.utils.get(guild.roles, name=new_rank)

    # Determine promotion or demotion
    rank_order = ["Rank D", "Rank C", "Rank B", "Rank A", "Rank X", "Rank S"]
    old_index = rank_order.index(current_rank_role.name) if current_rank_role else -1
    new_index = rank_order.index(new_rank)

    # Remove old rank role (if it exists)
    if current_rank_role:
        try:
            await member.remove_roles(current_rank_role)
        except discord.Forbidden:
            await ctx.send("⚠️ I don’t have permission to remove some roles.")

    # Add new rank role
    try:
        if new_rank_role:
            await member.add_roles(new_rank_role)
    except discord.Forbidden:
        await ctx.send(f"⚠️ {member.mention} I don’t have permission to assign the role **{new_rank}**.")
        return

    # Send message to user
    if new_index > old_index:
        await ctx.send(f"📈 {member.mention} has been **promoted** to **{new_rank}**!")
    elif new_index < old_index:
        await ctx.send(f"📉 {member.mention} has been **demoted** to **{new_rank}**!")
    else:
        await ctx.send(f"🎯 {member.mention} is now **{new_rank}**!")


