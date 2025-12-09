"""Background worker that processes queued tasks."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Awaitable, Callable, Dict

# Load env vars for local runs
from dotenv import load_dotenv

# Ensure src/ is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

load_dotenv()

from services.llm import classify_message_safety, generate_professional_reply, get_active_users_context  # noqa: E402
from taskqueue import QueueTask, get_task_queue  # noqa: E402


Handler = Callable[[QueueTask], Awaitable[Dict]]


async def handle_llm_reply(task: QueueTask) -> Dict:
    payload = task.payload
    prompt = payload.get("prompt") or payload.get("message") or ""
    guild_id = payload.get("guild_id")
    active_user_ids = [int(uid) for uid in payload.get("active_user_ids", []) if uid is not None]

    active_users_history = {}
    if guild_id is not None and active_user_ids:
        active_users_history = await get_active_users_context(
            guild_id=guild_id,
            user_ids=active_user_ids,
            max_per_user=5,
        )

    reply = await generate_professional_reply(
        user_message=prompt,
        username=payload.get("username") or "friend",
        guild_name=payload.get("guild_name"),
        guild_id=guild_id,
        user_id=payload.get("user_id"),
        channel_id=payload.get("channel_id"),
        channel_context=payload.get("channel_context"),
        active_users_history=active_users_history or None,
    )
    return {"reply": reply}


async def handle_safety_scan(task: QueueTask) -> Dict:
    payload = task.payload
    content = payload.get("content") or ""
    if not content:
        return {"verdict": None}
    verdict = await classify_message_safety(content)
    return {"verdict": verdict}


HANDLERS: Dict[str, Handler] = {
    "llm_reply": handle_llm_reply,
    "safety_scan": handle_safety_scan,
}


async def run_worker() -> None:
    queue = get_task_queue()
    print("Worker started - listening for tasks.")
    while True:
        task = await queue.pop(timeout=5)
        if task is None:
            await asyncio.sleep(0.1)
            continue

        handler = HANDLERS.get(task.job_type)
        if handler is None:
            await queue.publish_result(
                task.job_id,
                {"status": "error", "error": f"unknown job_type '{task.job_type}'"},
                ttl=task.result_ttl,
            )
            continue

        try:
            result = await handler(task)
            await queue.publish_result(
                task.job_id,
                {"status": "ok", **(result or {})},
                ttl=task.result_ttl,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            print(f"Task {task.job_id} failed: {exc}")
            await queue.publish_result(
                task.job_id,
                {"status": "error", "error": str(exc)},
                ttl=task.result_ttl,
            )


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
