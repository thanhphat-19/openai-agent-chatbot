# OpenAI Agent Chatbot

An AI chat service built with the OpenAI Agents SDK, FastAPI, and PostgreSQL — split into two independently deployable services.

---

## Architecture

```
[Client]
   ↓ HTTP / SSE
[chatbot-be]  ─────────────────────►  [chatbot-ai-service]
  FastAPI + PostgreSQL               FastAPI + OpenAI Agents SDK
  sessions, history, DB              agent execution, SSE streaming
```

- **`chatbot-be`** — public-facing API. Manages sessions and messages in PostgreSQL, proxies streaming to the AI service.
- **`chatbot-ai-service`** — internal AI service. Stateless. Accepts message history, runs `Runner.run_streamed()`, emits SSE text deltas.
  
The streaming endpoint returns Server-Sent Events in the following format:
```bash 
  event: message.delta
  data: {"content": "Paris"}

  event: message.completed
  data: {"status": "done"}
```
### Tech Stack

- FastAPI
- OpenAI Agents SDK
- PostgreSQL
- SQLAlchemy + Alembic
- Docker & Docker Compose
- Pytest
---

## Request Flow

![Request Flow Diagram](./request_flow.png)


## Prerequisites

- Docker + Docker Compose
- An [OpenAI API key](https://platform.openai.com/api-keys)


---

## Quick Start

### 1. Configure environment

```bash
# chatbot-ai-service
cp chatbot-ai-service/.env.example chatbot-ai-service/.env
# Edit chatbot-ai-service/.env and set: OPENAI_API_KEY=sk-...

# chatbot-be
cp chatbot-be/.env.example chatbot-be/.env
# Edit chatbot-be/.env if needed
```

### 2. Start all services

```bash
docker compose up --build
```

This will:
1. Start PostgreSQL and wait until healthy
2. Start `chatbot-ai-service` on port `8001` and wait until healthy
3. Start `chatbot-be` on port `8000`, run `alembic upgrade head`, then start the API

**API available at: `http://localhost:8000`**

### 3. Try it out

```bash
# Stream a chat response
curl -N -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
    "user_id": "user-123",
    "message": "What is the capital of France?"
  }'

# Get conversation history
curl "http://localhost:8000/api/v1/sessions/a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11/history?user_id=user-123"

# Delete a session
curl -X DELETE "http://localhost:8000/api/v1/sessions/a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11?user_id=user-123"
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/chat/stream` | Stream a chat response (SSE) |
| `GET` | `/api/v1/sessions/{session_id}/history` | Get session message history |
| `DELETE` | `/api/v1/sessions/{session_id}` | Delete session and messages |
| `GET` | `/api/v1/health` | Health check |

### Example: Chat Stream

```bash
curl -N -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
    "user_id": "user-123",
    "message": "What is the capital of France?"
  }'
```

### Example: Get History

```bash
curl "http://localhost:8000/api/v1/sessions/a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11/history?user_id=user-123"
```

---

## Running Tests

### chatbot-ai-service unit tests (no DB, no API key needed)

```bash
cd chatbot-ai-service
pip install -r requirements.txt
pytest tests/unit/ -v
```

### chatbot-be integration tests (requires local PostgreSQL)

```bash
# Start local DB first
docker run -d --name chatbot-test-db \
  -e POSTGRES_USER=chatbot -e POSTGRES_PASSWORD=chatbot -e POSTGRES_DB=chatbot_test \
  -p 5432:5432 postgres:16-alpine

cd chatbot-be
pip install -r requirements.txt
export TEST_DATABASE_URL=postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot_test
pytest tests/integration/ -v
```

---

## Database Migrations

```bash
cd chatbot-be

# Apply migrations
alembic upgrade head

# Create a new migration after model changes
alembic revision --autogenerate -m "describe_change"
```

---

## Design Choices & Trade-offs

### 1. Why OpenAI Agents SDK (instead of LangGraph)

#### OpenAI Agents SDK Advantages

- **Simpler code** — less boilerplate than `StateGraph` + node definitions
- **Built-in guardrails** — `InputGuardrail` / `OutputGuardrail` out of the box
- **Native OpenAI integration** — best performance with OpenAI models
- **Easier handoffs** — agent-to-agent delegation is a first-class concept

#### OpenAI Agents SDK Limitations

- **Less deterministic routing** — LLM decides handoffs; edge cases harder to debug
- **No explicit state typing** — LangGraph's `TypedDict` state is more structured
- **Less observable by default** — LangGraph + Langfuse callbacks are more granular
- **Node-level streaming control** — LangGraph streams per-node; OpenAI SDK streams by event type

### 2. Two-Service Architecture

**Decision:** Split the system into two independent services:
- **`chatbot-ai-service`** — handles AI execution only: runs the OpenAI agent, streams SSE responses, manages prompt logic. Stateless, no database access.
- **`chatbot-be`** — handles backend concerns only: session management, persistence, user ownership validation, API contracts. Does not know about agent internals.

**Why separate:**
- **Single Responsibility** — each service has one clear job. The AI service doesn't need to understand database schemas or authentication. The backend doesn't need to understand agent prompts or streaming protocols.
- **Independent evolution** — I can swap the LLM provider (OpenAI → Anthropic), add tool calling, or change the agent framework without touching any database code. The backend can add rate limiting, auth middleware, or analytics without redeploying the AI service.
- **Team scalability** — in a larger org, AI engineers work on `chatbot-ai-service`, backend engineers work on `chatbot-be`, and they communicate through a clean HTTP/SSE contract.

**Trade-off:** Two services mean more deployment complexity (two containers, two health checks) and an SSE proxy layer in `chatbot-be` that re-streams events from the AI service. I chose the split here to demonstrate production-oriented architecture


### 3. Streaming Failure — Partial Response Handling

If streaming fails midway (network drop, LLM provider error), should a partial assistant response be persisted?

**Decision: do not persist partial responses.**

- **Pros:** Data stays clean — no incomplete messages, no need for `is_partial` flags or special UI handling.
- **Cons:** If a user sees partial streamed text and the connection drops, that text won't appear in their history after reload.

**Trade-off:** Choosing data integrity over UX consistency. Users lose partial responses on connection failure, but the system avoids incomplete state.
