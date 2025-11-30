"""ChronoNation Economy Cog - Player commands for the economy simulation."""

import random
from datetime import datetime, timedelta
from typing import Optional

import discord
from discord.ext import commands, tasks

from db.economy import get_or_create_nation
from economy_service import EconomyService
from services.economy import process_year_tick


CLASS_EMOJI = {
    "working": "🧱",
    "middle": "🏢",
    "elite": "🏰",
}


class EconomyCog(commands.Cog, name="Economy"):
    """ChronoNation economy system - 1 day = 1 year simulation."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.service = EconomyService()
        self.year_tick_loop.start()

    def cog_unload(self):
        self.year_tick_loop.cancel()

    @tasks.loop(hours=24)
    async def year_tick_loop(self):
        """Run year tick for all guilds at midnight."""
        for guild in self.bot.guilds:
            try:
                result = await process_year_tick(guild.id)
                
                # Find a channel to post the summary
                channel = discord.utils.get(guild.text_channels, name="nation-history")
                if not channel:
                    channel = guild.system_channel
                
                if channel and result.history_entries:
                    nation = get_or_create_nation(guild.id)
                    embed = discord.Embed(
                        title=f"📜 Year {result.year} - {nation['name']}",
                        description=result.history_entries[0],
                        color=discord.Color.gold(),
                    )
                    
                    if result.events:
                        events_str = "\n".join(f"• {e['name']}" for e in result.events)
                        embed.add_field(name="📰 Events", value=events_str, inline=False)
                    
                    if result.deaths:
                        embed.add_field(
                            name="⚰️ Deaths", 
                            value=f"{len(result.deaths)} citizen(s)",
                            inline=True
                        )
                    
                    if result.elections_triggered:
                        embed.add_field(
                            name="🗳️ Elections Needed",
                            value=", ".join(result.elections_triggered),
                            inline=False
                        )
                    
                    await channel.send(embed=embed)
                    
            except Exception as e:
                print(f"Year tick failed for guild {guild.id}: {e}")

    @year_tick_loop.before_loop
    async def before_year_tick(self):
        await self.bot.wait_until_ready()
        # Wait until midnight
        now = datetime.utcnow()
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        await discord.utils.sleep_until(midnight)

    # ============ Player Commands ============

    @commands.hybrid_command(name="profile", aliases=["prof", "me"])
    async def profile(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """View your economic profile or another player's."""
        target = member or ctx.author
        profile = self.service.get_profile(ctx.guild.id, target.id)
        class_emoji = CLASS_EMOJI.get(profile.class_tier, "")
        job_name = profile.job["name"] if profile.job else "Unemployed"

        embed = discord.Embed(
            title=f"{class_emoji} {target.display_name}",
            color=discord.Color.blue(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        embed.add_field(
            name="\U0001f4b0 Balance",
            value=f"{profile.nation['currency_symbol']}{profile.citizen['balance']:,.2f}",
            inline=True,
        )
        embed.add_field(name="\U0001f4c5 Age", value=f"{profile.citizen['age']} years", inline=True)
        embed.add_field(name="\U0001f4ca Class", value=profile.class_tier.title(), inline=True)
        embed.add_field(name="\U0001f4bc Job", value=job_name, inline=True)
        embed.add_field(name="\U0001f5fd Party", value=profile.party_name, inline=True)
        embed.add_field(name="\u2b50 Reputation", value=str(profile.citizen["reputation"]), inline=True)

        if profile.properties:
            embed.add_field(name="\U0001f3e0 Properties", value=str(len(profile.properties)), inline=True)
        if profile.businesses:
            embed.add_field(name="\U0001f4b8 Businesses", value=str(len(profile.businesses)), inline=True)

        embed.set_footer(text=f"{profile.nation['name']} | Year {profile.nation['current_year']}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="work", aliases=["w"])
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def work(self, ctx: commands.Context):
        """Work at your job to earn money and XP."""
        result = self.service.work(ctx.guild.id, ctx.author.id)
        if not result.success:
            await ctx.send(f"? {result.message}")
            return

        work_messages = [
            f"You put in a solid day's work as a {result.job_name}.",
            f"Another productive shift at your {result.job_name} job!",
            f"Hard work pays off! You earned your keep today.",
            f"You hustled through your {result.job_name} duties.",
        ]

        embed = discord.Embed(
            title="?? Work Complete",
            description=random.choice(work_messages),
            color=discord.Color.green(),
        )
        embed.add_field(
            name="Earned",
            value=f"{result.currency_symbol}{result.earnings:,.2f}",
            inline=True,
        )
        embed.add_field(name="XP Gained", value=f"+{result.xp_gain}", inline=True)

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="jobs")
    async def list_jobs(self, ctx: commands.Context):
        """View available jobs."""
        jobs_data = self.service.list_jobs(ctx.guild.id)
        jobs = jobs_data.get("jobs", [])
        currency_symbol = jobs_data.get("currency_symbol", "?")

        embed = discord.Embed(
            title="?? Available Jobs",
            description="Use `/job take <name>` to get a job.",
            color=discord.Color.blue(),
        )

        for job in jobs[:15]:
            sector_emoji = "???" if job["sector"] == "public" else "??"
            embed.add_field(
                name=f"{sector_emoji} {job['name']}",
                value=(
                    f"Salary: {currency_symbol}{job['salary']:,.0f}/yr\\n"
                    f"Level: {job['required_level']}"
                ),
                inline=True,
            )

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="job")
    async def job_action(self, ctx: commands.Context, action: str, *, name: str = ""):
        """Manage your job. Actions: take, quit"""
        result = self.service.set_job(ctx.guild.id, ctx.author.id, action, name)
        prefix = "? " if not result.success else ""
        await ctx.send(f"{prefix}{result.message}")

    @commands.hybrid_command(name="balance", aliases=["bal"])
    async def balance(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Check your balance or another player's."""
        target = member or ctx.author
        result = self.service.balance(ctx.guild.id, target.id)
        data = result.data or {}
        await ctx.send(
            f"?? **{target.display_name}** has "
            f"**{data.get('currency_symbol', '?')}{data.get('balance', 0):,.2f}**"
        )

    @commands.hybrid_command(name="pay", aliases=["give"])
    async def pay(self, ctx: commands.Context, member: discord.Member, amount: float):
        """Pay another player."""
        result = self.service.pay_user(ctx.guild.id, ctx.author.id, member.id, amount)
        if not result.success:
            await ctx.send(f"? {result.message}")
            return

        currency = result.data.get("currency_symbol", "?") if result.data else "?"
        await ctx.send(
            f"? Paid **{currency}{amount:,.2f}** to {member.mention}"
        )

    @commands.hybrid_command(name="start-business", aliases=["startbiz"])
    async def start_business(self, ctx: commands.Context, *, name: str):
        """Start a new business."""
        result = self.service.start_business(ctx.guild.id, ctx.author.id, name)
        if not result.success:
            await ctx.send(f"? {result.message}")
            return

        await ctx.send(f"?? **{name}** founded! Your business will generate profits each year.")

    @commands.hybrid_command(name="businesses", aliases=["biz"])
    async def list_businesses(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """List your businesses or another player's."""
        target = member or ctx.author
        data = self.service.list_businesses(ctx.guild.id, owner_id=target.id)
        businesses = data.get("businesses", [])
        currency = data.get("currency_symbol", "?")

        if not businesses:
            await ctx.send(f"?? {target.display_name} doesn't own any businesses.")
            return

        embed = discord.Embed(
            title=f"?? {target.display_name}'s Businesses",
            color=discord.Color.blue(),
        )

        for biz in businesses[:10]:
            embed.add_field(
                name=biz["name"],
                value=(
                    f"Capital: {currency}{biz['capital']:,.0f}\\n"
                    f"Productivity: {biz['productivity']:.1f}x\\n"
                    f"Founded: Year {biz['created_year']}"
                ),
                inline=True,
            )

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="buy-property", aliases=["buyprop"])
    async def buy_property(self, ctx: commands.Context, property_type: str, *, name: str):
        """Buy a new property. Types: residential, commercial"""
        result = self.service.buy_property(ctx.guild.id, ctx.author.id, property_type, name)
        prefix = "" if result.success else "? "
        await ctx.send(f"{prefix}{result.message}")

    @commands.hybrid_command(name="properties", aliases=["props"])
    async def list_properties(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """List your properties or another player's."""
        target = member or ctx.author
        data = self.service.list_properties(ctx.guild.id, owner_id=target.id)
        properties = data.get("properties", [])
        currency = data.get("currency_symbol", "?")

        if not properties:
            await ctx.send(f"?? {target.display_name} doesn't own any properties.")
            return

        embed = discord.Embed(
            title=f"?? {target.display_name}'s Properties",
            color=discord.Color.blue(),
        )

        for prop in properties[:10]:
            tenant = "Vacant" if not prop.get("tenant_id") else f"<@{prop['tenant_id']}>"
            embed.add_field(
                name=f"{prop['name']} ({prop['property_type']})",
                value=(
                    f"Value: {currency}{prop['value']:,.0f}\\n"
                    f"Rent: {currency}{prop['rent_price']:,.0f}/yr\\n"
                    f"Tenant: {tenant}"
                ),
                inline=True,
            )

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="party")
    async def party_cmd(self, ctx: commands.Context, action: str = "info", *, name: str = ""):
        """Manage political parties. Actions: create, join, leave, list"""
        result = self.service.party_action(ctx.guild.id, ctx.author.id, action, name)
        if not result.success and not result.data:
            await ctx.send(f"? {result.message}")
            return

        action_lower = action.lower()
        if action_lower == "list" and result.data:
            parties = result.data.get("parties", [])
            if not parties:
                await ctx.send("?? No political parties exist yet. Create one with `/party create <name>`!")
                return

            embed = discord.Embed(title="??? Political Parties", color=discord.Color.purple())
            for party in parties:
                leader = self.bot.get_user(party["leader_id"])
                leader_name = leader.display_name if leader else f"User {party['leader_id']}"
                embed.add_field(
                    name=party["name"],
                    value=(
                        f"Leader: {leader_name}\\n"
                        f"Members: {party['member_count']}\\n"
                        f"Founded: Year {party['founded_year']}"
                    ),
                    inline=True,
                )
            await ctx.send(embed=embed)
            return

        await ctx.send(result.message)

    @commands.hybrid_command(name="history", aliases=["chronicle"])
    async def view_history(self, ctx: commands.Context, limit: int = 10):
        """View the nation's history."""
        data = self.service.history(ctx.guild.id, limit=limit)
        history = data.get("events", [])
        nation = data.get("nation", {})

        if not history:
            await ctx.send("?? No history recorded yet.")
            return

        embed = discord.Embed(
            title=f"?? {nation.get('name', 'Nation')} - Chronicle",
            color=discord.Color.gold(),
        )

        for event in history[:10]:
            embed.add_field(
                name=f"Year {event['year']} - {event['event_type'].replace('_', ' ').title()}",
                value=event["description"][:200],
                inline=False,
            )

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="treasury")
    async def view_treasury(self, ctx: commands.Context):
        """View the nation's treasury."""
        treasury = self.service.treasury(ctx.guild.id)

        embed = discord.Embed(
            title=f"?? {treasury.get('name', 'Nation')} Treasury",
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="Balance",
            value=f"{treasury.get('currency_symbol', '?')}{treasury.get('treasury', 0):,.2f}",
            inline=True,
        )
        embed.add_field(
            name="Current Year",
            value=str(treasury.get("current_year", "?")),
            inline=True,
        )

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="heir")
    async def set_heir(self, ctx: commands.Context, member: discord.Member):
        """Set your heir for inheritance."""
        result = self.service.set_heir(ctx.guild.id, ctx.author.id, member.id)
        prefix = "" if result.success else "? "
        await ctx.send(f"{prefix}{result.message}")

