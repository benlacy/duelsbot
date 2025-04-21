from discord.ext import commands
import discord
import sqlite3
from utils import get_rank

def register_report_command(bot: commands.Bot):
    @bot.command()
    async def report(ctx, match_id: int, result: str):
        print(f"📥 Received report command from {ctx.author} for match {match_id} with result '{result}'")

        # Only respond if used in #score-report
        if ctx.channel.name != "score-report":
            print("🚫 Command not used in #score-report channel.")
            return

        await ctx.message.add_reaction("⏳")

        # Validate result
        result = result.upper()
        if result not in ["W", "L", "C"]:
            print("⚠️ Invalid result provided.")
            await ctx.send("⚠️ Invalid result. Use `W` for win or `L` for loss. `C` cancels the match")
            await ctx.message.add_reaction("⚠️")
            return

        user_id = str(ctx.author.id)
        print(f"🔍 Looking up match {match_id} in database.")

        # Fetch match
        conn = sqlite3.connect("mmr.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT player1_id, player2_id, winner_id FROM matches WHERE match_id = ? AND status = 'CONFIRMED'",
            (match_id,)
        )
        row = cursor.fetchone()

        if not row:
            print("❌ No match found or match not in CONFIRMED status.")
            await ctx.send("❌ Match ID not found, or not active")
            await ctx.message.add_reaction("❌")
            conn.close()
            return

        p1_id, p2_id, winner_id = row
        print(f"✅ Match found: p1={p1_id}, p2={p2_id}, winner={winner_id}")

        if str(p1_id) != user_id and str(p2_id) != user_id:
            print("❌ User is not a participant in this match.")
            await ctx.send("❌ You are not a participant in this match.")
            await ctx.message.add_reaction("❌")
            conn.close()
            return

        if winner_id is not None:
            print("⚠️ Match already reported.")
            await ctx.send("⚠️ This match has already been reported.")
            await ctx.message.add_reaction("⚠️")
            conn.close()
            return

        if result == "C":
            # Update match result
            print("🛑 Cancelling match.")
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
                    print(f"📺 Found match channel ID: {match_channel_id}")
                conn.close()
            except Exception as e:
                print(f"⚠️ Error fetching match channel for deletion: {e}")

            if match_channel_id:
                match_channel = bot.get_channel(match_channel_id)
                if match_channel:
                    try:
                        await match_channel.delete(reason="Match reported")
                        print("🗑️ Match channel deleted.")
                    except discord.Forbidden:
                        print("⚠️ Missing permissions to delete match channel.")
            return

        if result == "W":
            new_winner_id = user_id
            new_loser_id = str(p1_id) if str(p2_id) == user_id else str(p2_id)
        else: # result == "L"
            new_loser_id = user_id
            new_winner_id = str(p1_id) if str(p2_id) == user_id else str(p2_id)
        print(f"🏆 Winner: {new_winner_id}, Loser: {new_loser_id}")

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
        print(f"📊 MMRs: Winner={winner_mmr}, Loser={loser_mmr}")

        # Calculate new MMRs
        new_winner_mmr, new_loser_mmr = calculate_elo(winner_mmr, loser_mmr)
        print(f"📈 New MMRs: Winner={new_winner_mmr}, Loser={new_loser_mmr}")

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
        print("💾 Match and player stats updated in database.")

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
                print(f"📺 Found match channel ID: {match_channel_id}")
            conn.close()
        except Exception as e:
            print(f"⚠️ Error fetching match channel for deletion: {e}")

        if match_channel_id:
            match_channel = bot.get_channel(match_channel_id)
            if match_channel:
                try:
                    await match_channel.delete(reason="Match reported")
                    print("🗑️ Match channel deleted.")
                except discord.Forbidden:
                    print("⚠️ Missing permissions to delete match channel.")

        await update_player_role(ctx, new_winner_id, new_winner_mmr)
        await update_player_role(ctx, new_loser_id, new_loser_mmr)

        leaderboard_channel = discord.utils.get(bot.get_all_channels(), name="leaderboard")
        if leaderboard_channel:
            print("📢 Posting updated leaderboard...")
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

def register_leaderboard_command(bot: commands.Bot):
    @bot.command()
    async def leaderboard(ctx):
        if ctx.channel.name != "leaderboard":
            return
        
        await post_leaderboard(ctx.channel)
        

async def post_leaderboard(channel):
    # Step 1: Clear old leaderboard messages
    await clear_all_bot_messages(channel)

    # Step 2: Fetch current player MMRs from the database
    conn = sqlite3.connect("mmr.db")
    cursor = conn.cursor()
    cursor.execute("SELECT discord_id, mmr, wins, losses FROM players WHERE wins > 0 OR losses > 0")
    players = cursor.fetchall()
    conn.close()

    # Step 3: Sort by MMR descending
    players.sort(key=lambda x: x[1], reverse=True)

    # Step 4: Format as a table-style string
    lines = []
    lines.append(f"{'Rank':<5} {'MMR':<5} {'W':<3} {'L':<3} {'Player':<20}")
    lines.append("-" * 45)

    for idx, (discord_id, mmr, wins, losses) in enumerate(players, start=1):
        try:
            user = await channel.guild.fetch_member(int(discord_id))
            name = user.display_name if user else f"User {discord_id}"
            lines.append(f"{idx:<5} {mmr:<5} {wins:<3} {losses:<3} {name:<20}")
        except:
            #TODO Prune this user from the database, probably, or skip them somehow
            print(f"{discord_id} user doesnt exist anymore")

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


