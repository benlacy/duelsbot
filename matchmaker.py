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
        # print("\n🔄 Running matchmaking loop...")

        with sqlite3.connect("mmr.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT discord_id, mmr, queue_time, regions FROM players WHERE queue_status = 'IN_QUEUE'")
            queued_players = cursor.fetchall()

        # print(f"📥 {len(queued_players)} players currently in queue")
        # for player in queued_players:
        #     print(f"  - ID: {player[0]}, MMR: {player[1]}, Queued at: {player[2]}, Regions: {player[3]}")

        queued_players.sort(key=lambda x: x[2])  # Sort by queue time (oldest first)
        matched = set()

        for i, (p1_id, p1_mmr, p1_time_str, p1_regions_str) in enumerate(queued_players):
            if p1_id in matched:
                continue

            p1_time = datetime.datetime.fromisoformat(p1_time_str)
            wait_minutes = (datetime.datetime.now(datetime.UTC) - p1_time).total_seconds() / 60
            mmr_range = BASE_RANGE + RANGE_EXPAND_PER_MINUTE * wait_minutes
            p1_regions = set(p1_regions_str.split(','))

            # print(f"🔍 Trying to match player {p1_id} (MMR: {p1_mmr}, Regions: {p1_regions}, Wait: {wait_minutes:.1f} min, Range: ±{mmr_range:.1f})")

            for j in range(i + 1, len(queued_players)):
                p2_id, p2_mmr, p2_time_str, p2_regions_str = queued_players[j]
                if p2_id in matched:
                    continue

                p2_regions = set(p2_regions_str.split(','))
                mmr_diff = abs(p1_mmr - p2_mmr)

                # print(f"   ↪ Checking {p2_id} (MMR: {p2_mmr}, Regions: {p2_regions}, Diff: {mmr_diff})")

                if mmr_diff <= mmr_range and p1_regions & p2_regions:
                    now = datetime.datetime.now(datetime.UTC).isoformat()

                    with sqlite3.connect("mmr.db") as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT INTO matches (player1_id, player2_id, status, created_at) VALUES (?, ?, 'WAITING_CONFIRM', ?)",
                            (p1_id, p2_id, now)
                        )
                        match_id = cursor.lastrowid

                        cursor.execute(
                            "UPDATE players SET queue_status = 'IN_MATCH' WHERE discord_id IN (?, ?)",
                            (p1_id, p2_id)
                        )
                        conn.commit()

                    matched.update({p1_id, p2_id})
                    matched_regions = sorted(p1_regions & p2_regions)

                    print(f"✅ Matched {p1_id} and {p2_id} in regions {matched_regions} (match_id: {match_id})")

                    guild = bot.get_guild(FEER_GUILD_ID)
                    queue_channel = discord.utils.get(guild.text_channels, name="queue-here")
                    if queue_channel:
                        await queue_channel.send("🔔 A match has been found! Check your DMs to see if it's you.")

                    bot.loop.create_task(send_match_confirmation(bot, match_id, p1_id, p2_id, matched_regions))
                    break  # done with p1

        # Timeout check
        TIMEOUT_MINUTES = 60
        now = datetime.datetime.now(datetime.UTC)
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
                    await user.send("⏳ You were removed from the queue after waiting 60 minutes without a match.")
                except Exception as dm_error:
                    print(f"⚠️ Could not DM {p_id}: {dm_error}")
                    
    # except Exception as e:
    #     print(f"⚠️ Matchmaker error: {e}")



CONFIRM_TIMEOUT = 420  # 7 minutes

async def send_match_confirmation(bot, match_id, player1_id, player2_id, matched_regions):
        print(f"[MATCH {match_id}] ➤ Starting match confirmation between {player1_id} and {player2_id} in regions: {matched_regions}")
        
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
            print(f"[MATCH {match_id}] ➤ Sending DM to user {pid}")
            user = await bot.fetch_user(int(pid))
            msg = await user.send(embed=make_embed())
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")
            confirmed[pid] = None # Placeholder for reaction
            messages[pid] = msg
            print(f"[MATCH {match_id}] ✅ Sent match confirmation to {user.name} ({pid})")

        def check(reaction, user):
            try:
                if user.id not in messages:
                    print(f"[MATCH {match_id}] ⚠️ Ignoring reaction from user {user.id}, not a match participant")
                    return False
                print(f"[MATCH {match_id}] 🔍 Reaction received: {user.id} on message {reaction.message.id}")
                return (
                    str(reaction.emoji) in ["✅", "❌"]
                    and user.id in player_ids
                    and reaction.message.id == messages[user.id].id
                )
            except Exception as check_error:
                print(f"[MATCH {match_id}] ⚠️ Error in check function: {check_error}")
                return False

        while True:
            try:
                print(f"[MATCH {match_id}] ⏳ Waiting for reaction (timeout in {CONFIRM_TIMEOUT}s)...")
                reaction, user = await bot.wait_for("reaction_add", timeout=CONFIRM_TIMEOUT, check=check)
                emoji = str(reaction.emoji)
                user_id = user.id
                print(f"[MATCH {match_id}] 🔁 Reaction: {user_id} reacted with {emoji}")

                if confirmed[user_id] is not None:
                    print(f"[MATCH {match_id}] ⏭️ Ignoring duplicate reaction from {user_id}")
                    continue

                confirmed[user_id] = emoji

                if emoji == "❌":
                    # Cancel immediately
                    print(f"[MATCH {match_id}] ❌ Match canceled by {user_id}")
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
                    print(f"[MATCH {match_id}] ✅ All players responded. Proceeding...")
                    break

            except asyncio.TimeoutError:
                print(f"[MATCH {match_id}] ⏰ Confirmation timed out.")
                conn = sqlite3.connect("mmr.db")
                cursor = conn.cursor()
                cursor.execute("DELETE FROM matches WHERE match_id = ?", (match_id,))

                for pid in player_ids:
                    if confirmed[pid] is None:
                        # Did not react – mark as idle
                        print(f"[MATCH {match_id}] ⏰ Timeout: {pid} to idle")
                        cursor.execute("UPDATE players SET queue_status = 'IDLE' WHERE discord_id = ?", (pid,))
                    else:
                        # Reacted – still interested, return to queue
                        print(f"[MATCH {match_id}] ⏰ Timeout: {pid} to IN_QUEUE")
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

        # Both confirmed
        print(f"[MATCH {match_id}] ✅ Both players confirmed. Creating match channel...")
        conn = sqlite3.connect("mmr.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE matches SET status = 'CONFIRMED' WHERE match_id = ?", (match_id,))
        conn.commit()
        conn.close()

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

        category = discord.utils.get(guild.categories, name="Feer Duels - 2mans")
        match_channel = await guild.create_text_channel(
            name=f"match-{match_id}",
            overwrites=overwrites,
            category=category
        )

        print(f"[MATCH {match_id}] 📺 Created channel #{match_channel.name} (ID: {match_channel.id})")

        conn = sqlite3.connect("mmr.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE matches SET channel_id = ? WHERE match_id = ?", (match_channel.id, match_id))
        conn.commit()
        conn.close()

        match_name = f"duel{match_id}"
        match_password = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
        host = p1.display_name if random.choice([True, False]) else p2.display_name
        print(f"[MATCH {match_id}] 🧩 Match setup: name={match_name}, pass={match_password}, host={host}")

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
            print(f"[MATCH {match_id}] ✉️ Sent final DM to {user.name} ({pid})")

