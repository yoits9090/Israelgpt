"""Community and utility commands cog."""

from __future__ import annotations

import asyncio

import discord
from discord.ext import commands

from db.levels import get_user_stats, get_top_users
from utils import parse_duration


class CommunityCog(commands.Cog, name="Community"):
    """Community features and utility commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="leaderboard", aliases=["lb", "top"])
    async def leaderboard(self, ctx: commands.Context):
        """Show the top 10 chatters by messages and level."""
        rows = get_top_users(ctx.guild.id, limit=10)

        embed = discord.Embed(
            title="📊 Message Leaderboard",
            description="Top 10 members by message count",
            color=0x0000FF,
        )

        for i, row in enumerate(rows, 1):
            user = await self.bot.fetch_user(row["user_id"])
            embed.add_field(
                name=f"{i}. {user.name}",
                value=f"Messages: {row['messages']} | Level: {row['level']}",
                inline=False,
            )

        embed.set_footer(text="Keep chatting to climb the ranks!")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="rank", aliases=["level", "stats"])
    async def rank(self, ctx: commands.Context, member: discord.Member = None):
        """View your or another member's stats."""
        member = member or ctx.author
        stats = get_user_stats(ctx.guild.id, member.id)

        embed = discord.Embed(title=f"{member.display_name}'s Stats", color=0x0000FF)
        embed.add_field(name="Messages", value=stats["messages"], inline=True)
        embed.add_field(name="Level", value=stats["level"], inline=True)
        embed.add_field(name="XP", value=f"{stats['xp']}/100", inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="info")
    async def info(self, ctx: commands.Context):
        """Show server information."""
        embed = discord.Embed(
            title=f"Info for {ctx.guild.name}",
            description="Here is the situation...",
            color=0x0000FF,
        )
        embed.add_field(name="Server Name", value=ctx.guild.name, inline=True)
        embed.add_field(name="Member Count", value=ctx.guild.member_count, inline=True)
        embed.add_field(name="Region", value="The Middle East (probably)", inline=True)
        embed.set_footer(text="Developed with chutzpah")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="avatar", aliases=["av", "pfp"])
    async def avatar(self, ctx: commands.Context, member: discord.Member = None):
        """Display a member's avatar."""
        member = member or ctx.author
        embed = discord.Embed(title=f"{member.display_name}'s Avatar", color=0x0000FF)
        embed.set_image(url=member.display_avatar.url)
        embed.set_footer(text="Have fun!")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="banner")
    async def banner(self, ctx: commands.Context, member: discord.Member = None):
        """Display a member's banner."""
        member = member or ctx.author
        user = await self.bot.fetch_user(member.id)
        if user.banner:
            embed = discord.Embed(title=f"{member.display_name}'s Banner", color=0x0000FF)
            embed.set_image(url=user.banner.url)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"Oy, {member.display_name} doesn't have a banner!")

    @commands.hybrid_command(name="servericon", aliases=["guildicon"])
    async def servericon(self, ctx: commands.Context):
        """Display the server's icon."""
        if ctx.guild.icon:
            embed = discord.Embed(title=f"{ctx.guild.name}'s Icon", color=0x0000FF)
            embed.set_image(url=ctx.guild.icon.url)
            await ctx.send(embed=embed)
        else:
            await ctx.send("This server has no icon, bubbeleh!")

    @commands.hybrid_command(name="serverbanner", aliases=["guildbanner"])
    async def serverbanner(self, ctx: commands.Context):
        """Display the server's banner."""
        if ctx.guild.banner:
            embed = discord.Embed(title=f"{ctx.guild.name}'s Banner", color=0x0000FF)
            embed.set_image(url=ctx.guild.banner.url)
            await ctx.send(embed=embed)
        else:
            await ctx.send("This server has no banner configured.")

    @commands.hybrid_command(name="poll")
    async def poll(self, ctx: commands.Context, *, question_and_options: str | None = None):
        """Create a reaction poll."""
        if question_and_options is None:
            await ctx.send("Provide a question and at least two options using `|` as a separator.")
            return

        segments = [s.strip() for s in question_and_options.split("|") if s.strip()]
        if len(segments) < 3:
            await ctx.send("Format: `,poll What do we eat? | Pizza | Falafel | Sushi`")
            return

        question, options = segments[0], segments[1:]
        if len(options) > 10:
            await ctx.send("Easy there! Maximum of 10 options.")
            return

        emoji_numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        embed = discord.Embed(title=f"📊 {question}", color=0x1ABC9C)
        description_lines = [f"{emoji_numbers[i]} {option}" for i, option in enumerate(options)]
        embed.description = "\n".join(description_lines)
        embed.set_footer(text="React below to vote! Votes update live.")

        message = await ctx.send(embed=embed)
        for i in range(len(options)):
            await message.add_reaction(emoji_numbers[i])

    @commands.hybrid_command(name="remind", aliases=["reminder"])
    async def remind(
        self, ctx: commands.Context, duration: str | None = None, *, reminder: str | None = None
    ):
        """Set a reminder."""
        if duration is None or reminder is None:
            await ctx.send("Usage: `,remind <duration> <message>` e.g. `,remind 15m Drink water`")
            return

        parsed = parse_duration(duration.lower())
        if parsed is None:
            await ctx.send("I couldn't parse that time. Use values like 10m, 2h, or 1d.")
            return

        await ctx.send(f"Reminder set for {duration}. I'll ping you when time's up!")

        await asyncio.sleep(parsed.total_seconds())

        try:
            await ctx.send(f"{ctx.author.mention} ⏰ Reminder: {reminder}")
        except Exception as e:
            print(f"Failed to send reminder: {e}")

    @commands.hybrid_command(name="botresources", aliases=["bleedbot", "greed"])
    async def botresources(self, ctx: commands.Context):
        """Show community bot resources."""
        embed = discord.Embed(
            title="Community bot resources",
            description=(
                "Quick references for popular community tools so you can onboard "
                "new guilds without leaving the chat."
            ),
            color=0x95A5A6,
        )
        embed.add_field(
            name="BleedBot",
            value=(
                "Moderation, logging, and autorole helper. Common commands include `/setup`, `/automod`, "
                "and `/purge`. Full list: https://bleed.bot/commands"
            ),
            inline=False,
        )
        embed.add_field(
            name="Greed (greed.best)",
            value=(
                "Economy and utility bot with games and leaderboards. Popular commands: `/balance`, "
                "`/daily`, `/work`, and `/shop`. Explore more at https://greed.best/commands"
            ),
            inline=False,
        )
        embed.set_footer(text="These links pull the latest docs directly from the bot authors.")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(CommunityCog(bot))
