"""Vanna singleton — initialised once, reused across requests."""
from functools import lru_cache
from pathlib import Path

from loguru import logger
from vanna.chromadb import ChromaDB_VectorStore
from vanna.openai import OpenAI_Chat

from src.core.config import settings

SCHEMA_DDL = """
CREATE TABLE products (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL,
    category TEXT NOT NULL,
    price    REAL NOT NULL,
    stock    INTEGER NOT NULL
);

CREATE TABLE customers (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    region      TEXT NOT NULL,
    joined_date TEXT NOT NULL
);

CREATE TABLE orders (
    id          INTEGER PRIMARY KEY,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    quantity    INTEGER NOT NULL,
    amount      REAL NOT NULL,
    status      TEXT NOT NULL,   -- completed | pending | cancelled | refunded
    order_date  TEXT NOT NULL    -- ISO date string YYYY-MM-DD
);

CREATE TABLE monthly_metrics (
    month            TEXT PRIMARY KEY,  -- YYYY-MM
    total_revenue    REAL NOT NULL,
    total_orders     INTEGER NOT NULL,
    avg_order_value  REAL NOT NULL,
    new_customers    INTEGER NOT NULL,
    top_category     TEXT NOT NULL
);
"""

SAMPLE_QA = [
    ("What is the total revenue for each month?",
     "SELECT month, total_revenue FROM monthly_metrics ORDER BY month"),
    ("Show me total orders and revenue by product category",
     "SELECT p.category, COUNT(o.id) AS total_orders, SUM(o.amount) AS total_revenue "
     "FROM orders o JOIN products p ON o.product_id = p.id WHERE o.status = 'completed' "
     "GROUP BY p.category ORDER BY total_revenue DESC"),
    ("Which products have the highest sales?",
     "SELECT p.name, SUM(o.quantity) AS units_sold, SUM(o.amount) AS revenue "
     "FROM orders o JOIN products p ON o.product_id = p.id WHERE o.status = 'completed' "
     "GROUP BY p.id ORDER BY revenue DESC LIMIT 10"),
    ("What is the revenue trend over time?",
     "SELECT month, total_revenue, total_orders FROM monthly_metrics ORDER BY month"),
    ("Show orders by region",
     "SELECT c.region, COUNT(o.id) AS total_orders, SUM(o.amount) AS total_amount "
     "FROM orders o JOIN customers c ON o.customer_id = c.id "
     "GROUP BY c.region ORDER BY total_amount DESC"),
    ("What is the average order value by month?",
     "SELECT month, avg_order_value FROM monthly_metrics ORDER BY month"),
    ("How many new customers joined each month?",
     "SELECT month, new_customers FROM monthly_metrics ORDER BY month"),
]


class MyVanna(ChromaDB_VectorStore, OpenAI_Chat):
    def __init__(self, config=None):
        ChromaDB_VectorStore.__init__(self, config={"path": config.get("path", "./data/chroma")})
        OpenAI_Chat.__init__(self, config={
            "api_key": config.get("api_key"),
            "model": config.get("model", "gpt-4o-mini"),
        })


@lru_cache(maxsize=1)
def get_vanna() -> MyVanna:
    """Return trained Vanna singleton (cached after first call)."""
    chroma_path = settings.chroma_abs_path
    Path(chroma_path).mkdir(parents=True, exist_ok=True)

    vn = MyVanna(config={
        "api_key": settings.OPENAI_API_KEY,
        "model": settings.VANNA_MODEL,
        "path": chroma_path,
    })

    db_path = settings.db_abs_path
    if not Path(db_path).exists():
        raise FileNotFoundError(
            f"Database not found at {db_path}. Run: python data/seed.py"
        )
    vn.connect_to_sqlite(db_path)

    # Train on DDL + sample Q&A (idempotent — Chroma skips duplicates)
    existing = vn.get_training_data()
    if existing is None or len(existing) == 0:
        logger.info("Training Vanna on schema DDL and sample Q&A pairs...")
        vn.train(ddl=SCHEMA_DDL)
        for question, sql in SAMPLE_QA:
            vn.train(question=question, sql=sql)
        logger.info("Vanna training complete.")
    else:
        logger.info(f"Vanna already trained ({len(existing)} examples). Skipping.")

    return vn
