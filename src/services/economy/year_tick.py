"""Year Tick System - Runs daily (1 real day = 1 game year)."""

import random
from typing import Dict, List, Tuple, Optional
from datetime import datetime

from db.economy import (
    get_or_create_nation,
    update_nation,
    increment_year,
    get_all_citizens,
    update_citizen,
    transfer_balance,
    get_all_policies,
    get_policy,
    get_jobs,
    get_job,
    get_businesses,
    get_properties,
    transfer_property,
    get_offices,
    get_pending_bills,
    resolve_bill,
    log_history,
    get_random_event,
)


class YearTickResult:
    """Results from processing a year tick."""
    
    def __init__(self, guild_id: int, year: int):
        self.guild_id = guild_id
        self.year = year
        self.deaths: List[Tuple[int, str]] = []  # (user_id, cause)
        self.inheritances: List[Tuple[int, int, float]] = []  # (from_id, to_id, amount)
        self.income_paid: float = 0
        self.taxes_collected: float = 0
        self.ubi_paid: float = 0
        self.rent_collected: float = 0
        self.business_profits: float = 0
        self.events: List[Dict] = []
        self.elections_triggered: List[str] = []
        self.bills_resolved: List[Dict] = []
        self.history_entries: List[str] = []


async def process_year_tick(guild_id: int) -> YearTickResult:
    """
    Process the annual tick for a nation.
    This is the core simulation loop.
    """
    # Get nation and increment year
    nation = get_or_create_nation(guild_id)
    new_year = increment_year(guild_id)
    
    result = YearTickResult(guild_id, new_year)
    policies = get_all_policies(guild_id)
    
    # Get all living citizens
    citizens = get_all_citizens(guild_id, alive_only=True)
    
    # 1. Aging and death
    _process_aging(guild_id, citizens, policies, result)
    
    # 2. Income (jobs and businesses)
    _process_income(guild_id, citizens, policies, nation, result)
    
    # 3. Rent collection
    _process_rent(guild_id, policies, result)
    
    # 4. Tax collection
    _process_taxes(guild_id, citizens, policies, nation, result)
    
    # 5. UBI / Welfare
    _process_welfare(guild_id, citizens, policies, nation, result)
    
    # 6. Government cycle (terms, elections)
    _process_government_cycle(guild_id, new_year, policies, result)
    
    # 7. Resolve pending bills
    _process_bills(guild_id, result)
    
    # 8. Random events
    _process_random_events(guild_id, new_year, policies, result)
    
    # Log year summary to history
    summary = _generate_year_summary(result)
    log_history(guild_id, new_year, "year_summary", summary)
    result.history_entries.append(summary)
    
    return result


def _process_aging(guild_id: int, citizens: List[Dict], 
                   policies: Dict, result: YearTickResult):
    """Age citizens and handle deaths."""
    death_min = policies.get("death_age_min", 70)
    death_max = policies.get("death_age_max", 100)
    inheritance_tax = policies.get("inheritance_tax_rate", 0.20)
    
    for citizen in citizens:
        user_id = citizen["user_id"]
        new_age = citizen["age"] + 1
        update_citizen(guild_id, user_id, age=new_age)
        
        # Death check for elderly
        if new_age >= death_min:
            # Probability increases with age
            death_chance = (new_age - death_min) / (death_max - death_min)
            death_chance = min(death_chance, 0.95)  # Cap at 95%
            
            if new_age >= death_max or random.random() < death_chance:
                # Citizen dies
                _handle_death(guild_id, citizen, inheritance_tax, result)


def _handle_death(guild_id: int, citizen: Dict, 
                  inheritance_tax: float, result: YearTickResult):
    """Handle a citizen's death and inheritance."""
    user_id = citizen["user_id"]
    balance = citizen["balance"]
    
    # Mark as dead
    update_citizen(guild_id, user_id, is_alive=0, death_year=result.year)
    result.deaths.append((user_id, "old age"))
    
    # Handle inheritance
    heir_id = citizen.get("heir_id")
    if not heir_id:
        # Estate goes to treasury
        heir_id = 0
    
    # Apply inheritance tax
    tax_amount = balance * inheritance_tax
    inheritance_amount = balance - tax_amount
    
    if inheritance_amount > 0:
        if heir_id == 0:
            # To treasury
            transfer_balance(guild_id, user_id, 0, balance)
        else:
            # Pay tax to treasury
            if tax_amount > 0:
                transfer_balance(guild_id, user_id, 0, tax_amount)
            # Give remainder to heir
            transfer_balance(guild_id, user_id, heir_id, inheritance_amount)
        
        result.inheritances.append((user_id, heir_id, inheritance_amount))
    
    # Transfer properties
    properties = get_properties(guild_id, owner_id=user_id)
    for prop in properties:
        transfer_property(prop["id"], heir_id)


