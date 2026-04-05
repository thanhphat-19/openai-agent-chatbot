# LangGraph Local Chatbot

A production-correct LangGraph chatbot with **true cyclic ReAct agents** for report and dashboard generation.

## Architecture

```
SupervisorGraph (LangGraph StateGraph — compiled once)
       |
  [router_node]  ← LLM → Command(goto="gen_report"|"gen_dashboard"|"general")
       |
  ┌────┴──────────────────┐
  |                       |
GenReportSubgraph    GenDashboardSubgraph
(ReAct loop)         (ReAct loop)

Each subgraph:
  [agent_node] ←──────────────┐
       |                      │  CYCLE (back-edge)
  has tool_calls?              │
       │ YES → [ToolNode] ────┘
       │ NO  → END
```

**Key difference from DAG:** The LLM decides at runtime how many times to call Vanna SQL.
No hardcoded validation nodes, no fixed retrieve→generate sequence.

## Setup

### 1. Install dependencies
```bash
cd ai-service
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env and set your OPENAI_API_KEY
```

### 3. Seed the database
```bash
python data/seed.py
```

### 4. Run the server
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
```

## API

### Stream chat
```
POST /v1/chat/stream
Content-Type: application/json

{
  "messages": [{"role": "user", "content": "Generate a monthly revenue report for 2023"}],
  "session_id": "optional-session-id"
}
```

### SSE Events
- `event: agent.message.delta` — streaming token chunk
- `event: agent.message.done` — generation complete
- `event: agent.workflow.failed` — error

## Example Queries

**GenReport** (triggers when asking for reports/analysis):
- "Generate a sales performance report for 2023"
- "Write a report on our top performing products"
- "Analyze revenue trends and give me insights"

**GenDashboard** (triggers when asking for charts/dashboards):
- "Create a sales dashboard with monthly revenue chart"
- "Show me a dashboard with order trends by region"
- "Build a product performance dashboard"

**General** (fallback):
- "What can you do?"
- "How does this system work?"

## Database Schema

```sql
products(id, name, category, price, stock)
customers(id, name, region, joined_date)
orders(id, product_id, customer_id, quantity, amount, status, order_date)
monthly_metrics(month, total_revenue, total_orders, avg_order_value, new_customers, top_category)
```

## LangGraph Patterns Used

| Pattern | Location | Why |
|---------|----------|-----|
| Cyclic graph (back-edge) | gen_report_agent.py, gen_dashboard_agent.py | `tools → agent` loop = true ReAct |
| `Command(goto=...)` | supervisor.py router_node | Dynamic routing without `add_conditional_edges` |
| `TypedDict` + `add_messages` | All states | Native LangGraph state with message reducer |
| `ToolNode` (prebuilt) | Both agent graphs | Automatic tool call dispatch |
| Compile once at module level | All graphs | No compilation overhead per request |
| Subgraph as node | supervisor.py | Agent graphs called as isolated subgraphs |

## Compare with md-ai-service-data

| Aspect | md-ai-service-data | This Project |
|--------|-------------------|--------------|
| Graph topology | DAG (all edges → END) | Cyclic (tools → agent back-edge) |
| Retry logic | None (hard fail) | Natural: agent re-queries if data empty |
| Data retrieval | Fixed `retrieve_data` node | LLM calls `query_data` N times as needed |
| Supervisor | Plain Python class | LangGraph StateGraph + `Command` handoffs |
| State schema | Pydantic BaseModel | TypedDict + `add_messages` reducer |
| Graph compilation | Inside `run()` per request | Once at module import |
| Control decisions | Hardcoded routing functions | LLM decides via tool_calls presence |
