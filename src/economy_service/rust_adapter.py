"""Rust-backed math helpers for the economy domain."""

from __future__ import annotations

import random
import time
from typing import Dict, Optional

try:
    from israelgpt_core import EconomyEngine
except Exception:
    EconomyEngine = None


class EconomyMath:
    """Wraps the Rust economy engine with Python fallbacks."""

    def __init__(self, policies: Dict):
        self.elite_threshold = policies.get("elite_class_threshold", 100_000)
        self.middle_threshold = policies.get("working_class_threshold", 10_000)
        self.min_wage = policies.get("min_wage", 400)
        self.income_tax_rate = policies.get("income_tax_rate", 0.15)
        self.wealth_tax_rate = policies.get("wealth_tax_rate", 0.0)

        self.engine: Optional[EconomyEngine] = None
        if EconomyEngine is not None:
            try:
                self.engine = EconomyEngine(
                    elite_threshold=float(self.elite_threshold),
                    middle_threshold=float(self.middle_threshold),
                    min_wage=float(self.min_wage),
                    income_tax_rate=float(self.income_tax_rate),
                    wealth_tax_rate=float(self.wealth_tax_rate),
                )
            except Exception:
                # Graceful fallback if wheel is missing or misbuilt
                self.engine = None

    def class_tier(self, balance: float) -> str:
        """Return working/middle/elite tier."""
        if self.engine:
            try:
                return str(self.engine.classify(float(balance)))
            except Exception:
                pass

        if balance >= self.elite_threshold:
            return "elite"
        if balance >= self.middle_threshold:
            return "middle"
        return "working"

    def work_payout(self, annual_salary: float, work_xp: int, seed_a: int, seed_b: int) -> float:
        """Calculate a work payout with XP bonus and variance."""
        if self.engine:
            try:
                return float(self.engine.work_payout(float(annual_salary), int(work_xp), seed_a, seed_b))
            except Exception:
                pass

        base_pay = max(annual_salary, self.min_wage) / 365 * 5
        xp_bonus = 1 + (work_xp / 1000)
        rng = random.Random(seed_a ^ seed_b)
        variance = 0.8 + rng.random() * 0.4
        return base_pay * xp_bonus * variance

    def income_tax(self, income: float) -> float:
        if self.engine:
            try:
                return float(self.engine.income_tax(float(income)))
            except Exception:
                pass
        return max(0.0, income) * max(0.0, self.income_tax_rate)

    def wealth_tax(self, balance: float, threshold: float = 50_000.0) -> float:
        if self.engine:
            try:
                return float(self.engine.wealth_tax(float(balance), float(threshold)))
            except Exception:
                pass

        if balance <= threshold or self.wealth_tax_rate <= 0:
            return 0.0
        return (balance - threshold) * self.wealth_tax_rate

    @staticmethod
    def seeds() -> tuple[int, int]:
        """Generate deterministic-ish seeds for variance."""
        now_ms = int(time.time() * 1000)
        return now_ms, random.getrandbits(32)
