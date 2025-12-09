# Gateway → Queue → Worker

Repository layout now follows a small pipeline to keep Discord-facing code lean and push heavy work to background workers.

## Components
- **Gateway** (`src/main.py`, `core/events.py`): handles Discord events, spam/leveling, and enqueues heavy work (LLM replies, safety checks) to Redis.
- **Queue** (`taskqueue/`): Redis-backed list at `<namespace>:tasks` plus per-job result lists at `<namespace>:results:<job_id>`. Defaults are driven by `REDIS_URL` and `TASK_NAMESPACE`.
- **Worker** (`microservices/worker/main.py`): pulls from the task list and runs handlers (`llm_reply`, `safety_scan`) using existing services, then publishes results back for the gateway to respond in Discord.
- **Other microservices**: command sync and status notifier remain separate. High-volume services can be split further (consider Rust for CPU-bound/high-QPS pieces per repo guidelines).

## Redis contract
- **Task payload**: `{"job_id", "job_type", "payload", "requested_by", "result_ttl"}`
- **Queues**: tasks in `<namespace>:tasks`; results in `<namespace>:results:<job_id>` with TTL to avoid leaks.
- **Timeouts**: gateway waits ~30s for safety scans, ~75s for LLM replies; timeouts are logged and dropped to keep Discord responsive.

## Adding jobs
1. Add a handler in `microservices/worker/main.py` and register it in `HANDLERS`.
2. Enqueue from the gateway via `taskqueue.get_task_queue().enqueue(...)`, then await `wait_for_result` in a background task.
3. Keep payloads JSON-serializable; compute Discord-only context (e.g., channel history) in the gateway before enqueuing.

## Database migration path (SQLite → Postgres)
Central connection handling lives in `src/db/engine.py` with an opt-in guard `ALLOW_EXPERIMENTAL_POSTGRES`. Steps to complete the migration:
1. Convert SQL placeholders from `?` to `%s` (or move to a query builder/ORM) across the `db/` modules; add migrations (Alembic) instead of ad-hoc table creation.
2. Consolidate per-feature SQLite files into a single Postgres schema; introduce connection pooling suitable for workers.
3. Enable `ALLOW_EXPERIMENTAL_POSTGRES=true` and point `DATABASE_URL` at Postgres; run migrations and smoke tests.
4. For the highest-volume paths (spam detection, queue workers), consider porting handlers to Rust for throughput while keeping the Redis contract intact.

Until those steps are complete, SQLite remains the default and safest backend.
