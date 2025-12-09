"""ChronoNation Economy Database - 1 day = 1 year simulation."""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

from .engine import get_connection as get_db_connection, get_db_path

DB_PATH = get_db_path("economy.db")


class ClassTier(Enum):
    WORKING = "working"
    MIDDLE = "middle"
    ELITE = "elite"


class PropertyMode(Enum):
    CAPITALIST = "capitalist"
    SOCIALIZED = "socialized"
    COLLECTIVE = "collective"


class GovType(Enum):
    DEMOCRACY = "democracy"
    PRESIDENTIAL = "presidential"
    ONE_PARTY = "one_party"
    MONARCHY = "monarchy"


@dataclass
class Citizen:
    user_id: int
    guild_id: int
    balance: float = 1000.0
    age: int = 18
    influence: int = 0
    reputation: int = 50
    job_id: Optional[int] = None
    party_id: Optional[int] = None
    heir_id: Optional[int] = None
    is_alive: bool = True
    created_at: Optional[datetime] = None

    @property
    def class_tier(self) -> ClassTier:
        # Default thresholds, can be overridden per-guild
        if self.balance >= 100000:
            return ClassTier.ELITE
        elif self.balance >= 10000:
            return ClassTier.MIDDLE
        return ClassTier.WORKING


@dataclass
class Job:
    id: int
    guild_id: int
    name: str
    salary: float
    sector: str  # public, private
    required_level: int = 0
    description: str = ""


@dataclass
class Business:
    id: int
    guild_id: int
    owner_id: int
    name: str
    business_type: str
    capital: float = 0.0
    productivity: float = 1.0
    employee_count: int = 0
    created_year: int = 0


@dataclass
class Property:
    id: int
    guild_id: int
    owner_id: int  # user_id or 0 for state
    name: str
    property_type: str  # residential, commercial
    value: float
    rent_price: float = 0.0
    tenant_id: Optional[int] = None
    is_collective: bool = False
    collective_members: List[int] = field(default_factory=list)


@dataclass 
class Policy:
    guild_id: int
    key: str
    value: Any
    updated_at: Optional[datetime] = None


@dataclass
class Bill:
    id: int
    guild_id: int
    proposer_id: int
    policy_key: str
    new_value: str
    description: str
    votes_for: int = 0
    votes_against: int = 0
    status: str = "pending"  # pending, passed, failed
    voting_ends_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


@dataclass
class Office:
    id: int
    guild_id: int
    name: str
    holder_id: Optional[int] = None
    term_years: int = 4
    term_start_year: int = 0
    max_terms: int = 2
    terms_served: int = 0
    powers: List[str] = field(default_factory=list)


@dataclass
class Party:
    id: int
    guild_id: int
    name: str
    leader_id: int
    member_count: int = 1
    founded_year: int = 0


@dataclass
class HistoryEvent:
    id: int
    guild_id: int
    year: int
    event_type: str
    description: str
    data: Dict = field(default_factory=dict)
    created_at: Optional[datetime] = None


def get_connection():
    conn = get_db_connection("economy.db")
    try:
        conn.execute("PRAGMA foreign_keys = ON")
    except Exception:
        # Postgres or drivers that do not support PRAGMA
        pass
    return conn


