"""Economy domain service with Rust-backed hot paths."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional

from db.economy import (
    get_or_create_nation,
    get_or_create_citizen,
    update_citizen,
    transfer_balance,
    get_all_policies,
    get_jobs,
    get_job,
    create_default_jobs,
    get_businesses,
    create_business,
    get_properties,
    create_property,
    get_parties,
    create_party,
    join_party,
    get_history,
    log_history,
)
from .rust_adapter import EconomyMath


@dataclass
class OperationResult:
    success: bool
    message: str = ""
    data: Optional[Dict] = None


@dataclass
class WorkResult:
    success: bool
    message: str = ""
    earnings: float = 0.0
    xp_gain: int = 0
    job_name: Optional[str] = None
    currency_symbol: str = "?"


@dataclass
class ProfileData:
    citizen: Dict
    nation: Dict
    class_tier: str
    job: Optional[Dict]
    party_name: str
    properties: List[Dict]
    businesses: List[Dict]


class EconomyService:
    """Encapsulates economy operations for reuse and testing."""

    STARTUP_COST = 5000
    PROPERTY_PRICES = {"residential": 10_000, "commercial": 25_000}

    def __init__(self) -> None:
        pass

    def _math(self, guild_id: int) -> EconomyMath:
        policies = get_all_policies(guild_id)
        return EconomyMath(policies)

    def get_profile(self, guild_id: int, user_id: int) -> ProfileData:
        citizen = get_or_create_citizen(guild_id, user_id)
        nation = get_or_create_nation(guild_id)
        policies = get_all_policies(guild_id)
        math = EconomyMath(policies)

        class_tier = math.class_tier(citizen["balance"])
        job = get_job(citizen["job_id"]) if citizen.get("job_id") else None

        party_name = "Independent"
        if citizen.get("party_id"):
            for party in get_parties(guild_id):
                if party["id"] == citizen["party_id"]:
                    party_name = party["name"]
                    break

        properties = get_properties(guild_id, owner_id=user_id)
        businesses = get_businesses(guild_id, owner_id=user_id)

        return ProfileData(
            citizen=citizen,
            nation=nation,
            class_tier=class_tier,
            job=job,
            party_name=party_name,
            properties=properties,
            businesses=businesses,
        )

    def work(self, guild_id: int, user_id: int) -> WorkResult:
        citizen = get_or_create_citizen(guild_id, user_id)
        nation = get_or_create_nation(guild_id)
        policies = get_all_policies(guild_id)
        math = EconomyMath(policies)

        job_id = citizen.get("job_id")
        if not job_id:
            return WorkResult(False, "You don't have a job. Use `/jobs` to pick one.")

        job = get_job(job_id)
        if not job:
            return WorkResult(False, "Your job no longer exists. Pick a new one.")

        seed_a, seed_b = EconomyMath.seeds()
        earnings = math.work_payout(job["salary"], int(citizen.get("work_xp", 0)), seed_a, seed_b)

        if job["sector"] == "public":
            transfer_balance(guild_id, 0, user_id, earnings)
        else:
            update_citizen(guild_id, user_id, balance=citizen["balance"] + earnings)

        xp_gain = random.randint(5, 15)
        update_citizen(guild_id, user_id, work_xp=citizen.get("work_xp", 0) + xp_gain)

        return WorkResult(
            True,
            f"Finished a shift as a {job['name']}.",
            earnings=earnings,
            xp_gain=xp_gain,
            job_name=job["name"],
            currency_symbol=nation["currency_symbol"],
        )

    def list_jobs(self, guild_id: int) -> Dict:
        jobs = get_jobs(guild_id)
        if not jobs:
            create_default_jobs(guild_id)
            jobs = get_jobs(guild_id)
        nation = get_or_create_nation(guild_id)
        return {"jobs": jobs, "currency_symbol": nation["currency_symbol"]}

    def set_job(self, guild_id: int, user_id: int, action: str, name: str = "") -> OperationResult:
        citizen = get_or_create_citizen(guild_id, user_id)
        action_lower = action.lower()

        if action_lower == "take":
            if not name:
                return OperationResult(False, "Specify a job name.")

            jobs = get_jobs(guild_id)
            job = next((j for j in jobs if j["name"].lower() == name.lower()), None)
            if not job:
                return OperationResult(False, f"Job '{name}' not found.")

            work_level = citizen.get("work_xp", 0) // 500
            if work_level < job["required_level"]:
                return OperationResult(
                    False,
                    f"This job requires level {job['required_level']}. You are level {work_level}.",
                )

            update_citizen(guild_id, user_id, job_id=job["id"])
            return OperationResult(True, f"You are now employed as **{job['name']}**.")

        if action_lower == "quit":
            if not citizen.get("job_id"):
                return OperationResult(False, "You do not have a job to quit.")

            update_citizen(guild_id, user_id, job_id=None)
            return OperationResult(True, "You quit your job.")

        return OperationResult(False, "Unknown action. Use `take` or `quit`.")

    def balance(self, guild_id: int, user_id: int) -> OperationResult:
        citizen = get_or_create_citizen(guild_id, user_id)
        nation = get_or_create_nation(guild_id)
        return OperationResult(
            True,
            "",
            {
                "balance": citizen["balance"],
                "currency_symbol": nation["currency_symbol"],
            },
        )

    def pay_user(self, guild_id: int, from_id: int, to_id: int, amount: float) -> OperationResult:
        if from_id == to_id:
            return OperationResult(False, "You cannot pay yourself.")
        if amount <= 0:
            return OperationResult(False, "Amount must be positive.")

        payer = get_or_create_citizen(guild_id, from_id)
        nation = get_or_create_nation(guild_id)

        if payer["balance"] < amount:
            return OperationResult(False, "Insufficient funds.")

        get_or_create_citizen(guild_id, to_id)
        if transfer_balance(guild_id, from_id, to_id, amount):
            return OperationResult(
                True,
                f"Paid {nation['currency_symbol']}{amount:,.2f}.",
                {"amount": amount, "currency_symbol": nation["currency_symbol"]},
            )
        return OperationResult(False, "Transfer failed.")

    def start_business(self, guild_id: int, owner_id: int, name: str) -> OperationResult:
        citizen = get_or_create_citizen(guild_id, owner_id)
        nation = get_or_create_nation(guild_id)

        if citizen["balance"] < self.STARTUP_COST:
            return OperationResult(
                False,
                f"Starting a business costs {nation['currency_symbol']}{self.STARTUP_COST:,}.",
            )

        update_citizen(guild_id, owner_id, balance=citizen["balance"] - self.STARTUP_COST)
        biz_id = create_business(
            guild_id,
            owner_id,
            name,
            "general",
            capital=self.STARTUP_COST,
            year=nation["current_year"],
        )
        return OperationResult(
            True,
            f"{name} founded! (id={biz_id})",
            {"business_id": biz_id, "cost": self.STARTUP_COST},
        )

    def list_businesses(self, guild_id: int, owner_id: Optional[int]) -> Dict:
        businesses = get_businesses(guild_id, owner_id=owner_id)
        nation = get_or_create_nation(guild_id)
        return {"businesses": businesses, "currency_symbol": nation["currency_symbol"]}

    def buy_property(self, guild_id: int, owner_id: int, property_type: str, name: str) -> OperationResult:
        property_key = property_type.lower()
        if property_key not in self.PROPERTY_PRICES:
            return OperationResult(False, "Property type must be residential or commercial.")

        price = self.PROPERTY_PRICES[property_key]
        citizen = get_or_create_citizen(guild_id, owner_id)
        nation = get_or_create_nation(guild_id)
        policies = get_all_policies(guild_id)
        max_props = policies.get("max_properties_per_person", 10)
        current_props = get_properties(guild_id, owner_id=owner_id)

        if citizen["balance"] < price:
            return OperationResult(
                False,
                f"{property_key.title()} property costs {nation['currency_symbol']}{price:,}.",
            )

        if len(current_props) >= max_props:
            return OperationResult(False, f"You can only own {max_props} properties.")

        update_citizen(guild_id, owner_id, balance=citizen["balance"] - price)
        rent = price * 0.05
        prop_id = create_property(guild_id, owner_id, name, property_key, price, rent)
        return OperationResult(
            True,
            f"Purchased {name} ({property_key}) for {nation['currency_symbol']}{price:,}.",
            {"property_id": prop_id, "rent": rent, "price": price},
        )

    def list_properties(self, guild_id: int, owner_id: Optional[int]) -> Dict:
        properties = get_properties(guild_id, owner_id=owner_id)
        nation = get_or_create_nation(guild_id)
        return {"properties": properties, "currency_symbol": nation["currency_symbol"]}

    def party_action(self, guild_id: int, user_id: int, action: str, name: str = "") -> OperationResult:
        citizen = get_or_create_citizen(guild_id, user_id)
        nation = get_or_create_nation(guild_id)
        action_lower = action.lower()

        if action_lower == "list":
            parties = get_parties(guild_id)
            return OperationResult(True, "", {"parties": parties, "year": nation["current_year"]})

        if action_lower == "create":
            if not name:
                return OperationResult(False, "Specify a party name.")
            if citizen.get("party_id"):
                return OperationResult(False, "Leave your current party first.")

            party_id = create_party(guild_id, name, user_id, nation["current_year"])
            log_history(
                guild_id,
                nation["current_year"],
                "party_founded",
                f"User {user_id} founded the party '{name}'",
            )
            return OperationResult(True, f"{name} party founded.", {"party_id": party_id})

        if action_lower == "join":
            if not name:
                return OperationResult(False, "Specify a party name.")
            if citizen.get("party_id"):
                return OperationResult(False, "Leave your current party first.")

            parties = get_parties(guild_id)
            party = next((p for p in parties if p["name"].lower() == name.lower()), None)
            if not party:
                return OperationResult(False, f"Party '{name}' not found.")

            join_party(guild_id, user_id, party["id"])
            return OperationResult(True, f"Joined {party['name']}.")

        if action_lower == "leave":
            if not citizen.get("party_id"):
                return OperationResult(False, "You are not in a party.")

            update_citizen(guild_id, user_id, party_id=None)
            return OperationResult(True, "You left your party.")

        return OperationResult(False, "Unknown action. Use: list, create, join, leave.")

    def history(self, guild_id: int, limit: int = 10) -> Dict:
        events = get_history(guild_id, limit=min(limit, 25))
        nation = get_or_create_nation(guild_id)
        return {"events": events, "nation": nation}

    def treasury(self, guild_id: int) -> Dict:
        nation = get_or_create_nation(guild_id)
        return {
            "currency_symbol": nation["currency_symbol"],
            "treasury": nation["treasury"],
            "current_year": nation["current_year"],
            "name": nation["name"],
        }

    def set_heir(self, guild_id: int, user_id: int, heir_id: int) -> OperationResult:
        if user_id == heir_id:
            return OperationResult(False, "You cannot be your own heir.")
        update_citizen(guild_id, user_id, heir_id=heir_id)
        return OperationResult(True, "Heir updated.")
