"""ChronoNation Government Cog - Laws, elections, and nation administration."""

import json
from datetime import datetime, timedelta
from typing import Optional

import discord
from discord.ext import commands

from db.economy import (
    get_or_create_nation,
    update_nation,
    get_or_create_citizen,
    get_all_policies,
    get_policy,
    set_policy,
    get_offices,
    appoint_to_office,
    create_bill,
    vote_on_bill,
    get_pending_bills,
    resolve_bill,
    log_history,
    create_default_jobs,
    create_default_offices,
    DEFAULT_POLICIES,
)
from services.economy import process_year_tick, socialize_property


GOV_TYPES = {
    "democracy": "Parliamentary Democracy",
    "presidential": "Presidential Republic",
    "one_party": "One-Party State",
    "monarchy": "Constitutional Monarchy",
}


class GovernmentCog(commands.Cog, name="Government"):
    """Nation administration, laws, and elections."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_in_government(self, guild_id: int, user_id: int) -> bool:
        """Check if user holds any government office."""
        offices = get_offices(guild_id)
        return any(o.get("holder_id") == user_id for o in offices)

    def _has_power(self, guild_id: int, user_id: int, power: str) -> bool:
        """Check if user has a specific government power."""
        offices = get_offices(guild_id)
        for office in offices:
            if office.get("holder_id") == user_id:
                powers = json.loads(office.get("powers", "[]"))
                if "all" in powers or power in powers:
                    return True
        return False

    # ============ Nation Setup Commands ============

    @commands.command(name="nation")
    async def nation_info(self, ctx: commands.Context):
        """View nation information."""
        nation = get_or_create_nation(ctx.guild.id)
        policies = get_all_policies(ctx.guild.id)
        
        gov_type = GOV_TYPES.get(nation["gov_type"], nation["gov_type"])
        
        embed = discord.Embed(
            title=f"{nation['flag_emoji']} {nation['name']}",
            description=nation.get("motto", "") or "No motto set",
            color=discord.Color.gold(),
        )
        
        embed.add_field(name="Government", value=gov_type, inline=True)
        embed.add_field(name="Current Year", value=str(nation["current_year"]), inline=True)
        embed.add_field(
            name="Treasury",
            value=f"{nation['currency_symbol']}{nation['treasury']:,.0f}",
            inline=True
        )
        embed.add_field(
            name="Currency",
            value=f"{nation['currency_name']} ({nation['currency_symbol']})",
            inline=True
        )
        
        # Key policies
        embed.add_field(
            name="Income Tax",
            value=f"{policies.get('income_tax_rate', 0.15) * 100:.0f}%",
            inline=True
        )
        embed.add_field(
            name="UBI",
            value="Enabled" if policies.get("ubi_enabled") else "Disabled",
            inline=True
        )
        embed.add_field(
            name="Property Rights",
            value=policies.get("property_rights_mode", "capitalist").title(),
            inline=True
        )
        embed.add_field(
            name="Min Wage",
            value=f"{nation['currency_symbol']}{policies.get('min_wage', 400):,.0f}",
            inline=True
        )
        
        # Offices
        offices = get_offices(ctx.guild.id)
        if offices:
            office_strs = []
            for o in offices[:5]:
                holder = self.bot.get_user(o["holder_id"]) if o.get("holder_id") else None
                holder_name = holder.display_name if holder else "Vacant"
                office_strs.append(f"**{o['name']}**: {holder_name}")
            embed.add_field(
                name="Government Offices",
                value="\n".join(office_strs) or "None",
                inline=False
            )
        
        await ctx.send(embed=embed)

    @commands.command(name="nation-setup")
    @commands.has_permissions(administrator=True)
    async def nation_setup(self, ctx: commands.Context, *, name: str):
        """Initialize your nation (Admin only)."""
        nation = get_or_create_nation(ctx.guild.id)
        
        update_nation(ctx.guild.id, name=name)
        create_default_jobs(ctx.guild.id)
        create_default_offices(ctx.guild.id, nation["gov_type"])
        
        log_history(ctx.guild.id, 1, "nation_founded", 
                   f"The nation of {name} was founded!")
        
        await ctx.send(f"🎉 **{name}** has been founded! Use `,nation` to view details.")

    @commands.command(name="nation-config")
    @commands.has_permissions(administrator=True)
    async def nation_config(self, ctx: commands.Context, key: str = "", *, value: str = ""):
        """Configure nation settings (Admin only)."""
        if not key:
            # Show configurable keys
            embed = discord.Embed(
                title="⚙️ Nation Configuration",
                description="Use `,nation-config <key> <value>` to change settings.",
                color=discord.Color.blue(),
            )
            embed.add_field(
                name="Settings",
                value="• `name` - Nation name\n"
                      "• `currency_symbol` - e.g. ₵, $, £\n"
                      "• `currency_name` - e.g. Coins, Dollars\n"
                      "• `flag_emoji` - Nation flag emoji\n"
                      "• `motto` - National motto\n"
                      "• `gov_type` - democracy, presidential, monarchy, one_party",
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        valid_keys = ["name", "currency_symbol", "currency_name", "flag_emoji", "motto", "gov_type"]
        
        if key not in valid_keys:
            await ctx.send(f"❌ Invalid key. Valid keys: {', '.join(valid_keys)}")
            return
        
        if key == "gov_type":
            if value not in GOV_TYPES:
                await ctx.send(f"❌ Invalid government type. Options: {', '.join(GOV_TYPES.keys())}")
                return
            create_default_offices(ctx.guild.id, value)
        
        update_nation(ctx.guild.id, **{key: value})
        await ctx.send(f"✅ Set `{key}` to `{value}`")

    # ============ Policy & Law Commands ============

    @commands.command(name="policies")
    async def list_policies(self, ctx: commands.Context):
        """View all current policies."""
        policies = get_all_policies(ctx.guild.id)
        nation = get_or_create_nation(ctx.guild.id)
        
        embed = discord.Embed(
            title=f"📜 {nation['name']} - Policies",
            color=discord.Color.blue(),
        )
        
        # Tax & Welfare
        embed.add_field(
            name="💰 Tax & Welfare",
            value=f"Income Tax: {policies['income_tax_rate']*100:.0f}%\n"
                  f"Corporate Tax: {policies['corporate_tax_rate']*100:.0f}%\n"
                  f"Wealth Tax: {policies['wealth_tax_rate']*100:.0f}%\n"
                  f"Inheritance Tax: {policies['inheritance_tax_rate']*100:.0f}%\n"
                  f"UBI: {'Yes' if policies['ubi_enabled'] else 'No'} ({nation['currency_symbol']}{policies['ubi_amount']}/yr)\n"
                  f"Unemployment Benefit: {nation['currency_symbol']}{policies['unemployment_benefit']}",
            inline=True
        )
        
        # Property & Labor
        embed.add_field(
            name="🏠 Property & Labor",
            value=f"Property Mode: {policies['property_rights_mode'].title()}\n"
                  f"Max Properties: {policies['max_properties_per_person']}\n"
                  f"Rent Cap: {policies['rent_cap_percent']}%\n"
                  f"Min Wage: {nation['currency_symbol']}{policies['min_wage']}\n"
                  f"Union Power: {policies['union_power']*100:.0f}%",
            inline=True
        )
        
        # Political
        embed.add_field(
            name="🗳️ Political",
            value=f"Voting: {policies['voting_eligibility'].replace('_', ' ').title()}\n"
                  f"Term Length: {policies['term_length_years']} years\n"
                  f"Class Thresholds:\n"
                  f"  Working: <{nation['currency_symbol']}{policies['working_class_threshold']:,}\n"
                  f"  Elite: >{nation['currency_symbol']}{policies['elite_class_threshold']:,}",
            inline=True
        )
        
        await ctx.send(embed=embed)

    @commands.command(name="law")
    async def law_cmd(self, ctx: commands.Context, action: str = "list", *, args: str = ""):
        """Manage laws. Actions: propose, list, vote, info"""
        nation = get_or_create_nation(ctx.guild.id)
        
        if action.lower() == "list":
            bills = get_pending_bills(ctx.guild.id)
            
            if not bills:
                await ctx.send("📭 No pending bills. Use `,law propose <policy> <value>` to propose one.")
                return
            
            embed = discord.Embed(
                title="📋 Pending Bills",
                color=discord.Color.purple(),
            )
            
            for bill in bills[:10]:
                proposer = self.bot.get_user(bill["proposer_id"])
                proposer_name = proposer.display_name if proposer else f"User {bill['proposer_id']}"
                
                ends = datetime.fromisoformat(bill["voting_ends_at"])
                time_left = ends - datetime.utcnow()
                hours_left = max(0, time_left.total_seconds() / 3600)
                
                embed.add_field(
                    name=f"Bill #{bill['id']}: {bill['policy_key']}",
                    value=f"New Value: `{bill['new_value']}`\n"
                          f"Proposed by: {proposer_name}\n"
                          f"Votes: {bill['votes_for']} for / {bill['votes_against']} against\n"
                          f"Time left: {hours_left:.1f}h",
                    inline=False
                )
            
            embed.set_footer(text="Vote with: ,law vote <bill_id> yes/no")
            await ctx.send(embed=embed)
        
        elif action.lower() == "propose":
            # Check if user has propose power
            if not self._has_power(ctx.guild.id, ctx.author.id, "propose_law"):
                # In democracies, anyone can propose
                policies = get_all_policies(ctx.guild.id)
                if nation["gov_type"] not in ["democracy", "presidential"]:
                    await ctx.send("❌ You don't have the power to propose laws!")
                    return
            
            # Parse args: <policy_key> <new_value> [description]
            parts = args.split(maxsplit=2)
            if len(parts) < 2:
                await ctx.send("❌ Usage: `,law propose <policy_key> <new_value> [description]`\n"
                              "Example: `,law propose income_tax_rate 0.25 Increase income tax to 25%`")
                return
            
            policy_key = parts[0]
            new_value = parts[1]
            description = parts[2] if len(parts) > 2 else f"Change {policy_key} to {new_value}"
            
            # Validate policy key
            if policy_key not in DEFAULT_POLICIES:
                await ctx.send(f"❌ Unknown policy key. Use `,policies` to see available policies.")
                return
            
            bill_id = create_bill(
                ctx.guild.id, ctx.author.id, policy_key, 
                new_value, description, voting_hours=24
            )
            
            log_history(ctx.guild.id, nation["current_year"], "bill_proposed",
                       f"Bill #{bill_id} proposed: {policy_key} = {new_value}")
            
            await ctx.send(f"📜 **Bill #{bill_id}** proposed!\n"
                          f"Policy: `{policy_key}` → `{new_value}`\n"
                          f"Voting open for 24 hours. Use `,law vote {bill_id} yes/no`")
        
        elif action.lower() == "vote":
            parts = args.split()
            if len(parts) < 2:
                await ctx.send("❌ Usage: `,law vote <bill_id> yes/no`")
                return
            
            try:
                bill_id = int(parts[0])
            except ValueError:
                await ctx.send("❌ Invalid bill ID.")
                return
            
            vote_choice = parts[1].lower()
            if vote_choice not in ["yes", "no", "y", "n", "for", "against"]:
                await ctx.send("❌ Vote must be `yes` or `no`.")
                return
            
            vote_for = vote_choice in ["yes", "y", "for"]
            
            # Check voting eligibility
            policies = get_all_policies(ctx.guild.id)
            eligibility = policies.get("voting_eligibility", "all")
            citizen = get_or_create_citizen(ctx.guild.id, ctx.author.id)
            
            if eligibility == "elites_only" and citizen["balance"] < policies["elite_class_threshold"]:
                await ctx.send("❌ Only elites can vote in this nation!")
                return
            
            if vote_on_bill(bill_id, ctx.author.id, vote_for):
                vote_str = "✅ for" if vote_for else "❌ against"
                await ctx.send(f"🗳️ You voted {vote_str} Bill #{bill_id}")
            else:
                await ctx.send("❌ Could not vote. Bill may not exist or you already voted.")
        
        elif action.lower() == "info":
            if not args:
                await ctx.send("❌ Specify a policy key: `,law info income_tax_rate`")
                return
            
            policy_key = args.strip()
            if policy_key not in DEFAULT_POLICIES:
                await ctx.send("❌ Unknown policy key.")
                return
            
            current = get_policy(ctx.guild.id, policy_key)
            default = DEFAULT_POLICIES[policy_key]
            
            await ctx.send(f"📜 **{policy_key}**\n"
                          f"Current: `{current}`\n"
                          f"Default: `{default}`")
        
        else:
            await ctx.send("❌ Unknown action. Use: `list`, `propose`, `vote`, `info`")

    @commands.command(name="policy")
    @commands.has_permissions(administrator=True)
    async def set_policy_direct(self, ctx: commands.Context, key: str, *, value: str):
        """Directly set a policy (Admin only, bypasses voting)."""
        if key not in DEFAULT_POLICIES:
            await ctx.send(f"❌ Unknown policy key. Use `,policies` to see valid keys.")
            return
        
        # Parse value type
        default = DEFAULT_POLICIES[key]
        try:
            if isinstance(default, bool):
                parsed = value.lower() in ["true", "yes", "1", "on"]
            elif isinstance(default, int):
                parsed = int(value)
            elif isinstance(default, float):
                parsed = float(value)
            else:
                parsed = value
        except ValueError:
            await ctx.send(f"❌ Invalid value type for `{key}`.")
            return
        
        set_policy(ctx.guild.id, key, parsed)
        
        nation = get_or_create_nation(ctx.guild.id)
        log_history(ctx.guild.id, nation["current_year"], "policy_decree",
                   f"Policy decree: {key} set to {parsed}")
        
        await ctx.send(f"✅ Policy `{key}` set to `{parsed}`")

    # ============ Office & Election Commands ============

    @commands.command(name="offices")
    async def list_offices(self, ctx: commands.Context):
        """View government offices."""
        offices = get_offices(ctx.guild.id)
        nation = get_or_create_nation(ctx.guild.id)
        
        if not offices:
            create_default_offices(ctx.guild.id, nation["gov_type"])
            offices = get_offices(ctx.guild.id)
        
        embed = discord.Embed(
            title=f"🏛️ {nation['name']} - Government Offices",
            color=discord.Color.purple(),
        )
        
        for office in offices:
            holder = self.bot.get_user(office["holder_id"]) if office.get("holder_id") else None
            holder_name = holder.display_name if holder else "**Vacant**"
            
            term_info = ""
            if office.get("holder_id") and office.get("term_start_year"):
                years_in = nation["current_year"] - office["term_start_year"]
                term_info = f"\nIn office: {years_in}/{office['term_years']} years"
            
            powers = json.loads(office.get("powers", "[]"))
            powers_str = ", ".join(powers[:3]) if powers else "None"
            
            embed.add_field(
                name=office["name"],
                value=f"Holder: {holder_name}{term_info}\n"
                      f"Term: {office['term_years']} years\n"
                      f"Powers: {powers_str}",
                inline=True
            )
        
        await ctx.send(embed=embed)

    @commands.command(name="appoint")
    @commands.has_permissions(administrator=True)
    async def appoint_office(self, ctx: commands.Context, office_name: str, member: discord.Member):
        """Appoint someone to office (Admin or with appoint power)."""
        # Check if user can appoint
        if not ctx.author.guild_permissions.administrator:
            if not self._has_power(ctx.guild.id, ctx.author.id, "appoint"):
                await ctx.send("❌ You don't have the power to appoint!")
                return
        
        offices = get_offices(ctx.guild.id)
        office = next((o for o in offices if o["name"].lower() == office_name.lower()), None)
        
        if not office:
            await ctx.send(f"❌ Office '{office_name}' not found. Use `,offices` to see offices.")
            return
        
        nation = get_or_create_nation(ctx.guild.id)
        appoint_to_office(office["id"], member.id, nation["current_year"])
        
        log_history(ctx.guild.id, nation["current_year"], "appointment",
                   f"{member.display_name} appointed as {office['name']}")
        
        await ctx.send(f"🎖️ **{member.display_name}** has been appointed as **{office['name']}**!")

    # ============ Special Actions ============

    @commands.command(name="abolish-landlords")
    async def abolish_landlords(self, ctx: commands.Context, compensate: str = "yes"):
        """Socialize all property (requires government power or admin)."""
        if not ctx.author.guild_permissions.administrator:
            if not self._has_power(ctx.guild.id, ctx.author.id, "all"):
                await ctx.send("❌ Only administrators or supreme leaders can abolish landlords!")
                return
        
        nation = get_or_create_nation(ctx.guild.id)
        do_compensate = compensate.lower() in ["yes", "true", "1"]
        
        count = socialize_property(ctx.guild.id, compensate=do_compensate)
        set_policy(ctx.guild.id, "property_rights_mode", "socialized")
        
        comp_str = "with compensation" if do_compensate else "without compensation"
        log_history(ctx.guild.id, nation["current_year"], "revolution",
                   f"Land reform: {count} properties nationalized {comp_str}!")
        
        await ctx.send(f"🚩 **LAND REFORM**\n"
                      f"{count} properties have been transferred to state ownership {comp_str}!\n"
                      f"All rent now goes to the national treasury.")

    @commands.command(name="force-tick")
    @commands.has_permissions(administrator=True)
    async def force_tick(self, ctx: commands.Context):
        """Force a year tick (Admin only, for testing)."""
        await ctx.send("⏳ Processing year tick...")
        
        result = await process_year_tick(ctx.guild.id)
        
        embed = discord.Embed(
            title=f"📅 Year {result.year} Complete",
            color=discord.Color.gold(),
        )
        
        if result.history_entries:
            embed.description = result.history_entries[0]
        
        if result.deaths:
            embed.add_field(name="⚰️ Deaths", value=str(len(result.deaths)), inline=True)
        if result.events:
            embed.add_field(name="📰 Events", value=str(len(result.events)), inline=True)
        if result.bills_resolved:
            embed.add_field(name="📜 Bills Resolved", value=str(len(result.bills_resolved)), inline=True)
        
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(GovernmentCog(bot))