def init_db():
    """Initialize all economy tables."""
    conn = get_connection()
    c = conn.cursor()

    # Nation configuration per guild
    c.execute("""
        CREATE TABLE IF NOT EXISTS nations (
            guild_id INTEGER PRIMARY KEY,
            name TEXT DEFAULT 'Unnamed Nation',
            currency_symbol TEXT DEFAULT '₵',
            currency_name TEXT DEFAULT 'Coins',
            current_year INTEGER DEFAULT 1,
            gov_type TEXT DEFAULT 'democracy',
            treasury REAL DEFAULT 10000.0,
            flag_emoji TEXT DEFAULT '🏳️',
            motto TEXT DEFAULT '',
            last_tick_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Citizens (players)
    c.execute("""
        CREATE TABLE IF NOT EXISTS citizens (
            user_id INTEGER,
            guild_id INTEGER,
            balance REAL DEFAULT 1000.0,
            age INTEGER DEFAULT 18,
            influence INTEGER DEFAULT 0,
            reputation INTEGER DEFAULT 50,
            job_id INTEGER,
            party_id INTEGER,
            heir_id INTEGER,
            work_xp INTEGER DEFAULT 0,
            last_work_at TEXT,
            is_alive INTEGER DEFAULT 1,
            death_year INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, guild_id)
        )
    """)

    # Jobs
    c.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            name TEXT,
            salary REAL,
            sector TEXT DEFAULT 'private',
            required_level INTEGER DEFAULT 0,
            description TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1
        )
    """)

    # Businesses
    c.execute("""
        CREATE TABLE IF NOT EXISTS businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            owner_id INTEGER,
            name TEXT,
            business_type TEXT,
            capital REAL DEFAULT 0.0,
            productivity REAL DEFAULT 1.0,
            employee_count INTEGER DEFAULT 0,
            created_year INTEGER DEFAULT 0
        )
    """)

    # Business employees
    c.execute("""
        CREATE TABLE IF NOT EXISTS business_employees (
            business_id INTEGER,
            user_id INTEGER,
            salary REAL,
            hired_year INTEGER,
            PRIMARY KEY (business_id, user_id)
        )
    """)

    # Properties
    c.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            owner_id INTEGER DEFAULT 0,
            name TEXT,
            property_type TEXT,
            value REAL,
            rent_price REAL DEFAULT 0.0,
            tenant_id INTEGER,
            is_collective INTEGER DEFAULT 0,
            collective_members TEXT DEFAULT '[]'
        )
    """)

    # Policies (per-guild configurable)
    c.execute("""
        CREATE TABLE IF NOT EXISTS policies (
            guild_id INTEGER,
            key TEXT,
            value TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (guild_id, key)
        )
    """)

    # Bills/Laws
    c.execute("""
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            proposer_id INTEGER,
            policy_key TEXT,
            new_value TEXT,
            description TEXT,
            votes_for INTEGER DEFAULT 0,
            votes_against INTEGER DEFAULT 0,
            voters TEXT DEFAULT '[]',
            status TEXT DEFAULT 'pending',
            voting_ends_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Government offices
    c.execute("""
        CREATE TABLE IF NOT EXISTS offices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            name TEXT,
            holder_id INTEGER,
            term_years INTEGER DEFAULT 4,
            term_start_year INTEGER DEFAULT 0,
            max_terms INTEGER DEFAULT 2,
            terms_served INTEGER DEFAULT 0,
            powers TEXT DEFAULT '[]',
            UNIQUE(guild_id, name)
        )
    """)

    # Political parties
    c.execute("""
        CREATE TABLE IF NOT EXISTS parties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            name TEXT,
            leader_id INTEGER,
            member_count INTEGER DEFAULT 1,
            founded_year INTEGER DEFAULT 0,
            UNIQUE(guild_id, name)
        )
    """)

    # Elections
    c.execute("""
        CREATE TABLE IF NOT EXISTS elections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            office_id INTEGER,
            status TEXT DEFAULT 'nominations',
            candidates TEXT DEFAULT '[]',
            votes TEXT DEFAULT '{}',
            started_at TEXT,
            ends_at TEXT
        )
    """)

    # History chronicle
    c.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            year INTEGER,
            event_type TEXT,
            description TEXT,
            data TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Random events pool
    c.execute("""
        CREATE TABLE IF NOT EXISTS event_pool (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            event_type TEXT,
            description TEXT,
            effects TEXT DEFAULT '{}',
            weight INTEGER DEFAULT 10
        )
    """)

    conn.commit()
    conn.close()
    
    _seed_default_data()


