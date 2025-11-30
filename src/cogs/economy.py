"""ChronoNation Economy Cog - Player commands for the economy simulation."""

import random
from datetime import datetime, timedelta
from typing import Optional

import discord
from discord.ext import commands, tasks

from db.economy import (
    get_or_create_nation,
    update_nation,
    get_or_create_citizen,
    update_citizen,
    get_citizen_class,
    transfer_balance,
    get_all_policies,
    get_policy,
    get_jobs,
    get_job,
    get_businesses,
    create_business,
    get_properties,
    create_property,
    get_parties,
    create_party,
    join_party,
    get_offices,
    get_history,
    create_default_jobs,
    create_default_offices,
    log_history,
)
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

    @commands.command(name="profile", aliases=["p", "me"])
    async def profile(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """View your economic profile or another player's."""
        target = member or ctx.author
        citizen = get_or_create_citizen(ctx.guild.id, target.id)
        nation = get_or_create_nation(ctx.guild.id)
        policies = get_all_policies(ctx.guild.id)
        
        class_tier = get_citizen_class(
            citizen["balance"],
            {"elite": policies.get("elite_class_threshold", 100000),
             "middle": policies.get("working_class_threshold", 10000)}
        )
        class_emoji = CLASS_EMOJI.get(class_tier, "")
        
        # Get job name
        job_name = "Unemployed"
        if citizen.get("job_id"):
            job = get_job(citizen["job_id"])
            if job:
                job_name = job["name"]
        
        # Get party name
        party_name = "Independent"
        if citizen.get("party_id"):
            parties = get_parties(ctx.guild.id)
            for p in parties:
                if p["id"] == citizen["party_id"]:
                    party_name = p["name"]
                    break
        
        embed = discord.Embed(
            title=f"{class_emoji} {target.display_name}",
            color=discord.Color.blue(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        
        embed.add_field(
            name="💰 Balance",
            value=f"{nation['currency_symbol']}{citizen['balance']:,.2f}",
            inline=True
        )
        embed.add_field(name="📅 Age", value=f"{citizen['age']} years", inline=True)
        embed.add_field(name="🎭 Class", value=class_tier.title(), inline=True)
        embed.add_field(name="💼 Job", value=job_name, inline=True)
        embed.add_field(name="🗳️ Party", value=party_name, inline=True)
        embed.add_field(name="⭐ Reputation", value=str(citizen["reputation"]), inline=True)
        
        # Properties and businesses
        properties = get_properties(ctx.guild.id, owner_id=target.id)
        businesses = get_businesses(ctx.guild.id, owner_id=target.id)
        
        if properties:
            embed.add_field(name="🏠 Properties", value=str(len(properties)), inline=True)
        if businesses:
            embed.add_field(name="🏭 Businesses", value=str(len(businesses)), inline=True)
        
        embed.set_footer(text=f"{nation['name']} | Year {nation['current_year']}")
        
        await ctx.send(embed=embed)

    @commands.command(name="work", aliases=["w"])
    @commands.cooldown(1, 300, commands.BucketType.user)  # 5 min cooldown
    async def work(self, ctx: commands.Context):
        """Work at your job to earn money and XP."""
        citizen = get_or_create_citizen(ctx.guild.id, ctx.author.id)
        policies = get_all_policies(ctx.guild.id)
        nation = get_or_create_nation(ctx.guild.id)
        
        job_id = citizen.get("job_id")
        if not job_id:
            await ctx.send("❌ You don't have a job! Use `,jobs` to see available jobs.")
            return
        
        job = get_job(job_id)
        if not job:
            await ctx.send("❌ Your job no longer exists. Use `,jobs` to find a new one.")
            return
        
        # Calculate earnings (daily work = fraction of annual salary)
        min_wage = policies.get("min_wage", 400)
        base_pay = max(job["salary"], min_wage) / 365 * 5  # ~5 days worth per action
        
        # XP bonus
        xp_bonus = 1 + (citizen.get("work_xp", 0) / 1000)
        earnings = base_pay * xp_bonus * (0.8 + random.random() * 0.4)  # Some variance
        
        # Pay from treasury if public sector
        if job["sector"] == "public":
            transfer_balance(ctx.guild.id, 0, ctx.author.id, earnings)
        else:
            update_citizen(ctx.guild.id, ctx.author.id, 
                          balance=citizen["balance"] + earnings)
        
        # Gain XP
        new_xp = citizen.get("work_xp", 0) + random.randint(5, 15)
        update_citizen(ctx.guild.id, ctx.author.id, work_xp=new_xp)
        
        work_messages = [
            f"You put in a solid day's work as a {job['name']}.",
            f"Another productive shift at your {job['name']} job!",
            f"Hard work pays off! You earned your keep today.",
            f"You hustled through your {job['name']} duties.",
        ]
        
        embed = discord.Embed(
            title="💼 Work Complete",
            description=random.choice(work_messages),
            color=discord.Color.green(),
        )
        embed.add_field(
            name="Earned",
            value=f"{nation['currency_symbol']}{earnings:,.2f}",
            inline=True
        )
        embed.add_field(name="XP Gained", value=f"+{new_xp - citizen.get('work_xp', 0)}", inline=True)
        
        await ctx.send(embed=embed)

    @commands.command(name="jobs")
    async def list_jobs(self, ctx: commands.Context):
        """View available jobs."""
        jobs = get_jobs(ctx.guild.id)
        nation = get_or_create_nation(ctx.guild.id)
        
        if not jobs:
            # Create default jobs
            create_default_jobs(ctx.guild.id)
            jobs = get_jobs(ctx.guild.id)
        
        embed = discord.Embed(
            title="💼 Available Jobs",
            description="Use `,job take <name>` to get a job.",
            color=discord.Color.blue(),
        )
        
        for job in jobs[:15]:
            sector_emoji = "🏛️" if job["sector"] == "public" else "🏢"
            embed.add_field(
                name=f"{sector_emoji} {job['name']}",
                value=f"Salary: {nation['currency_symbol']}{job['salary']:,.0f}/yr\nLevel: {job['required_level']}",
                inline=True
            )
        
        await ctx.send(embed=embed)

    @commands.command(name="job")
    async def job_action(self, ctx: commands.Context, action: str, *, name: str = ""):
        """Manage your job. Actions: take, quit"""
        citizen = get_or_create_citizen(ctx.guild.id, ctx.author.id)
        
        if action.lower() == "take":
            if not name:
                await ctx.send("❌ Specify a job name: `,job take Clerk`")
                return
            
            jobs = get_jobs(ctx.guild.id)
            job = next((j for j in jobs if j["name"].lower() == name.lower()), None)
            
            if not job:
                await ctx.send(f"❌ Job '{name}' not found. Use `,jobs` to see available jobs.")
                return
            
            # Check level requirement
            work_level = citizen.get("work_xp", 0) // 500
            if work_level < job["required_level"]:
                await ctx.send(f"❌ This job requires level {job['required_level']}. You're level {work_level}.")
                return
            
            update_citizen(ctx.guild.id, ctx.author.id, job_id=job["id"])
            await ctx.send(f"✅ You are now employed as a **{job['name']}**!")
        
        elif action.lower() == "quit":
            if not citizen.get("job_id"):
                await ctx.send("❌ You don't have a job to quit!")
                return
            
            update_citizen(ctx.guild.id, ctx.author.id, job_id=None)
            await ctx.send("✅ You quit your job. Use `,jobs` to find a new one.")
        
        else:
            await ctx.send("❌ Unknown action. Use `take` or `quit`.")

    @commands.command(name="balance", aliases=["bal"])
    async def balance(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Check your balance or another player's."""
        target = member or ctx.author
        citizen = get_or_create_citizen(ctx.guild.id, target.id)
        nation = get_or_create_nation(ctx.guild.id)
        
        await ctx.send(
            f"💰 **{target.display_name}** has "
            f"**{nation['currency_symbol']}{citizen['balance']:,.2f}**"
        )

    @commands.command(name="pay", aliases=["give"])
    async def pay(self, ctx: commands.Context, member: discord.Member, amount: float):
        """Pay another player."""
        if member.id == ctx.author.id:
            await ctx.send("❌ You can't pay yourself!")
            return
        
        if amount <= 0:
            await ctx.send("❌ Amount must be positive!")
            return
        
        citizen = get_or_create_citizen(ctx.guild.id, ctx.author.id)
        nation = get_or_create_nation(ctx.guild.id)
        
        if citizen["balance"] < amount:
            await ctx.send("❌ Insufficient funds!")
            return
        
        # Ensure recipient exists
        get_or_create_citizen(ctx.guild.id, member.id)
        
        if transfer_balance(ctx.guild.id, ctx.author.id, member.id, amount):
            await ctx.send(
                f"✅ Paid **{nation['currency_symbol']}{amount:,.2f}** to {member.mention}"
            )
        else:
            await ctx.send("❌ Transfer failed!")

    @commands.command(name="start-business", aliases=["startbiz"])
    async def start_business(self, ctx: commands.Context, *, name: str):
        """Start a new business (costs ₵5000)."""
        STARTUP_COST = 5000
        
        citizen = get_or_create_citizen(ctx.guild.id, ctx.author.id)
        nation = get_or_create_nation(ctx.guild.id)
        
        if citizen["balance"] < STARTUP_COST:
            await ctx.send(f"❌ Starting a business costs {nation['currency_symbol']}{STARTUP_COST:,}!")
            return
        
        # Deduct cost
        update_citizen(ctx.guild.id, ctx.author.id, balance=citizen["balance"] - STARTUP_COST)
        
        # Create business
        biz_id = create_business(
            ctx.guild.id, ctx.author.id, name, "general",
            capital=STARTUP_COST, year=nation["current_year"]
        )
        
        await ctx.send(f"🏭 **{name}** founded! Your business will generate profits each year.")

    @commands.command(name="businesses", aliases=["biz"])
    async def list_businesses(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """List your businesses or another player's."""
        target = member or ctx.author
        businesses = get_businesses(ctx.guild.id, owner_id=target.id)
        nation = get_or_create_nation(ctx.guild.id)
        
        if not businesses:
            await ctx.send(f"📭 {target.display_name} doesn't own any businesses.")
            return
        
        embed = discord.Embed(
            title=f"🏭 {target.display_name}'s Businesses",
            color=discord.Color.blue(),
        )
        
        for biz in businesses[:10]:
            embed.add_field(
                name=biz["name"],
                value=f"Capital: {nation['currency_symbol']}{biz['capital']:,.0f}\n"
                      f"Productivity: {biz['productivity']:.1f}x\n"
                      f"Founded: Year {biz['created_year']}",
                inline=True
            )
        
        await ctx.send(embed=embed)

    @commands.command(name="buy-property", aliases=["buyprop"])
    async def buy_property(self, ctx: commands.Context, property_type: str, *, name: str):
        """Buy a new property. Types: residential, commercial"""
        PRICES = {"residential": 10000, "commercial": 25000}
        
        ptype = property_type.lower()
        if ptype not in PRICES:
            await ctx.send("❌ Property type must be `residential` or `commercial`.")
            return
        
        price = PRICES[ptype]
        citizen = get_or_create_citizen(ctx.guild.id, ctx.author.id)
        nation = get_or_create_nation(ctx.guild.id)
        
        if citizen["balance"] < price:
            await ctx.send(f"❌ {ptype.title()} property costs {nation['currency_symbol']}{price:,}!")
            return
        
        # Check property limit
        policies = get_all_policies(ctx.guild.id)
        max_props = policies.get("max_properties_per_person", 10)
        current_props = get_properties(ctx.guild.id, owner_id=ctx.author.id)
        
        if len(current_props) >= max_props:
            await ctx.send(f"❌ You can only own {max_props} properties!")
            return
        
        # Deduct cost
        update_citizen(ctx.guild.id, ctx.author.id, balance=citizen["balance"] - price)
        
        # Create property
        rent = price * 0.05  # 5% annual rent
        create_property(ctx.guild.id, ctx.author.id, name, ptype, price, rent)
        
        await ctx.send(f"🏠 Purchased **{name}** ({ptype}) for {nation['currency_symbol']}{price:,}!")

    @commands.command(name="properties", aliases=["props"])
    async def list_properties(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """List your properties or another player's."""
        target = member or ctx.author
        properties = get_properties(ctx.guild.id, owner_id=target.id)
        nation = get_or_create_nation(ctx.guild.id)
        
        if not properties:
            await ctx.send(f"📭 {target.display_name} doesn't own any properties.")
            return
        
        embed = discord.Embed(
            title=f"🏠 {target.display_name}'s Properties",
            color=discord.Color.blue(),
        )
        
        for prop in properties[:10]:
            tenant = "Vacant" if not prop.get("tenant_id") else f"<@{prop['tenant_id']}>"
            embed.add_field(
                name=f"{prop['name']} ({prop['property_type']})",
                value=f"Value: {nation['currency_symbol']}{prop['value']:,.0f}\n"
                      f"Rent: {nation['currency_symbol']}{prop['rent_price']:,.0f}/yr\n"
                      f"Tenant: {tenant}",
                inline=True
            )
        
        await ctx.send(embed=embed)

    @commands.command(name="party")
    async def party_cmd(self, ctx: commands.Context, action: str = "info", *, name: str = ""):
        """Manage political parties. Actions: create, join, leave, list, info"""
        citizen = get_or_create_citizen(ctx.guild.id, ctx.author.id)
        nation = get_or_create_nation(ctx.guild.id)
        
        if action.lower() == "list":
            parties = get_parties(ctx.guild.id)
            if not parties:
                await ctx.send("📭 No political parties exist yet. Create one with `,party create <name>`!")
                return
            
            embed = discord.Embed(title="🗳️ Political Parties", color=discord.Color.purple())
            for party in parties:
                leader = self.bot.get_user(party["leader_id"])
                leader_name = leader.display_name if leader else f"User {party['leader_id']}"
                embed.add_field(
                    name=party["name"],
                    value=f"Leader: {leader_name}\nMembers: {party['member_count']}\nFounded: Year {party['founded_year']}",
                    inline=True
                )
            await ctx.send(embed=embed)
        
        elif action.lower() == "create":
            if not name:
                await ctx.send("❌ Specify a party name: `,party create Workers United`")
                return
            
            if citizen.get("party_id"):
                await ctx.send("❌ Leave your current party first with `,party leave`!")
                return
            
            party_id = create_party(ctx.guild.id, name, ctx.author.id, nation["current_year"])
            log_history(ctx.guild.id, nation["current_year"], "party_founded",
                       f"{ctx.author.display_name} founded the party '{name}'")
            
            await ctx.send(f"🎉 **{name}** party founded! You are the leader.")
        
        elif action.lower() == "join":
            if not name:
                await ctx.send("❌ Specify a party name: `,party join Workers United`")
                return
            
            if citizen.get("party_id"):
                await ctx.send("❌ Leave your current party first!")
                return
            
            parties = get_parties(ctx.guild.id)
            party = next((p for p in parties if p["name"].lower() == name.lower()), None)
            
            if not party:
                await ctx.send(f"❌ Party '{name}' not found. Use `,party list` to see parties.")
                return
            
            join_party(ctx.guild.id, ctx.author.id, party["id"])
            await ctx.send(f"✅ You joined **{party['name']}**!")
        
        elif action.lower() == "leave":
            if not citizen.get("party_id"):
                await ctx.send("❌ You're not in a party!")
                return
            
            update_citizen(ctx.guild.id, ctx.author.id, party_id=None)
            await ctx.send("✅ You left your party.")
        
        else:
            await ctx.send("❌ Unknown action. Use: `list`, `create`, `join`, `leave`")

    @commands.command(name="history", aliases=["chronicle"])
    async def view_history(self, ctx: commands.Context, limit: int = 10):
        """View the nation's history."""
        history = get_history(ctx.guild.id, limit=min(limit, 25))
        nation = get_or_create_nation(ctx.guild.id)
        
        if not history:
            await ctx.send("📜 No history recorded yet.")
            return
        
        embed = discord.Embed(
            title=f"📜 {nation['name']} - Chronicle",
            color=discord.Color.gold(),
        )
        
        for event in history[:10]:
            embed.add_field(
                name=f"Year {event['year']} - {event['event_type'].replace('_', ' ').title()}",
                value=event["description"][:200],
                inline=False
            )
        
        await ctx.send(embed=embed)

    @commands.command(name="treasury")
    async def view_treasury(self, ctx: commands.Context):
        """View the nation's treasury."""
        nation = get_or_create_nation(ctx.guild.id)
        
        embed = discord.Embed(
            title=f"🏦 {nation['name']} Treasury",
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="Balance",
            value=f"{nation['currency_symbol']}{nation['treasury']:,.2f}",
            inline=True
        )
        embed.add_field(
            name="Current Year",
            value=str(nation["current_year"]),
            inline=True
        )
        
        await ctx.send(embed=embed)

    @commands.command(name="heir")
    async def set_heir(self, ctx: commands.Context, member: discord.Member):
        """Set your heir for inheritance."""
        if member.id == ctx.author.id:
            await ctx.send("❌ You can't be your own heir!")
            return
        
        update_citizen(ctx.guild.id, ctx.author.id, heir_id=member.id)
        await ctx.send(f"✅ **{member.display_name}** is now your designated heir.")


async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))
