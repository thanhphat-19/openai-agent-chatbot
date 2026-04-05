"""Build-time script: seed the DB then train Vanna (local ONNX embeddings only).

Designed to run during `docker build` — NO OpenAI calls are made here.
vn.train() only writes embeddings to ChromaDB using the local all-MiniLM-L6-v2
ONNX model, which is downloaded automatically on first use and then cached.

Usage (Docker build step):
    python data/train.py
"""
import os
import sqlite3
import sys
from pathlib import Path

# ── Resolve paths relative to ai-service root ──────────────────────────────
ROOT = Path(__file__).parent.parent          # ai-service/
DATA = ROOT / "data"
DB_PATH = DATA / "sample.db"
CHROMA_PATH = DATA / "chroma"

# ── 1. Seed the database ────────────────────────────────────────────────────
print("==> Seeding SQLite database...")

conn = sqlite3.connect(str(DB_PATH))
cur = conn.cursor()

cur.executescript("""
DROP TABLE IF EXISTS monthly_metrics;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS products;

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
    status      TEXT NOT NULL,
    order_date  TEXT NOT NULL
);

CREATE TABLE monthly_metrics (
    month            TEXT PRIMARY KEY,
    total_revenue    REAL NOT NULL,
    total_orders     INTEGER NOT NULL,
    avg_order_value  REAL NOT NULL,
    new_customers    INTEGER NOT NULL,
    top_category     TEXT NOT NULL
);
""")

import random, datetime

random.seed(42)

CATEGORIES = ["Electronics", "Clothing", "Home & Kitchen", "Books", "Sports"]
REGIONS    = ["North", "South", "East", "West", "Central"]
STATUSES   = ["completed", "pending", "cancelled", "refunded"]

products = [
    (1, "Laptop Pro 15", "Electronics", 1299.99, 50),
    (2, "Wireless Headphones", "Electronics", 199.99, 200),
    (3, "Running Shoes", "Sports", 89.99, 300),
    (4, "Python Cookbook", "Books", 49.99, 500),
    (5, "Smart Watch", "Electronics", 299.99, 150),
    (6, "Yoga Mat", "Sports", 29.99, 400),
    (7, "Coffee Maker", "Home & Kitchen", 79.99, 120),
    (8, "Winter Jacket", "Clothing", 149.99, 80),
    (9, "Desk Lamp", "Home & Kitchen", 39.99, 250),
    (10, "Bluetooth Speaker", "Electronics", 129.99, 180),
]
cur.executemany("INSERT INTO products VALUES (?,?,?,?,?)", products)

customers = []
for i in range(1, 101):
    year  = random.randint(2020, 2023)
    month = random.randint(1, 12)
    day   = random.randint(1, 28)
    customers.append((i, f"Customer {i}", random.choice(REGIONS),
                      f"{year}-{month:02d}-{day:02d}"))
cur.executemany("INSERT INTO customers VALUES (?,?,?,?)", customers)

orders = []
base = datetime.date(2023, 1, 1)
for i in range(1, 501):
    p   = random.choice(products)
    cid = random.randint(1, 100)
    qty = random.randint(1, 5)
    dt  = base + datetime.timedelta(days=random.randint(0, 364))
    orders.append((i, p[0], cid, qty, round(p[3] * qty, 2),
                   random.choice(STATUSES), str(dt)))
cur.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?)", orders)

metrics = [
    ("2023-01", 45230.50, 38, 1190.28, 12, "Electronics"),
    ("2023-02", 52100.75, 44, 1184.11, 15, "Electronics"),
    ("2023-03", 48750.20, 41, 1189.03, 11, "Sports"),
    ("2023-04", 61200.00, 52, 1176.92, 18, "Electronics"),
    ("2023-05", 55680.30, 47, 1184.69, 14, "Home & Kitchen"),
    ("2023-06", 49320.80, 42, 1174.31, 13, "Clothing"),
    ("2023-07", 58900.15, 50, 1178.00, 16, "Electronics"),
    ("2023-08", 63450.90, 54, 1175.02, 20, "Electronics"),
    ("2023-09", 51230.40, 43, 1191.40, 12, "Sports"),
    ("2023-10", 67800.60, 57, 1189.49, 22, "Electronics"),
    ("2023-11", 72100.25, 61, 1182.00, 25, "Electronics"),
    ("2023-12", 89500.00, 75, 1193.33, 30, "Electronics"),
]
cur.executemany("INSERT INTO monthly_metrics VALUES (?,?,?,?,?,?)", metrics)

conn.commit()
conn.close()
print(f"    DB seeded at {DB_PATH}")

# ── 2. Train Vanna (local ONNX embeddings — no OpenAI calls) ────────────────
print("==> Training Vanna (downloads ONNX model + builds ChromaDB)...")

# Provide a dummy key so the class can instantiate — train() never calls OpenAI
os.environ.setdefault("OPENAI_API_KEY", "sk-build-placeholder")

CHROMA_PATH.mkdir(parents=True, exist_ok=True)

from vanna.chromadb import ChromaDB_VectorStore
from vanna.openai import OpenAI_Chat

class MyVanna(ChromaDB_VectorStore, OpenAI_Chat):
    def __init__(self, config=None):
        ChromaDB_VectorStore.__init__(self, config={"path": config.get("path", "./data/chroma")})
        OpenAI_Chat.__init__(self, config={
            "api_key": config.get("api_key"),
            "model": config.get("model", "gpt-4o-mini"),
        })

vn = MyVanna(config={
    "api_key": os.environ["OPENAI_API_KEY"],
    "model": os.environ.get("VANNA_MODEL", "gpt-4o-mini"),
    "path": str(CHROMA_PATH),
})

SCHEMA_DDL = """
CREATE TABLE products (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
    price REAL NOT NULL, stock INTEGER NOT NULL
);
CREATE TABLE customers (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, region TEXT NOT NULL,
    joined_date TEXT NOT NULL
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    quantity INTEGER NOT NULL, amount REAL NOT NULL,
    status TEXT NOT NULL, order_date TEXT NOT NULL
);
CREATE TABLE monthly_metrics (
    month TEXT PRIMARY KEY, total_revenue REAL NOT NULL,
    total_orders INTEGER NOT NULL, avg_order_value REAL NOT NULL,
    new_customers INTEGER NOT NULL, top_category TEXT NOT NULL
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

vn.train(ddl=SCHEMA_DDL)
for question, sql in SAMPLE_QA:
    vn.train(question=question, sql=sql)

print(f"    ChromaDB written to {CHROMA_PATH}")
print("==> Build-time training complete.")
