import asyncio
import sqlite3
import datetime
import discord
from discord import Embed

from utils import FEER_GUILD_ID

EXPAND_INTERVAL_SECONDS = 60
BASE_RANGE = 50
RANGE_EXPAND_PER_MINUTE = 25

async def matchmaking_loop(bot):
    await bot.wait_until_ready()
    while not bot.is_closed():
        await run_matchmaking(bot)
        await asyncio.sleep(EXPAND_INTERVAL_SECONDS)

async def run_matchmaking(bot):
    # try:
        with sqlite3.connect("mmr.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT discord_id, mmr, queue_time FROM players WHERE queue_status = 'IN_QUEUE'")
            queued_players = cursor.fetchall()

        queued_players.sort(key=lambda x: x[2])  # Sort by queue time (oldest first)

        matched = set()  # Keep track of matched players to avoid double matching

        # 2. Start trying to match players
        for i, (p1_id, p1_mmr, p1_time_str) in enumerate(queued_players):
            if p1_id in matched:
                continue  # Skip if this player is already matched

            p1_time = datetime.datetime.fromisoformat(p1_time_str)  # Convert the queue time from string to datetime
            wait_minutes = (datetime.datetime.now(datetime.UTC) - p1_time).total_seconds() / 60  # How long they've been queued (in minutes)
            mmr_range = BASE_RANGE + RANGE_EXPAND_PER_MINUTE * wait_minutes  # Calculate allowable MMR range

            # 3. Try to find a player that can match with p1 (based on MMR range)
            for j in range(i + 1, len(queued_players)):
                p2_id, p2_mmr, p2_time_str = queued_players[j]
                if p2_id in matched:
                    continue  # Skip if p2 is already matched

                # Check if the MMR difference is within the acceptable range
                if abs(p1_mmr - p2_mmr) <= mmr_range:
                    now = datetime.datetime.now(datetime.UTC).isoformat()  # Get current time for match creation

                    with sqlite3.connect("mmr.db") as conn:
                        cursor = conn.cursor()
                        # 4. Insert the match into the 'matches' table
                        cursor.execute(
                            "INSERT INTO matches (player1_id, player2_id, status, created_at) VALUES (?, ?, 'WAITING_CONFIRM', ?)",
                            (p1_id, p2_id, now)
                        )
                        match_id = cursor.lastrowid

                        # 5. Update players' status to "IN_MATCH"
                        cursor.execute(
                            "UPDATE players SET queue_status = 'IN_MATCH' WHERE discord_id IN (?, ?)",
                            (p1_id, p2_id)
                        )
                        conn.commit()

                    # 6. Mark both players as matched
                    matched.update({p1_id, p2_id})

                    print(f"🔁 Matched {p1_id} and {p2_id}")

                    bot.loop.create_task(send_match_confirmation(bot, match_id, p1_id, p2_id))

                    break  # Stop searching for a match for player 1

    # except Exception as e:
    #     print(f"⚠️ Matchmaker error: {e}")



CONFIRM_TIMEOUT = 120  # 2 minutes

async def send_match_confirmation(bot, match_id, player1_id, player2_id):
    # try:
        guild = bot.get_guild(FEER_GUILD_ID)
        player_ids = [player1_id, player2_id]
        confirmed = {}
        messages = {}

        def make_embed():
            return Embed(
                title="🎮 Match Found!",
                description="React with ✅ to confirm or ❌ to cancel.\nYou have 2 minutes.",
                color=discord.Color.green()
            )

        # Send DM to each player
        for pid in player_ids:
            user = await bot.fetch_user(int(pid))
            msg = await user.send(embed=make_embed())
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")
            confirmed[pid] = None  # Placeholder for reaction
            messages[pid] = msg

        def check(reaction, user):
            try:
                # Ignore if user isn't in messages dict
                if user.id not in messages:
                    print(f"⚠️ Ignoring reaction from user {user.id}, not in match participants")
                    return False

                print(f"🧪 Checking reaction from {user.id} on message {reaction.message.id}, expected {messages[user.id].id}")
                return (
                    str(reaction.emoji) in ["✅", "❌"]
                    and user.id in player_ids
                    and reaction.message.id == messages[user.id].id
                )
            except Exception as check_error:
                print(f"⚠️ Error inside check function: {check_error}")
                return False

        while True:
            try:
                print("✅ Waiting for reactions on message IDs:")
                # for pid, data in confirmed.items():
                #     print(f"  {pid}: {data['message'].id}")

                reaction, user = await bot.wait_for("reaction_add", timeout=CONFIRM_TIMEOUT, check=check)
                emoji = str(reaction.emoji)
                user_id = user.id

                print(f"🔁 REACTION {user_id} reacted {emoji}")

                if confirmed[user_id] is not None:
                    continue  # Ignore duplicate reactions

                confirmed[user_id] = emoji

                if emoji == "❌":
                    # Cancel immediately
                    canceler_id = user_id
                    other_id = next(pid for pid in player_ids if pid != canceler_id)

                    # Update database
                    conn = sqlite3.connect("mmr.db")
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM matches WHERE match_id = ?", (match_id,))
                    cursor.execute("UPDATE players SET queue_status = 'IDLE' WHERE discord_id = ?", (canceler_id,))
                    cursor.execute("UPDATE players SET queue_status = 'IN_QUEUE' WHERE discord_id = ?", (other_id,))
                    conn.commit()
                    conn.close()

                    # Notify players
                    canceler = await bot.fetch_user(int(canceler_id))
                    other = await bot.fetch_user(int(other_id))
                    await canceler.send("❌ You canceled the match. You've been removed from the queue.")
                    await other.send("🔁 Your opponent canceled. You've been returned to the queue.")
                    return

                elif emoji == "✅":
                    await user.send("✅ Confirmed! Waiting for your opponent...")

                if all(r in ["✅", "❌"] for r in confirmed.values()):
                    break

            except asyncio.TimeoutError:
                # Match expired
                conn = sqlite3.connect("mmr.db")
                cursor = conn.cursor()
                cursor.execute("DELETE FROM matches WHERE match_id = ?", (match_id,))
                for pid in player_ids:
                    cursor.execute("UPDATE players SET queue_status = 'IN_QUEUE' WHERE discord_id = ?", (pid,))
                conn.commit()
                conn.close()

                for pid in player_ids:
                    user = await bot.fetch_user(int(pid))
                    await user.send("⏰ Match timed out. You've been returned to the queue.")
                return

        # Both confirmed ✅
        conn = sqlite3.connect("mmr.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE matches SET status = 'CONFIRMED' WHERE match_id = ?", (match_id,))
        conn.commit()
        conn.close()

        for pid in player_ids:
            user = await bot.fetch_user(int(pid))
            await user.send("✅ Match confirmed! GLHF 🎮")

    # except Exception as e:
    #     print(f"⚠️ Error in send_match_confirmation: {e}")