def _process_income(guild_id: int, citizens: List[Dict], 
                   policies: Dict, nation: Dict, result: YearTickResult):
    """Process job salaries and business profits."""
    min_wage = policies.get("min_wage", 400)
    
    for citizen in citizens:
        user_id = citizen["user_id"]
        
        # Job salary
        job_id = citizen.get("job_id")
        if job_id:
            job = get_job(job_id)
            if job:
                salary = max(job["salary"], min_wage)
                
                # Public sector pays from treasury
                if job["sector"] == "public":
                    transfer_balance(guild_id, 0, user_id, salary)
                else:
                    # Private sector - just credit (simplified)
                    update_citizen(guild_id, user_id, 
                                  balance=citizen["balance"] + salary)
                
                result.income_paid += salary
    
    # Business profits
    businesses = get_businesses(guild_id)
    corp_tax = policies.get("corporate_tax_rate", 0.20)
    
    for biz in businesses:
        # Calculate profit based on productivity and employees
        base_profit = 500 * biz["productivity"] * (1 + biz["employee_count"] * 0.2)
        
        # Apply any event modifiers (stored in nation data)
        event_mult = nation.get("business_profit_mult", 1.0)
        gross_profit = base_profit * event_mult
        
        # Corporate tax
        tax = gross_profit * corp_tax
        net_profit = gross_profit - tax
        
        # Pay owner
        owner_id = biz["owner_id"]
        if owner_id:
            update_citizen(guild_id, owner_id, 
                          balance=get_or_create_citizen(guild_id, owner_id)["balance"] + net_profit)
        
        # Tax to treasury
        transfer_balance(guild_id, owner_id, 0, tax)
        
        result.business_profits += net_profit
        result.taxes_collected += tax


def _process_rent(guild_id: int, policies: Dict, result: YearTickResult):
    """Process rent payments from tenants to landlords."""
    property_mode = policies.get("property_rights_mode", "capitalist")
    
    properties = get_properties(guild_id)
    
    for prop in properties:
        tenant_id = prop.get("tenant_id")
        if not tenant_id:
            continue
        
        rent = prop["rent_price"]
        
        if property_mode == "capitalist":
            # Rent goes to owner
            owner_id = prop["owner_id"]
            if transfer_balance(guild_id, tenant_id, owner_id, rent):
                result.rent_collected += rent
        
        elif property_mode == "socialized":
            # Rent goes to state treasury
            if transfer_balance(guild_id, tenant_id, 0, rent):
                result.rent_collected += rent
        
        elif property_mode == "collective":
            # Rent split among collective members (simplified)
            if transfer_balance(guild_id, tenant_id, 0, rent):
                result.rent_collected += rent


def _process_taxes(guild_id: int, citizens: List[Dict], 
                  policies: Dict, nation: Dict, result: YearTickResult):
    """Collect income and wealth taxes."""
    income_tax = policies.get("income_tax_rate", 0.15)
    wealth_tax = policies.get("wealth_tax_rate", 0.0)
    
    for citizen in citizens:
        user_id = citizen["user_id"]
        balance = citizen["balance"]
        
        # Wealth tax (on balance over threshold)
        if wealth_tax > 0 and balance > 50000:
            taxable_wealth = balance - 50000
            tax = taxable_wealth * wealth_tax
            if transfer_balance(guild_id, user_id, 0, tax):
                result.taxes_collected += tax


def _process_welfare(guild_id: int, citizens: List[Dict], 
                    policies: Dict, nation: Dict, result: YearTickResult):
    """Process UBI and unemployment benefits."""
    ubi_enabled = policies.get("ubi_enabled", False)
    ubi_amount = policies.get("ubi_amount", 0)
    unemployment_benefit = policies.get("unemployment_benefit", 200)
    
    for citizen in citizens:
        user_id = citizen["user_id"]
        
        # UBI
        if ubi_enabled and ubi_amount > 0:
            if transfer_balance(guild_id, 0, user_id, ubi_amount):
                result.ubi_paid += ubi_amount
        
        # Unemployment benefit
        if not citizen.get("job_id") and unemployment_benefit > 0:
            transfer_balance(guild_id, 0, user_id, unemployment_benefit)
            result.ubi_paid += unemployment_benefit


