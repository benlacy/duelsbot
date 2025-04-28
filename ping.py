import discord
from discord.ext import commands
import sqlite3
import logging

PING_NO = 0
PING_PUBLIC = 1
PING_DM = 2

def register_ping_command(bot: commands.Bot):
    # Constants for ping modes


    @bot.command()
    async def ping(ctx, mode: str = None):  # optional 'mode' argument
        user_id = str(ctx.author.id)
        location = "DMs" if isinstance(ctx.channel, discord.DMChannel) else f"#{ctx.channel.name}"
        logging.info(f"User {ctx.author} ({user_id}) used !ping from {location} with mode '{mode}'")

        if not isinstance(ctx.channel, discord.DMChannel) and ctx.channel.name != "queue-here":
            logging.warning(f"User {ctx.author} tried to !ping from #{ctx.channel.name}, which is not allowed.")
            await ctx.send("❌ You can only use `!ping` in DMs or in the #queue-here channel.")
            await ctx.message.delete()
            return

        guild = discord.utils.get(bot.guilds)
        member = guild.get_member(ctx.author.id)

        if not member:
            await ctx.send("❌ Could not verify your account. Please try again later.")
            return

        # Determine ping setting
        ping_value = PING_DM if mode and mode.lower() == "dm" else PING_PUBLIC

        # Check if the player exists
        conn = sqlite3.connect("mmr.db")
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM players WHERE discord_id = ?", (user_id,))
        if not cursor.fetchone():
            await ctx.send("❌ You are not registered. Use `!rankcheck` first.")
            conn.close()
            return

        # Update ping column
        cursor.execute("UPDATE players SET ping = ? WHERE discord_id = ?", (ping_value, user_id))
        conn.commit()
        conn.close()
        logging.info(f"Set ping = {ping_value} for {user_id}")

        # Add ping role if needed
        ping_role = discord.utils.get(guild.roles, name="PING")
        if ping_role:
            await member.add_roles(ping_role)
            logging.info(f"Gave PING role to {user_id}")

        # Send appropriate confirmation
        if ping_value == PING_DM:
            await ctx.send("✅ You will now be **DM'd** for future match opportunities.")
        else:
            await ctx.send("✅ You will now be pinged in **#queue-here** for future matches.")
