"""
Prometheus metrics helpers for Guildest.

Exports a small HTTP server on METRICS_PORT to be scraped by Prometheus.
"""

from __future__ import annotations

import threading
from typing import Optional

from prometheus_client import Counter, Histogram, start_http_server

# Counters
MESSAGE_COUNTER = Counter(
    "guildest_messages_total",
    "Total number of messages seen by the bot",
    ["guild_id"],
)

COMMAND_COUNTER = Counter(
    "guildest_commands_total",
    "Total number of commands executed",
    ["guild_id", "command"],
)

ERROR_COUNTER = Counter(
    "guildest_errors_total",
    "Total number of errors encountered",
    ["source"],
)

SPAM_COUNTER = Counter(
    "guildest_spam_events_total",
    "Total number of spam detections",
    ["guild_id"],
)

LLM_REQUEST_COUNTER = Counter(
    "guildest_llm_requests_total",
    "Total number of LLM requests",
    ["model", "status"],
)

COMMAND_DURATION_HISTOGRAM = Histogram(
    "guildest_command_duration_seconds",
    "Command execution duration in seconds",
    ["guild_id", "command"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

LLM_DURATION_HISTOGRAM = Histogram(
    "guildest_llm_duration_seconds",
    "LLM request duration in seconds",
    ["model"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 30.0),
)

_server_started = False
_server_lock = threading.Lock()


def start_metrics_server(port: int = 8000) -> None:
    """Start the Prometheus HTTP metrics server once."""
    global _server_started
    with _server_lock:
        if _server_started:
            return
        # start_http_server is non-blocking and runs a background thread
        start_http_server(port)
        _server_started = True


def count_message(guild_id: Optional[int]) -> None:
    MESSAGE_COUNTER.labels(guild_id=str(guild_id or "unknown")).inc()


def count_command(guild_id: Optional[int], command_name: str) -> None:
    COMMAND_COUNTER.labels(
        guild_id=str(guild_id or "unknown"),
        command=command_name or "unknown",
    ).inc()


def count_error(source: str) -> None:
    ERROR_COUNTER.labels(source=source or "unknown").inc()


def count_spam(guild_id: Optional[int]) -> None:
    SPAM_COUNTER.labels(guild_id=str(guild_id or "unknown")).inc()


def count_llm_request(model: str, status: str) -> None:
    LLM_REQUEST_COUNTER.labels(model=model or "unknown", status=status or "unknown").inc()


def observe_command_duration(guild_id: Optional[int], command_name: str, duration: float) -> None:
    COMMAND_DURATION_HISTOGRAM.labels(
        guild_id=str(guild_id or "unknown"),
        command=command_name or "unknown",
    ).observe(duration)


def observe_llm_duration(model: str, duration: float) -> None:
    LLM_DURATION_HISTOGRAM.labels(model=model or "unknown").observe(duration)
