import discord
from discord.ext import commands
import sqlite3
import logging
from ping import PING_NO

def register_mute_command(bot: commands.Bot):
    @bot.command()
    async def mute(ctx):
        user_id = str(ctx.author.id)
        location = "DMs" if isinstance(ctx.channel, discord.DMChannel) else f"#{ctx.channel.name}"
        logging.info(f"User {ctx.author} ({user_id}) used !mute from {location}")

        # Disallow using the command in public channels except #queue-here
        if not isinstance(ctx.channel, discord.DMChannel) and ctx.channel.name != "queue-here":
            logging.warning(f"User {ctx.author} tried to !mute from #{ctx.channel.name}, which is not allowed.")
            await ctx.send("❌ You can only use `!mute` in DMs or in the #queue-here channel.")
            await ctx.message.delete()
            return

        # Get the member and guild
        guild = discord.utils.get(bot.guilds)
        member = guild.get_member(ctx.author.id)

        if not member:
            await ctx.send("❌ Could not verify your account. Please try again later.")
            return

        # Check if the player exists in the database
        conn = sqlite3.connect("mmr.db")
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM players WHERE discord_id = ?", (user_id,))
        if not cursor.fetchone():
            await ctx.send("❌ You are not registered. Use `!rankcheck` first.")
            conn.close()
            return

        # Update ping column
        cursor.execute("UPDATE players SET ping = ? WHERE discord_id = ?", (PING_NO, user_id,))
        conn.commit()
        conn.close()
        logging.info(f"Set ping = {PING_NO} for {user_id}")

        # Remove ping role
        ping_role = discord.utils.get(guild.roles, name="PING")
        if ping_role and ping_role in member.roles:
            await member.remove_roles(ping_role)
            await ctx.send("🔇 You have been muted from match pings.")
            logging.info(f"Removed Ping role from {user_id}")
        else:
            await ctx.send("ℹ️ You weren’t being pinged anyway.")
