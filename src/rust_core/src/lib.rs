//! High-performance Rust functions for IsraelGPT Discord bot.
//!
//! This module provides Rust implementations of frequently-called functions
//! that benefit from native performance, particularly for:
//! - Anti-spam timestamp tracking (called on every message)
//! - Chat activity window management (called on every message)
//! - String operations (truncation, phrase matching)
//! - Duration parsing

use pyo3::prelude::*;
use dashmap::DashMap;
use regex::Regex;
use std::collections::VecDeque;
use std::sync::LazyLock;

/// Global spam tracker: user_id -> list of timestamps (as f64 seconds since epoch)
static SPAM_TIMESTAMPS: LazyLock<DashMap<u64, Vec<f64>>> = LazyLock::new(DashMap::new);

/// Global chat activity tracker: guild_id -> deque of (timestamp, user_id)
static CHAT_ACTIVITY: LazyLock<DashMap<u64, VecDeque<(f64, u64)>>> = LazyLock::new(DashMap::new);

/// Global chat cooldowns: guild_id -> last trigger timestamp
static CHAT_COOLDOWNS: LazyLock<DashMap<u64, f64>> = LazyLock::new(DashMap::new);

/// Duration parsing regex
static DURATION_REGEX: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^(\d+)([smhdw])$").unwrap()
});

/// Truncate text to a maximum length, appending "..." if truncated.
#[pyfunction]
#[pyo3(signature = (text, limit = 1700))]
fn truncate(text: &str, limit: usize) -> String {
    if text.len() <= limit {
        text.to_string()
    } else if limit > 3 {
        format!("{}...", &text[..limit - 3])
    } else {
        text[..limit].to_string()
    }
}

/// Parse a duration string like "10m", "2h", "1d" into seconds.
/// Returns None if the format is invalid.
#[pyfunction]
fn parse_duration_secs(duration: &str) -> Option<u64> {
    let caps = DURATION_REGEX.captures(duration)?;
    let value: u64 = caps.get(1)?.as_str().parse().ok()?;
    let unit = caps.get(2)?.as_str();

    let multiplier: u64 = match unit {
        "s" => 1,
        "m" => 60,
        "h" => 3600,
        "d" => 86400,
        "w" => 604800,
        _ => return None,
    };

    Some(value * multiplier)
}

/// Check if text contains a phrase (case-insensitive).
#[pyfunction]
fn text_contains_phrase(text: &str, phrase: &str) -> bool {
    text.to_lowercase().contains(&phrase.to_lowercase())
}

/// High-performance activity tracker for anti-spam and chat engagement.
#[pyclass]
struct ActivityTrackerRust {
    spam_window_secs: f64,
    spam_threshold: usize,
    chat_window_secs: f64,
    chat_active_window_secs: f64,
    chat_min_messages: usize,
    chat_min_users: usize,
    chat_cooldown_secs: f64,
    chat_trigger_chance: f64,
}

#[pymethods]
impl ActivityTrackerRust {
    #[new]
    #[pyo3(signature = ())]
    fn new() -> Self {
        ActivityTrackerRust {
            spam_window_secs: 10.0,
            spam_threshold: 20,
            chat_window_secs: 30.0,
            chat_active_window_secs: 20.0,
            chat_min_messages: 6,
            chat_min_users: 3,
            chat_cooldown_secs: 45.0,
            chat_trigger_chance: 0.35,
        }
    }

    /// Check if a user is spamming.
    /// Returns (is_spam, message_count_in_window).
    fn check_spam(&self, user_id: u64, now_ts: f64) -> (bool, usize) {
        let cutoff = now_ts - self.spam_window_secs;

        let mut entry = SPAM_TIMESTAMPS.entry(user_id).or_insert_with(Vec::new);
        
        // Remove old timestamps
        entry.retain(|&ts| ts > cutoff);
        
        // Add current timestamp
        entry.push(now_ts);

        let count = entry.len();
        let is_spam = count > self.spam_threshold;

        (is_spam, count)
    }

    /// Record chat activity and determine if bot should jump into conversation.
    /// Returns true if the bot should send a reply.
    fn record_chat_activity(&self, guild_id: u64, user_id: u64, now_ts: f64) -> bool {
        let cleanup_cutoff = now_ts - self.chat_window_secs;
        let active_cutoff = now_ts - self.chat_active_window_secs;

        // Get or create the activity deque for this guild
        let mut entry = CHAT_ACTIVITY.entry(guild_id).or_insert_with(VecDeque::new);

        // Add current activity
        entry.push_back((now_ts, user_id));

        // Clean old entries
        while let Some(&(ts, _)) = entry.front() {
            if ts < cleanup_cutoff {
                entry.pop_front();
            } else {
                break;
            }
        }

        // Count active messages and unique users in the active window
        let mut active_count = 0;
        let mut unique_users = std::collections::HashSet::new();

        for &(ts, uid) in entry.iter() {
            if ts >= active_cutoff {
                active_count += 1;
                unique_users.insert(uid);
            }
        }

        // Check thresholds
        if active_count < self.chat_min_messages || unique_users.len() < self.chat_min_users {
            return false;
        }

        // Check cooldown
        if let Some(last_trigger) = CHAT_COOLDOWNS.get(&guild_id) {
            if (now_ts - *last_trigger) < self.chat_cooldown_secs {
                return false;
            }
        }

        // Random chance to trigger
        let rand_val: f64 = rand_simple(now_ts, guild_id, user_id);
        if rand_val < self.chat_trigger_chance {
            CHAT_COOLDOWNS.insert(guild_id, now_ts);
            return true;
        }

        false
    }

    /// Clear tracking data for a user.
    fn clear_user(&self, user_id: u64) {
        SPAM_TIMESTAMPS.remove(&user_id);
    }

    /// Clear tracking data for a guild.
    fn clear_guild(&self, guild_id: u64) {
        CHAT_ACTIVITY.remove(&guild_id);
        CHAT_COOLDOWNS.remove(&guild_id);
    }
}

/// Simple pseudo-random function using timestamp and IDs as seed.
/// Not cryptographically secure, but fine for triggering chat responses.
fn rand_simple(ts: f64, guild_id: u64, user_id: u64) -> f64 {
    let seed = (ts.to_bits() ^ guild_id ^ user_id).wrapping_mul(0x5851_f42d_4c95_7f2d);
    let hash = seed.wrapping_add(seed >> 33).wrapping_mul(0xc4ce_b9fe_1a85_ec53);
    let result = hash.wrapping_add(hash >> 29).wrapping_mul(0x94d0_49bb_1331_11eb);
    (result as f64) / (u64::MAX as f64)
}

/// Python module definition
#[pymodule]
fn israelgpt_core(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(truncate, m)?)?;
    m.add_function(wrap_pyfunction!(parse_duration_secs, m)?)?;
    m.add_function(wrap_pyfunction!(text_contains_phrase, m)?)?;
    m.add_class::<ActivityTrackerRust>()?;
    Ok(())
}
