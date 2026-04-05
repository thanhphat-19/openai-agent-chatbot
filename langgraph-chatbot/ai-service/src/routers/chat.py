import asyncio
import json
import time
from collections.abc import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from loguru import logger

from src.schemas.chat import AIStreamRequest
from src.streaming.runner import iter_events

chat_router = APIRouter()


async def _sse_generator(
    request: AIStreamRequest,
    heartbeat_interval: int = 15,
) -> AsyncGenerator[str, None]:
    """Core SSE generator — emits agent.message.delta, agent.step, agent.message.done."""
    complete_content = ""
    heartbeat_queue: asyncio.Queue[str] = asyncio.Queue()

    async def _heartbeat() -> None:
        while True:
            await asyncio.sleep(heartbeat_interval)
            await heartbeat_queue.put(
                f"event: heartbeat\ndata: {json.dumps({'ts': int(time.time())})}\n\n"
            )

    heartbeat_task = asyncio.create_task(_heartbeat())

    last_user = next((m.content for m in reversed(request.messages) if m.role == "user"), "")
    logger.info(f"[query] received: {last_user[:120]}")

    try:
        async for event_type, payload in iter_events([m.model_dump() for m in request.messages]):
            while not heartbeat_queue.empty():
                yield heartbeat_queue.get_nowait()

            if event_type == "text":
                complete_content += payload
                yield f"event: agent.message.delta\ndata: {json.dumps({'text': payload})}\n\n"

            elif event_type == "step":
                logger.info(f"[step] {payload}")
                yield f"event: agent.step\ndata: {json.dumps(payload)}\n\n"

        while not heartbeat_queue.empty():
            yield heartbeat_queue.get_nowait()

        yield (
            f"event: agent.message.done\n"
            f"data: {json.dumps({'session_id': request.session_id, 'full_text': complete_content})}\n\n"
        )

    except Exception as e:
        logger.exception(f"SSE stream error: {e}")
        yield (
            f"event: agent.workflow.failed\n"
            f"data: {json.dumps({'error': str(e)})}\n\n"
        )

    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass


@chat_router.post("/stream")
async def chat_stream(request: AIStreamRequest) -> StreamingResponse:
    """Stream a chat response using Server-Sent Events."""
    return StreamingResponse(
        _sse_generator(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