def _process_government_cycle(guild_id: int, year: int, 
                              policies: Dict, result: YearTickResult):
    """Check for term expirations and trigger elections."""
    offices = get_offices(guild_id)
    
    for office in offices:
        holder_id = office.get("holder_id")
        if not holder_id:
            continue
        
        term_start = office.get("term_start_year", 0)
        term_length = office.get("term_years", 4)
        
        if year >= term_start + term_length:
            # Term ended
            result.elections_triggered.append(office["name"])
            
            log_history(guild_id, year, "term_ended",
                       f"{office['name']}'s term has ended. Elections required.")


def _process_bills(guild_id: int, result: YearTickResult):
    """Resolve bills whose voting period has ended."""
    bills = get_pending_bills(guild_id)
    now = datetime.utcnow()
    
    for bill in bills:
        ends_at = datetime.fromisoformat(bill["voting_ends_at"])
        if now >= ends_at:
            resolved = resolve_bill(bill["id"])
            result.bills_resolved.append(resolved)
            
            status = "PASSED" if resolved["status"] == "passed" else "FAILED"
            log_history(
                guild_id, result.year, "bill_resolved",
                f"Bill #{bill['id']} ({bill['policy_key']} = {bill['new_value']}) {status}. "
                f"Votes: {bill['votes_for']} for, {bill['votes_against']} against."
            )


def _process_random_events(guild_id: int, year: int, 
                          policies: Dict, result: YearTickResult):
    """Roll for random events."""
    # 40% chance of an event each year
    if random.random() > 0.4:
        return
    
    event = get_random_event()
    if not event:
        return
    
    result.events.append(event)
    
    # Log to history
    log_history(
        guild_id, year, event["event_type"],
        f"Year {year}: {event['name']} - {event['description']}",
        event.get("effects", {})
    )
    
    # Apply effects (simplified - just log for now)
    # In a full implementation, you'd apply multipliers to the next tick


def _generate_year_summary(result: YearTickResult) -> str:
    """Generate a summary string for the year."""
    lines = [f"Year {result.year} Summary:"]
    
    if result.deaths:
        lines.append(f"  - {len(result.deaths)} citizen(s) passed away")
    
    if result.income_paid > 0:
        lines.append(f"  - ₵{result.income_paid:,.0f} paid in wages")
    
    if result.business_profits > 0:
        lines.append(f"  - ₵{result.business_profits:,.0f} in business profits")
    
    if result.taxes_collected > 0:
        lines.append(f"  - ₵{result.taxes_collected:,.0f} collected in taxes")
    
    if result.ubi_paid > 0:
        lines.append(f"  - ₵{result.ubi_paid:,.0f} paid in welfare/UBI")
    
    if result.rent_collected > 0:
        lines.append(f"  - ₵{result.rent_collected:,.0f} in rent collected")
    
    if result.events:
        for e in result.events:
            lines.append(f"  - EVENT: {e['name']}")
    
    if result.elections_triggered:
        lines.append(f"  - Elections needed: {', '.join(result.elections_triggered)}")
    
    if result.bills_resolved:
        passed = sum(1 for b in result.bills_resolved if b["status"] == "passed")
        lines.append(f"  - {len(result.bills_resolved)} bill(s) resolved ({passed} passed)")
    
    return "\n".join(lines)


def socialize_property(guild_id: int, compensate: bool = True) -> int:
    """
    Transfer all private property to state ownership.
    Returns number of properties transferred.
    """
    from db.economy import get_connection
    import json
    
    conn = get_connection()
    c = conn.cursor()
    
    # Get all private properties
    c.execute("SELECT * FROM properties WHERE guild_id = ? AND owner_id != 0", (guild_id,))
    properties = c.fetchall()
    
    count = 0
    for prop in properties:
        prop = dict(prop)
        former_owner = prop["owner_id"]
        value = prop["value"]
        
        # Transfer to state (owner_id = 0)
        c.execute("UPDATE properties SET owner_id = 0, tenant_id = NULL WHERE id = ?", 
                 (prop["id"],))
        
        # Compensate former owner (optional)
        if compensate and former_owner:
            compensation = value * 0.5  # 50% compensation
            c.execute(
                "UPDATE citizens SET balance = balance + ? WHERE guild_id = ? AND user_id = ?",
                (compensation, guild_id, former_owner)
            )
        
        count += 1
    
    conn.commit()
    conn.close()
    
    return count
