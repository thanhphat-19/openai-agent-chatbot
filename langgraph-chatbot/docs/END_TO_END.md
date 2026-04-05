# LangGraph Chatbot — End-to-End Documentation

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Project Structure](#project-structure)
3. [Core Concepts](#core-concepts)
4. [Data & Vanna Setup](#data--vanna-setup)
5. [Agent Implementation](#agent-implementation)
6. [Supervisor & Routing](#supervisor--routing)
7. [Streaming & SSE](#streaming--sse)
8. [Docker Build Optimization](#docker-build-optimization)
9. [Debugging & Logging](#debugging--logging)
10. [Common Issues & Solutions](#common-issues--solutions)

---

## Architecture Overview

### High-Level Flow
```
Client (SSE) → FastAPI → Supervisor → Sub-agent(s) → Tools → DB
     ↑              ↓           ↓          ↓      ↑
   Browser    (streaming)  (ReAct)   (SQL)   SQLite
```

### Key Components
- **FastAPI**: `/v1/chat/stream` endpoint with Server-Sent Events (SSE)
- **Supervisor**: Cyclic LangGraph node that orchestrates sub-agents
- **Sub-agents**: `gen_report` (markdown) and `gen_dashboard` (ECharts JSON)
- **Tools**: `query_data` (Vanna SQL generation) and `list_tables`
- **Vanna**: Local LLM-powered SQL generation with ChromaDB vector store

---

## Project Structure

```
langgraph-chatbot/
├── ai-service/
│   ├── src/
│   │   ├── agents/
│   │   │   ├── supervisor.py          # Cyclic supervisor graph
│   │   │   ├── gen_report_agent.py    # ReAct report writer
│   │   │   └── gen_dashboard_agent.py # ReAct dashboard writer
│   │   ├── tools/
│   │   │   ├── sql_tools.py           # query_data & list_tables
│   │   │   └── vanna_setup.py         # Vanna singleton & training
│   │   ├── streaming/
│   │   │   └── runner.py              # SSE event generator
│   │   ├── routers/
│   │   │   └── chat.py                # FastAPI streaming endpoint
│   │   ├── prompts/
│   │   │   ├── router.md              # Supervisor prompt
│   │   │   ├── gen_report.md          # Report agent prompt
│   │   │   └── gen_dashboard.md       # Dashboard agent prompt
│   │   └── core/
│   │       └── config.py              # Settings & env vars
│   ├── data/
│   │   ├── train.py                   # Build-time Vanna training
│   │   └── sample.db                  # SQLite DB (prepopulated)
│   ├── scripts/
│   │   └── build_vanna_train.sh       # Docker build training script
│   ├── Dockerfile                     # Multi-stage build with caching
│   └── requirements.txt               # Pinned LangChain versions
└── docker-compose.yml
```

---

## Core Concepts

### LangGraph State
```python
class SupervisorState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    next_agent: str                # last routing decision
    completed_agents: list[str]    # agents already run this turn
```

- `messages` là shared state giữa supervisor và sub-agents
- `add_messages` reducer tự động append messages
- `completed_agents` ngăn gọi lại agent đã chạy

### ReAct Loop (Sub-agents)
```
agent_node (LLM) → tool_calls → ToolNode → tool_results → agent_node → ...
```
- LLM quyết định gọi tool hoặc kết thúc
- `ToolNode` thực thi SQL queries
- Loop cho đến khi không có `tool_calls`

### Cyclic Supervisor
```
supervisor → agent → supervisor → agent → supervisor → FINISH
```
- Mỗi agent xong quay lại supervisor để đánh giá
- Supervisor đọc full history + `completed_agents`
- Quyết định gọi agent khác hoặc `FINISH`

---

## Data & Vanna Setup

### Database Schema
```sql
CREATE TABLE monthly_metrics (
    month TEXT PRIMARY KEY,
    total_revenue REAL,
    total_orders INTEGER,
    avg_order_value REAL,
    new_customers INTEGER,
    top_category TEXT
);
```

### Vanna Training (Build-time)
```python
# data/train.py
vn = MyVanna(config={"path": "./data/chroma", "api_key": "...", "model": "gpt-4o-mini"})
vn.connect(sqlite_file="./data/sample.db")
vn.train(ddl=SCHEMA_DDL, documentation=DOC, qa=SAMPLE_QA)
```

- Training chạy trong Docker build → cached layer
- ChromaDB vector store lưu question→SQL pairs
- ONNX embeddings (~79MB) downloaded once

---

## Agent Implementation

### gen_report_agent.py
```python
async def agent_node(state: ReportState) -> dict:
    messages = state["messages"]
    if not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=_SYSTEM_PROMPT)] + messages
    
    response = await _LLM.ainvoke(messages)  # ← streaming=True
    return {"messages": [response]}
```

- System prompt injected once (first turn)
- `ainvoke` enables token streaming via LangGraph callbacks
- Returns AIMessage with tool_calls OR final markdown

### gen_dashboard_agent.py
- Same pattern as gen_report
- Final output: ECharts-compatible JSON string
- Prompt emphasizes chart structure & data mapping

---

## Supervisor & Routing

### supervisor.py
```python
async def supervisor_node(state: SupervisorState) -> dict:
    prev_agent = state.get("next_agent", "")
    completed = list(state.get("completed_agents") or [])
    if prev_agent and prev_agent not in completed:
        completed = completed + [prev_agent]

    prompt = _SUPERVISOR_PROMPT + f"\n\nAlready completed: {completed}"
    decision = await asyncio.to_thread(_SUPERVISOR_LLM.invoke, [System(prompt)] + list(state["messages"]))
    
    return {"next_agent": decision.next, "completed_agents": completed}
```

### Graph Construction
```python
g = StateGraph(SupervisorState)
g.add_node("supervisor", supervisor_node)
g.add_node("gen_report", gen_report_graph)
g.add_node("gen_dashboard", gen_dashboard_graph)

g.set_entry_point("supervisor")
g.add_conditional_edges("supervisor", _route_supervisor, {...})
g.add_edge("gen_report", "supervisor")      # ← cyclic
g.add_edge("gen_dashboard", "supervisor")   # ← cyclic
```

---

## Streaming & SSE

### runner.py
```python
async def iter_events(history):
    async for event in supervisor_graph.astream(
        input_state, stream_mode=["messages", "updates"], subgraphs=True
    ):
        namespace, stream_type, data = event
        if stream_type == "updates":
            # routing decisions → agent.step
        else:
            # token chunks → agent.message.delta
```

- `subgraphs=True` propagates token events from inside subgraphs
- `updates` stream captures state changes (routing)
- `messages` stream captures LLM token chunks

### chat.py (SSE)
```python
async for event_type, payload in iter_events():
    if event_type == "text":
        yield f"event: agent.message.delta\ndata: {json.dumps({'text': payload})}\n\n"
    elif event_type == "step":
        yield f"event: agent.step\ndata: {json.dumps(payload)}\n\n"
# After loop:
yield f"event: agent.message.done\ndata: {json.dumps({'full_text': complete_content})}\n\n"
```

---

## Docker Build Optimization

### Layer Caching Strategy
```dockerfile
# 1. Install deps (changes rarely)
COPY requirements.txt .
RUN pip install -r requirements.txt

# 2. Training layer (cached unless data/ or scripts/ change)
COPY data/ ./data/
COPY scripts/ ./scripts/
RUN ./scripts/build_vanna_train.sh

# 3. Source code (changes frequently)
COPY . .
```

### Why this matters
- Vanna training + ONNX download takes ~2 minutes
- Without caching, every `docker compose up --build` retrains
- With caching, only rebuild when `data/` or `scripts/` change

---

## Debugging & Logging

### Loguru Integration
```python
from loguru import logger

logger.info(f"[supervisor] → {decision.next} (completed: {completed})")
logger.info(f"[gen_report] turn {iteration} → tool_calls: {tools}")
logger.info(f"[query] received: {last_user[:120]}")
```

### Detailed Input Logging
```python
if iteration == 1:
    logger.info(f"[gen_report] SYSTEM PROMPT:\n{_SYSTEM_PROMPT}")
for i, m in enumerate(messages):
    role = type(m).__name__.replace("Message", "").lower()
    preview = (m.content[:200] + "...") if len(m.content) > 200 else m.content
    logger.info(f"  [{i}] {role}: {preview}")
```

### SSE Events for Debugging
- `agent.step` → routing, tool_call, tool_result
- `agent.message.delta` → every token
- `agent.message.done` → final `full_text`

---

## Common Issues & Solutions

### Issue 1: Duplicate agent execution
**Symptom:** `gen_dashboard` runs twice for same request
**Cause:** Supervisor doesn't know agent already ran
**Fix:** Track `completed_agents` in state and inject into prompt

### Issue 2: `unknown channel branch:to:__end__`
**Symptom:** LangGraph v0.5 error with `Command(goto=END)`
**Cause:** Command routing to END not supported in v0.5
**Fix:** Use conditional edge + return END constant

### Issue 3: ChromaDB telemetry spam
**Symptom:** `capture() takes 1 positional argument but 3 were given`
**Cause:** ChromaDB tries to send telemetry with wrong signature
**Fix:** `ENV ANONYMIZED_TELEMETRY=False` in Dockerfile

### Issue 4: No token streaming from subgraphs
**Symptom:** Only see final response, no deltas
**Cause:** Missing `subgraphs=True` or using `invoke` instead of `ainvoke`
**Fix:** `supervisor_graph.astream(..., subgraphs=True)` + `await _LLM.ainvoke`

### Issue 5: Router JSON output in stream
**Symptom:** Client sees raw routing decision as text
**Cause:** Filtering only top-level router messages
**Fix:** Filter by `namespace` and `node == "router"` in runner

---

## Quick Start

```bash
# 1. Build & run (first time)
docker compose up --build

# 2. Test streaming
curl -N http://localhost:8001/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Generate a monthly revenue report for 2023"}]}'

# 3. View logs
docker compose logs -f ai-service
```

---

## Extending the System

### Adding a New Agent
1. Create `src/agents/new_agent.py` with ReAct graph
2. Add node to supervisor graph
3. Update supervisor prompt to include new agent
4. Add conditional edge mapping

### Adding New Tools
1. Implement `@tool` function in `src/tools/`
2. Import and add to `_TOOLS` list in agent files
3. Update prompts to describe tool usage

### Custom Prompts
- Edit `.md` files in `src/prompts/`
- No code changes required — prompts read at runtime
- Use `{variable}` syntax if injecting via `.format()`

---

## Performance Tips

- **Docker caching:** Separate training from source code layers
- **Streaming:** Use `ainvoke` + `subgraphs=True` for token-level visibility
- **Vanna:** Pre-train at build time; cache ChromaDB + ONNX model
- **LLM:** Use `gpt-4o-mini` for fast routing; keep `streaming=True` for UX
- **State:** Keep TypedDict minimal; avoid large payloads in shared state

---

## Security Considerations

- **API keys:** Use environment variables; never commit to repo
- **SQL injection:** Vanna generates SQL; validate schema access rights
- **SSE:** No authentication in example; add JWT/session validation
- **Docker:** Run as non-root user in production
- **Rate limiting:** Add FastAPI middleware for abuse prevention
