//! High-performance Rust functions for IsraelGPT Discord bot.
//!
//! This module provides Rust implementations of frequently-called functions
//! that benefit from native performance, particularly for:
//! - Anti-spam timestamp tracking (called on every message)
//! - Chat activity window management (called on every message)
//! - String operations (truncation, phrase matching)
//! - Duration parsing
//! - Async database writes via channel queue

use pyo3::prelude::*;
use dashmap::DashMap;
use regex::Regex;
use std::collections::VecDeque;
use std::sync::LazyLock;
use std::sync::mpsc::{self, Sender, Receiver};
use std::thread;
use std::sync::{Arc, Mutex};

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

// ============================================
// Database Writer with async queue
// ============================================

/// A database write operation to be queued
#[derive(Clone)]
enum DbWriteOp {
    Transcription {
        guild_id: u64,
        channel_id: u64,
        user_id: u64,
        content: String,
        username: String,
        duration_secs: f64,
    },
    Generic {
        table: String,
        data: String, // JSON serialized
    },
    Shutdown,
}

/// Async database writer that queues writes to a background thread.
/// This prevents database writes from blocking the Python async loop.
#[pyclass]
struct DatabaseWriter {
    sender: Sender<DbWriteOp>,
    pending_count: Arc<Mutex<usize>>,
}

#[pymethods]
impl DatabaseWriter {
    #[new]
    fn new() -> PyResult<Self> {
        let (sender, receiver): (Sender<DbWriteOp>, Receiver<DbWriteOp>) = mpsc::channel();
        let pending_count = Arc::new(Mutex::new(0usize));
        let pending_clone = pending_count.clone();

        // Spawn background thread to process writes
        thread::spawn(move || {
            DatabaseWriter::process_writes(receiver, pending_clone);
        });

        Ok(DatabaseWriter { sender, pending_count })
    }

    /// Queue a transcription to be saved.
    fn queue_transcription(
        &self,
        guild_id: u64,
        channel_id: u64,
        user_id: u64,
        content: String,
        username: String,
        duration_secs: f64,
    ) -> PyResult<()> {
        let op = DbWriteOp::Transcription {
            guild_id,
            channel_id,
            user_id,
            content,
            username,
            duration_secs,
        };
        
        if let Ok(mut count) = self.pending_count.lock() {
            *count += 1;
        }
        
        self.sender.send(op).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Failed to queue write: {}", e))
        })
    }

    /// Queue a generic database write (JSON data).
    fn queue_write(&self, table: String, json_data: String) -> PyResult<()> {
        let op = DbWriteOp::Generic {
            table,
            data: json_data,
        };
        
        if let Ok(mut count) = self.pending_count.lock() {
            *count += 1;
        }
        
        self.sender.send(op).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Failed to queue write: {}", e))
        })
    }

    /// Get the number of pending writes.
    fn pending_writes(&self) -> usize {
        self.pending_count.lock().map(|c| *c).unwrap_or(0)
    }

    /// Flush all pending writes (blocks until complete).
    fn flush(&self) -> PyResult<()> {
        // Wait for pending count to reach 0
        loop {
            let count = self.pending_count.lock().map(|c| *c).unwrap_or(0);
            if count == 0 {
                break;
            }
            thread::sleep(std::time::Duration::from_millis(10));
        }
        Ok(())
    }
}

impl DatabaseWriter {
    /// Background thread that processes write operations.
    fn process_writes(receiver: Receiver<DbWriteOp>, pending_count: Arc<Mutex<usize>>) {
        // We'll call back into Python to do the actual SQLite write
        // This is a queue processor that batches operations

        for op in receiver {
            match op {
                DbWriteOp::Shutdown => break,
                DbWriteOp::Transcription { guild_id, channel_id, user_id, content, username, duration_secs } => {
                    // Call Python to save - using pyo3's GIL
                    Python::with_gil(|py| {
                        let result = py.run_bound(
                            &format!(
                                r#"
from db.transcriptions import save_transcription
save_transcription({}, {}, {}, {}, {}, {})
"#,
                                guild_id,
                                channel_id, 
                                user_id,
                                repr_string(&content),
                                repr_string(&username),
                                duration_secs
                            ),
                            None,
                            None,
                        );
                        if let Err(e) = result {
                            eprintln!("DB write failed: {}", e);
                        }
                    });
                }
                DbWriteOp::Generic { table, data } => {
                    Python::with_gil(|py| {
                        let result = py.run_bound(
                            &format!(
                                r#"
import json
data = json.loads({})
# Generic write handler - implement per table
print(f"Generic write to {{}}: {{data}}")
"#,
                                repr_string(&data),
                                table
                            ),
                            None,
                            None,
                        );
                        if let Err(e) = result {
                            eprintln!("DB write failed: {}", e);
                        }
                    });
                }
            }

            // Decrement pending count
            if let Ok(mut count) = pending_count.lock() {
                *count = count.saturating_sub(1);
            }
        }
    }
}

impl Drop for DatabaseWriter {
    fn drop(&mut self) {
        let _ = self.sender.send(DbWriteOp::Shutdown);
    }
}

/// Helper to create a Python repr string
fn repr_string(s: &str) -> String {
    format!("\"{}\"", s.replace('\\', "\\\\").replace('"', "\\\"").replace('\n', "\\n"))
}

/// Python module definition
#[pymodule]
fn israelgpt_core(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(truncate, m)?)?;
    m.add_function(wrap_pyfunction!(parse_duration_secs, m)?)?;
    m.add_function(wrap_pyfunction!(text_contains_phrase, m)?)?;
    m.add_class::<ActivityTrackerRust>()?;
    m.add_class::<DatabaseWriter>()?;
    Ok(())
}
