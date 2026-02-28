import asyncio
import json
import time
from collections.abc import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.schemas.chat import AIStreamRequest
from src.streaming.runner import iter_text_deltas

chat_router = APIRouter()


async def _sse_generator(
    request: AIStreamRequest,
    heartbeat_interval: int = 15,
) -> AsyncGenerator[str, None]:
    """Core SSE generator.

    Order:
      1. Stream agent.message.delta events (interleaved with heartbeats)
      2. Emit agent.message.done
      On error: emit agent.workflow.failed
      Finally: always cancel heartbeat task
    """
    complete_content = ""
    heartbeat_queue: asyncio.Queue[str] = asyncio.Queue()

    async def _heartbeat() -> None:
        while True:
            await asyncio.sleep(heartbeat_interval)
            await heartbeat_queue.put(
                f"event: heartbeat\ndata: {json.dumps({'ts': int(time.time())})}\n\n"
            )

    heartbeat_task = asyncio.create_task(_heartbeat())

    try:
        async for text in iter_text_deltas([m.model_dump() for m in request.messages]):
            while not heartbeat_queue.empty():
                yield heartbeat_queue.get_nowait()

            complete_content += text
            yield f"event: agent.message.delta\ndata: {json.dumps({'text': text})}\n\n"

        while not heartbeat_queue.empty():
            yield heartbeat_queue.get_nowait()

        yield (
            f"event: agent.message.done\n"
            f"data: {json.dumps({'session_id': request.session_id})}\n\n"
        )

    except Exception as e:
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
    """Stream a chat response using Server-Sent Events.

    Accepts a message history and streams text deltas from the agent.
    """
    return StreamingResponse(
        _sse_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