def _seed_default_data():
    """Seed default jobs and events."""
    conn = get_connection()
    c = conn.cursor()

    # Check if already seeded
    c.execute("SELECT COUNT(*) FROM event_pool")
    if c.fetchone()[0] == 0:
        # Default random events
        events = [
            ("Economic Boom", "economy", "The economy is thriving! Business profits up.", 
             '{"business_profit_mult": 1.2, "wage_mult": 1.1}', 10),
            ("Recession", "economy", "Economic downturn hits the nation.", 
             '{"business_profit_mult": 0.7, "unemployment_chance": 0.1}', 8),
            ("Housing Bubble", "property", "Property values spike dramatically.", 
             '{"property_value_mult": 1.5, "rent_mult": 1.3}', 5),
            ("Housing Crash", "property", "Property market collapses.", 
             '{"property_value_mult": 0.6, "rent_mult": 0.8}', 4),
            ("Workers Strike", "labor", "Workers demand better conditions.", 
             '{"wage_pressure": 0.15, "productivity_mult": 0.8}', 6),
            ("Tech Boom", "economy", "New technology drives growth.", 
             '{"business_profit_mult": 1.3, "job_creation": 5}', 5),
            ("Political Scandal", "political", "A scandal rocks the government.", 
             '{"gov_reputation": -20}', 7),
            ("Prosperous Year", "economy", "A year of plenty and prosperity.", 
             '{"ubi_bonus": 100, "tax_revenue_mult": 1.1}', 8),
            ("Natural Disaster", "disaster", "A disaster strikes the nation.", 
             '{"treasury_cost": 5000, "property_damage": 0.1}', 3),
            ("Cultural Festival", "social", "A grand festival boosts morale.", 
             '{"reputation_all": 5, "spending_mult": 1.1}', 6),
        ]
        c.executemany(
            "INSERT INTO event_pool (name, event_type, description, effects, weight) VALUES (?, ?, ?, ?, ?)",
            events
        )

    conn.commit()
    conn.close()


# ============ Nation Functions ============

def get_or_create_nation(guild_id: int) -> Dict:
    """Get or create nation for a guild."""
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("SELECT * FROM nations WHERE guild_id = ?", (guild_id,))
    row = c.fetchone()
    
    if not row:
        c.execute("INSERT INTO nations (guild_id) VALUES (?)", (guild_id,))
        conn.commit()
        c.execute("SELECT * FROM nations WHERE guild_id = ?", (guild_id,))
        row = c.fetchone()
    
    conn.close()
    return dict(row)


def update_nation(guild_id: int, **kwargs) -> None:
    """Update nation fields."""
    conn = get_connection()
    c = conn.cursor()
    
    sets = ", ".join(f"{k} = ?" for k in kwargs.keys())
    values = list(kwargs.values()) + [guild_id]
    
    c.execute(f"UPDATE nations SET {sets} WHERE guild_id = ?", values)
    conn.commit()
    conn.close()


def increment_year(guild_id: int) -> int:
    """Increment nation year and return new year."""
    conn = get_connection()
    c = conn.cursor()
    
    c.execute(
        "UPDATE nations SET current_year = current_year + 1, last_tick_at = ? WHERE guild_id = ?",
        (datetime.utcnow().isoformat(), guild_id)
    )
    c.execute("SELECT current_year FROM nations WHERE guild_id = ?", (guild_id,))
    year = c.fetchone()[0]
    
    conn.commit()
    conn.close()
    return year


# ============ Citizen Functions ============

