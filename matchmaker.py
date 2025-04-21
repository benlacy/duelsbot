import asyncio
import sqlite3
import datetime
import discord
from discord import Embed
import random
import string

from utils import FEER_GUILD_ID

EXPAND_INTERVAL_SECONDS = 60
BASE_RANGE = 160 #50
RANGE_EXPAND_PER_MINUTE = 2#25

async def matchmaking_loop(bot):
    await bot.wait_until_ready()
    while not bot.is_closed():
        await run_matchmaking(bot)
        await asyncio.sleep(EXPAND_INTERVAL_SECONDS)

async def run_matchmaking(bot):
    # try:
        with sqlite3.connect("mmr.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT discord_id, mmr, queue_time, regions FROM players WHERE queue_status = 'IN_QUEUE'")
            queued_players = cursor.fetchall()

        queued_players.sort(key=lambda x: x[2])  # Sort by queue time (oldest first)

        matched = set()  # Keep track of matched players to avoid double matching

        # 2. Start trying to match players
        for i, (p1_id, p1_mmr, p1_time_str, p1_regions_str) in enumerate(queued_players):
            if p1_id in matched:
                continue  # Skip if this player is already matched

            p1_time = datetime.datetime.fromisoformat(p1_time_str)  # Convert the queue time from string to datetime
            wait_minutes = (datetime.datetime.now(datetime.UTC) - p1_time).total_seconds() / 60  # How long they've been queued (in minutes)
            mmr_range = BASE_RANGE + RANGE_EXPAND_PER_MINUTE * wait_minutes  # Calculate allowable MMR range

            # Split the regions
            p1_regions = set(p1_regions_str.split(','))

            # 3. Try to find a player that can match with p1 (based on MMR range)
            for j in range(i + 1, len(queued_players)):
                p2_id, p2_mmr, p2_time_str, p2_regions_str = queued_players[j]
                if p2_id in matched:
                    continue  # Skip if p2 is already matched

                # Split the regions
                p2_regions = set(p2_regions_str.split(','))

                # Check if the MMR difference is within the acceptable range
                print(f"🔁 Checking mmr diff {abs(p1_mmr - p2_mmr)} is inside {mmr_range} (and regions match)")
                if abs(p1_mmr - p2_mmr) <= mmr_range and p1_regions & p2_regions:
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

                    matched_regions = sorted(p1_regions & p2_regions)
                    print(f"🔁 Matched {p1_id} and {p2_id} in {matched_regions}")
                    
                    guild = bot.get_guild(FEER_GUILD_ID)
                    queue_channel = discord.utils.get(guild.text_channels, name="queue-here")
                    if queue_channel:
                        await queue_channel.send(
                            f"🔔 A match has been found! Check your DMs to see if its you"
                        )


                    bot.loop.create_task(send_match_confirmation(bot, match_id, p1_id, p2_id, matched_regions))

                    break  # Stop searching for a match for player 1
        
        TIMEOUT_MINUTES = 60  # 60-minute timeout
        now = datetime.datetime.now(datetime.UTC)

        # Remove players who have been queued too long
        for player in queued_players:
            p_id, _, p_time_str, _ = player
            p_time = datetime.datetime.fromisoformat(p_time_str)
            wait_minutes = (now - p_time).total_seconds() / 60

            if wait_minutes >= TIMEOUT_MINUTES:
                print(f"⏳ Removing player {p_id} from queue due to timeout ({wait_minutes:.1f} min)")
                with sqlite3.connect("mmr.db") as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE players SET queue_status = 'IDLE' WHERE discord_id = ?", (p_id,))
                    conn.commit()

                try:
                    user = await bot.fetch_user(int(p_id))
                    await user.send("⏳ You were removed from the queue after waiting 60 minutes without a match. Please re-queue with `!q` if you're still around!")
                except Exception as dm_error:
                    print(f"⚠️ Could not DM {p_id}: {dm_error}")

                    
    # except Exception as e:
    #     print(f"⚠️ Matchmaker error: {e}")



CONFIRM_TIMEOUT = 420  # 7 minutes

async def send_match_confirmation(bot, match_id, player1_id, player2_id, matched_regions):
    # try:
        guild = bot.get_guild(FEER_GUILD_ID)
        player_ids = [player1_id, player2_id]
        confirmed = {}
        messages = {}

        def make_embed():
            return Embed(
                title="🎮 Match Found!",
                description=(
                    f"React with ✅ to confirm or ❌ to cancel.\n"
                    f"You have {CONFIRM_TIMEOUT/60} minutes.\n\n"
                    f"**Matched Region(s):** {', '.join(matched_regions)}"
                ),
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
                    if confirmed[pid] is None:
                        # Did not react – mark as idle
                        cursor.execute("UPDATE players SET queue_status = 'IDLE' WHERE discord_id = ?", (pid,))
                    else:
                        # Reacted – still interested, return to queue
                        cursor.execute("UPDATE players SET queue_status = 'IN_QUEUE' WHERE discord_id = ?", (pid,))
                conn.commit()
                conn.close()

                for pid in player_ids:
                    user = await bot.fetch_user(int(pid))
                    if confirmed[pid] is None:
                        await user.send("⏰ Match timed out. You didn't respond in time and have been marked as idle.")
                    else:
                        await user.send("⏰ Match timed out. Your opponent didn’t confirm, so you’ve been returned to the queue.")
                return

        # Both confirmed ✅
        conn = sqlite3.connect("mmr.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE matches SET status = 'CONFIRMED' WHERE match_id = ?", (match_id,))
        conn.commit()
        conn.close()

        # Create match channel
        guild = bot.get_guild(FEER_GUILD_ID)
        p1 = guild.get_member(int(player1_id))
        p2 = guild.get_member(int(player2_id))

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            p1: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            p2: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }

        mod_role = discord.utils.get(guild.roles, name="Mod")
        if mod_role:
            overwrites[mod_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        category = discord.utils.get(guild.categories, name="Feer Duels - 2mans")  # Optional
        match_channel = await guild.create_text_channel(
            name=f"match-{match_id}",
            overwrites=overwrites,
            category=category
        )

        # Save channel ID in DB
        conn = sqlite3.connect("mmr.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE matches SET channel_id = ? WHERE match_id = ?", (match_channel.id, match_id))
        conn.commit()
        conn.close()

        match_name = f"duel{match_id}"
        match_password = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
        host = p1.display_name if random.choice([True, False]) else p2.display_name

        score_report_channel = discord.utils.get(guild.text_channels, name="score-report")

        await match_channel.send(
            f"🎮 **Match `{match_id}` Confirmed!**\n"
            f"🏟️ Private Match Name: `{match_name}`\n"
            f"🔐 Password: `{match_password}`\n"
            f"🧑‍💻 Host: **{host}**, please create the match!\n"
            f"🌎 Regions: {', '.join(matched_regions)}\n"
            f"\nThis match is a **Best of 3**.\n"
            f"Once complete, one of you should report the result in <#{score_report_channel.id}> using:\n"
            f"`!report {match_id} W` or `!report {match_id} L`\n\n"
            f"Good luck!"
        )

        for pid in player_ids:
            user = await bot.fetch_user(int(pid))
            await user.send(
                f"✅ Match confirmed! Head to {match_channel.mention} for match setup info. GLHF 🎮"
            )

    # except Exception as e:
    #     print(f"⚠️ Error in send_match_confirmation: {e}")
