# Guildest Rust Core

High-performance Rust extension for the Guildest Discord bot.

## Overview

This module provides Rust implementations of frequently-called functions that benefit from native performance:

- **Anti-spam tracking** - Called on every message to detect spam
- **Chat activity detection** - Called on every message to detect active conversations
- **String operations** - Text truncation, phrase matching
- **Duration parsing** - Parse "10m", "2h", etc.

## Building

### Prerequisites

1. **Rust toolchain**: Install from https://rustup.rs/
2. **Python development headers**: Usually included with Python
3. **maturin**: `pip install maturin`

### Build for development

```bash
cd src/rust_core
maturin develop --release
```

### Build wheel for distribution

```bash
maturin build --release
```

The wheel will be in `target/wheels/`.

## Installation

After building:

```bash
pip install target/wheels/guildest_core-*.whl
```

Or for development:

```bash
maturin develop --release
```

## Usage

The Python code automatically uses Rust functions when available:

```python
# In utils/helpers.py - falls back to Python if Rust not available
try:
    from guildest_core import truncate, parse_duration_secs, text_contains_phrase
    _USE_RUST = True
except ImportError:
    _USE_RUST = False

# In core/activity.py
try:
    from guildest_core import ActivityTrackerRust
    _USE_RUST = True
except ImportError:
    _USE_RUST = False
```

## Performance

Benchmarks show approximately:
- **10x speedup** for activity tracking operations
- **5x speedup** for string operations
- **3x speedup** for duration parsing

The improvements are most noticeable under high message volume.

## Functions

### `truncate(text: str, limit: int = 1700) -> str`
Truncate text with "..." suffix if needed.

### `parse_duration_secs(duration: str) -> Optional[int]`
Parse duration strings like "10m", "2h", "1d" to seconds.

### `text_contains_phrase(text: str, phrase: str) -> bool`
Case-insensitive phrase search.

### `ActivityTrackerRust`
High-performance tracker for spam detection and chat activity:
- `check_spam(user_id, timestamp) -> (is_spam, count)`
- `record_chat_activity(guild_id, user_id, timestamp) -> should_reply`
- `clear_user(user_id)`
- `clear_guild(guild_id)`