def get_or_create_citizen(guild_id: int, user_id: int) -> Dict:
    """Get or create citizen record."""
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("SELECT * FROM citizens WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
    row = c.fetchone()
    
    if not row:
        c.execute(
            "INSERT INTO citizens (guild_id, user_id) VALUES (?, ?)",
            (guild_id, user_id)
        )
        conn.commit()
        c.execute("SELECT * FROM citizens WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        row = c.fetchone()
    
    conn.close()
    return dict(row)


def update_citizen(guild_id: int, user_id: int, **kwargs) -> None:
    """Update citizen fields."""
    conn = get_connection()
    c = conn.cursor()
    
    sets = ", ".join(f"{k} = ?" for k in kwargs.keys())
    values = list(kwargs.values()) + [guild_id, user_id]
    
    c.execute(f"UPDATE citizens SET {sets} WHERE guild_id = ? AND user_id = ?", values)
    conn.commit()
    conn.close()


def get_all_citizens(guild_id: int, alive_only: bool = True) -> List[Dict]:
    """Get all citizens for a guild."""
    conn = get_connection()
    c = conn.cursor()
    
    query = "SELECT * FROM citizens WHERE guild_id = ?"
    if alive_only:
        query += " AND is_alive = 1"
    
    c.execute(query, (guild_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_citizen_class(balance: float, thresholds: Dict = None) -> str:
    """Determine class tier from balance."""
    if thresholds is None:
        thresholds = {"elite": 100000, "middle": 10000}
    
    if balance >= thresholds.get("elite", 100000):
        return "elite"
    elif balance >= thresholds.get("middle", 10000):
        return "middle"
    return "working"


def transfer_balance(guild_id: int, from_id: int, to_id: int, amount: float) -> bool:
    """Transfer money between citizens. from_id=0 means treasury."""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        if from_id == 0:
            # From treasury
            c.execute("SELECT treasury FROM nations WHERE guild_id = ?", (guild_id,))
            treasury = c.fetchone()[0]
            if treasury < amount:
                return False
            c.execute("UPDATE nations SET treasury = treasury - ? WHERE guild_id = ?", (amount, guild_id))
        else:
            c.execute("SELECT balance FROM citizens WHERE guild_id = ? AND user_id = ?", (guild_id, from_id))
            row = c.fetchone()
            if not row or row[0] < amount:
                return False
            c.execute("UPDATE citizens SET balance = balance - ? WHERE guild_id = ? AND user_id = ?", 
                     (amount, guild_id, from_id))
        
        if to_id == 0:
            # To treasury
            c.execute("UPDATE nations SET treasury = treasury + ? WHERE guild_id = ?", (amount, guild_id))
        else:
            c.execute("UPDATE citizens SET balance = balance + ? WHERE guild_id = ? AND user_id = ?",
                     (amount, guild_id, to_id))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Transfer failed: {e}")
        return False
    finally:
        conn.close()


# ============ Job Functions ============

def create_default_jobs(guild_id: int):
    """Create default jobs for a new nation."""
    conn = get_connection()
    c = conn.cursor()
    
    default_jobs = [
        ("Laborer", 500, "private", 0, "Basic manual labor"),
        ("Clerk", 800, "private", 1, "Office work and administration"),
        ("Engineer", 1500, "private", 3, "Technical and engineering work"),
        ("Banker", 2000, "private", 5, "Financial services"),
        ("Bureaucrat", 1000, "public", 2, "Government administration"),
        ("Teacher", 900, "public", 2, "Public education"),
        ("Soldier", 1200, "public", 1, "National defense"),
        ("Doctor", 2500, "private", 5, "Medical services"),
    ]
    
    for name, salary, sector, level, desc in default_jobs:
        c.execute(
            "INSERT OR IGNORE INTO jobs (guild_id, name, salary, sector, required_level, description) VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, name, salary, sector, level, desc)
        )
    
    conn.commit()
    conn.close()


def get_jobs(guild_id: int) -> List[Dict]:
    """Get all active jobs for a guild."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM jobs WHERE guild_id = ? AND is_active = 1", (guild_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_job(job_id: int) -> Optional[Dict]:
    """Get a specific job."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


# ============ Policy Functions ============

DEFAULT_POLICIES = {
    "income_tax_rate": 0.15,
    "corporate_tax_rate": 0.20,
    "wealth_tax_rate": 0.0,
    "ubi_enabled": False,
    "ubi_amount": 0,
    "unemployment_benefit": 200,
    "property_rights_mode": "capitalist",
    "max_properties_per_person": 10,
    "rent_cap_percent": 0,
    "min_wage": 400,
    "max_work_actions_per_day": 3,
    "union_power": 0.5,
    "interest_rate": 0.02,
    "voting_eligibility": "all",
    "term_length_years": 4,
    "working_class_threshold": 10000,
    "elite_class_threshold": 100000,
    "death_age_min": 70,
    "death_age_max": 100,
    "inheritance_tax_rate": 0.20,
}


def get_policy(guild_id: int, key: str) -> Any:
    """Get a policy value."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM policies WHERE guild_id = ? AND key = ?", (guild_id, key))
    row = c.fetchone()
    conn.close()
    
    if row:
        try:
            return json.loads(row[0])
        except:
            return row[0]
    return DEFAULT_POLICIES.get(key)


def set_policy(guild_id: int, key: str, value: Any) -> None:
    """Set a policy value."""
    conn = get_connection()
    c = conn.cursor()
    
    value_str = json.dumps(value) if not isinstance(value, str) else value
    
    c.execute(
        "INSERT OR REPLACE INTO policies (guild_id, key, value, updated_at) VALUES (?, ?, ?, ?)",
        (guild_id, key, value_str, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def get_all_policies(guild_id: int) -> Dict[str, Any]:
    """Get all policies for a guild, with defaults."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT key, value FROM policies WHERE guild_id = ?", (guild_id,))
    rows = c.fetchall()
    conn.close()
    
    policies = DEFAULT_POLICIES.copy()
    for key, value in rows:
        try:
            policies[key] = json.loads(value)
        except:
            policies[key] = value
    return policies


# ============ Property Functions ============

def create_property(guild_id: int, owner_id: int, name: str, 
                   property_type: str, value: float, rent_price: float = 0) -> int:
    """Create a new property."""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO properties (guild_id, owner_id, name, property_type, value, rent_price) VALUES (?, ?, ?, ?, ?, ?)",
        (guild_id, owner_id, name, property_type, value, rent_price)
    )
    prop_id = c.lastrowid
    conn.commit()
    conn.close()
    return prop_id


def get_properties(guild_id: int, owner_id: Optional[int] = None) -> List[Dict]:
    """Get properties, optionally filtered by owner."""
    conn = get_connection()
    c = conn.cursor()
    
    if owner_id is not None:
        c.execute("SELECT * FROM properties WHERE guild_id = ? AND owner_id = ?", (guild_id, owner_id))
    else:
        c.execute("SELECT * FROM properties WHERE guild_id = ?", (guild_id,))
    
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def transfer_property(property_id: int, new_owner_id: int) -> None:
    """Transfer property ownership."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE properties SET owner_id = ?, tenant_id = NULL WHERE id = ?", 
             (new_owner_id, property_id))
    conn.commit()
    conn.close()


# ============ Business Functions ============

def create_business(guild_id: int, owner_id: int, name: str, 
                   business_type: str, capital: float, year: int) -> int:
    """Create a new business."""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO businesses (guild_id, owner_id, name, business_type, capital, created_year) VALUES (?, ?, ?, ?, ?, ?)",
        (guild_id, owner_id, name, business_type, capital, year)
    )
    biz_id = c.lastrowid
    conn.commit()
    conn.close()
    return biz_id


def get_businesses(guild_id: int, owner_id: Optional[int] = None) -> List[Dict]:
    """Get businesses."""
    conn = get_connection()
    c = conn.cursor()
    
    if owner_id is not None:
        c.execute("SELECT * FROM businesses WHERE guild_id = ? AND owner_id = ?", (guild_id, owner_id))
    else:
        c.execute("SELECT * FROM businesses WHERE guild_id = ?", (guild_id,))
    
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============ Party Functions ============

def create_party(guild_id: int, name: str, leader_id: int, year: int) -> int:
    """Create a political party."""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO parties (guild_id, name, leader_id, founded_year) VALUES (?, ?, ?, ?)",
        (guild_id, name, leader_id, year)
    )
    party_id = c.lastrowid
    
    # Update leader's party
    c.execute("UPDATE citizens SET party_id = ? WHERE guild_id = ? AND user_id = ?",
             (party_id, guild_id, leader_id))
    
    conn.commit()
    conn.close()
    return party_id


def get_parties(guild_id: int) -> List[Dict]:
    """Get all parties."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM parties WHERE guild_id = ?", (guild_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def join_party(guild_id: int, user_id: int, party_id: int) -> None:
    """Join a party."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE citizens SET party_id = ? WHERE guild_id = ? AND user_id = ?",
             (party_id, guild_id, user_id))
    c.execute("UPDATE parties SET member_count = member_count + 1 WHERE id = ?", (party_id,))
    conn.commit()
    conn.close()


# ============ Office Functions ============

def create_default_offices(guild_id: int, gov_type: str):
    """Create default offices based on government type."""
    conn = get_connection()
    c = conn.cursor()
    
    if gov_type == "democracy":
        offices = [
            ("Prime Minister", 4, 2, '["propose_law", "appoint_cabinet", "veto"]'),
            ("Minister of Finance", 4, 3, '["set_tax", "manage_treasury"]'),
            ("Minister of Labor", 4, 3, '["set_min_wage", "labor_policy"]'),
        ]
    elif gov_type == "presidential":
        offices = [
            ("President", 4, 2, '["executive_order", "veto", "appoint"]'),
            ("Vice President", 4, 2, '["succeed", "tiebreak"]'),
            ("Treasury Secretary", 4, 3, '["manage_treasury"]'),
        ]
    elif gov_type == "monarchy":
        offices = [
            ("Monarch", 999, 1, '["decree", "appoint", "pardon", "all"]'),
            ("Royal Advisor", 4, 5, '["advise", "propose_law"]'),
            ("Chancellor", 4, 3, '["manage_treasury", "propose_law"]'),
        ]
    else:  # one_party
        offices = [
            ("Party Chairman", 5, 3, '["all"]'),
            ("Central Committee Member", 5, 5, '["propose_law", "vote"]'),
        ]
    
    for name, term, max_terms, powers in offices:
        c.execute(
            "INSERT OR IGNORE INTO offices (guild_id, name, term_years, max_terms, powers) VALUES (?, ?, ?, ?, ?)",
            (guild_id, name, term, max_terms, powers)
        )
    
    conn.commit()
    conn.close()


def get_offices(guild_id: int) -> List[Dict]:
    """Get all offices."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM offices WHERE guild_id = ?", (guild_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def appoint_to_office(office_id: int, user_id: int, year: int) -> None:
    """Appoint someone to office."""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE offices SET holder_id = ?, term_start_year = ?, terms_served = terms_served + 1 WHERE id = ?",
        (user_id, year, office_id)
    )
    conn.commit()
    conn.close()


# ============ Bill Functions ============

def create_bill(guild_id: int, proposer_id: int, policy_key: str, 
               new_value: str, description: str, voting_hours: int = 24) -> int:
    """Create a new bill for voting."""
    conn = get_connection()
    c = conn.cursor()
    
    from datetime import timedelta
    ends_at = datetime.utcnow() + timedelta(hours=voting_hours)
    
    c.execute(
        "INSERT INTO bills (guild_id, proposer_id, policy_key, new_value, description, voting_ends_at) VALUES (?, ?, ?, ?, ?, ?)",
        (guild_id, proposer_id, policy_key, new_value, description, ends_at.isoformat())
    )
    bill_id = c.lastrowid
    conn.commit()
    conn.close()
    return bill_id


def vote_on_bill(bill_id: int, user_id: int, vote_for: bool) -> bool:
    """Cast a vote on a bill."""
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("SELECT voters, status FROM bills WHERE id = ?", (bill_id,))
    row = c.fetchone()
    if not row or row[1] != "pending":
        conn.close()
        return False
    
    voters = json.loads(row[0])
    if user_id in voters:
        conn.close()
        return False  # Already voted
    
    voters.append(user_id)
    field = "votes_for" if vote_for else "votes_against"
    
    c.execute(f"UPDATE bills SET {field} = {field} + 1, voters = ? WHERE id = ?",
             (json.dumps(voters), bill_id))
    conn.commit()
    conn.close()
    return True


def get_pending_bills(guild_id: int) -> List[Dict]:
    """Get all pending bills."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM bills WHERE guild_id = ? AND status = 'pending'", (guild_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def resolve_bill(bill_id: int) -> Dict:
    """Resolve a bill's vote."""
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("SELECT * FROM bills WHERE id = ?", (bill_id,))
    bill = dict(c.fetchone())
    
    passed = bill["votes_for"] > bill["votes_against"]
    status = "passed" if passed else "failed"
    
    c.execute("UPDATE bills SET status = ? WHERE id = ?", (status, bill_id))
    
    if passed:
        set_policy(bill["guild_id"], bill["policy_key"], bill["new_value"])
    
    conn.commit()
    conn.close()
    
    bill["status"] = status
    return bill


# ============ History Functions ============

def log_history(guild_id: int, year: int, event_type: str, 
               description: str, data: Dict = None) -> int:
    """Log an event to history."""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO history (guild_id, year, event_type, description, data) VALUES (?, ?, ?, ?, ?)",
        (guild_id, year, event_type, description, json.dumps(data or {}))
    )
    event_id = c.lastrowid
    conn.commit()
    conn.close()
    return event_id


def get_history(guild_id: int, limit: int = 20) -> List[Dict]:
    """Get recent history."""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM history WHERE guild_id = ? ORDER BY year DESC, id DESC LIMIT ?",
        (guild_id, limit)
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_random_event() -> Optional[Dict]:
    """Get a weighted random event from the pool."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM event_pool")
    events = [dict(r) for r in c.fetchall()]
    conn.close()
    
    if not events:
        return None
    
    import random
    weights = [e["weight"] for e in events]
    return random.choices(events, weights=weights, k=1)[0]


# Initialize on import
init_db()
