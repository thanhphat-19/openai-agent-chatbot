"""Seed script — run once to create sample.db with realistic data."""
import sqlite3
import random
from pathlib import Path
from datetime import date, timedelta

DB_PATH = Path(__file__).parent / "sample.db"


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS products (
        id          INTEGER PRIMARY KEY,
        name        TEXT NOT NULL,
        category    TEXT NOT NULL,
        price       REAL NOT NULL,
        stock       INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS customers (
        id          INTEGER PRIMARY KEY,
        name        TEXT NOT NULL,
        region      TEXT NOT NULL,
        joined_date TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS orders (
        id          INTEGER PRIMARY KEY,
        product_id  INTEGER NOT NULL REFERENCES products(id),
        customer_id INTEGER NOT NULL REFERENCES customers(id),
        quantity    INTEGER NOT NULL,
        amount      REAL NOT NULL,
        status      TEXT NOT NULL,
        order_date  TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS monthly_metrics (
        month            TEXT PRIMARY KEY,
        total_revenue    REAL NOT NULL,
        total_orders     INTEGER NOT NULL,
        avg_order_value  REAL NOT NULL,
        new_customers    INTEGER NOT NULL,
        top_category     TEXT NOT NULL
    );
    """)


def seed_data(conn: sqlite3.Connection) -> None:
    categories = ["Electronics", "Agriculture", "Food & Beverage", "Machinery", "Chemicals"]
    regions = ["North", "South", "East", "West", "Central"]
    statuses = ["completed", "pending", "cancelled", "refunded"]

    products = [
        (1, "Smart Irrigation Controller", "Agriculture", 450.0, 120),
        (2, "Soil Moisture Sensor", "Agriculture", 89.99, 500),
        (3, "Greenhouse LED Light", "Agriculture", 220.0, 80),
        (4, "Water Pump 5HP", "Machinery", 380.0, 60),
        (5, "Pesticide Sprayer", "Agriculture", 175.0, 200),
        (6, "Fertilizer Mixer", "Machinery", 620.0, 30),
        (7, "Temperature Logger", "Electronics", 65.0, 350),
        (8, "pH Meter", "Electronics", 120.0, 180),
        (9, "Rice Seed 50kg", "Agriculture", 45.0, 1000),
        (10, "Organic Compost 20kg", "Food & Beverage", 25.0, 800),
    ]
    conn.executemany("INSERT OR IGNORE INTO products VALUES (?,?,?,?,?)", products)

    customers = []
    base_date = date(2023, 1, 1)
    for i in range(1, 101):
        name = f"Customer_{i:03d}"
        region = random.choice(regions)
        joined = (base_date + timedelta(days=random.randint(0, 365))).isoformat()
        customers.append((i, name, region, joined))
    conn.executemany("INSERT OR IGNORE INTO customers VALUES (?,?,?,?)", customers)

    orders = []
    order_date = date(2023, 1, 5)
    for oid in range(1, 501):
        pid = random.randint(1, 10)
        cid = random.randint(1, 100)
        qty = random.randint(1, 20)
        price = products[pid - 1][3]
        amount = round(qty * price, 2)
        status = random.choices(statuses, weights=[70, 15, 10, 5])[0]
        odate = (order_date + timedelta(days=random.randint(0, 360))).isoformat()
        orders.append((oid, pid, cid, qty, amount, status, odate))
    conn.executemany("INSERT OR IGNORE INTO orders VALUES (?,?,?,?,?,?,?)", orders)

    months = [
        ("2023-01", 85400.0,  42, 2033.3, 12, "Agriculture"),
        ("2023-02", 92100.0,  48, 1918.8, 15, "Agriculture"),
        ("2023-03", 110500.0, 55, 2009.1, 18, "Machinery"),
        ("2023-04", 98200.0,  50, 1964.0, 10, "Agriculture"),
        ("2023-05", 125300.0, 61, 2054.1, 22, "Electronics"),
        ("2023-06", 138700.0, 68, 2039.7, 25, "Agriculture"),
        ("2023-07", 142000.0, 72, 1972.2, 20, "Agriculture"),
        ("2023-08", 155600.0, 78, 1995.0, 28, "Machinery"),
        ("2023-09", 133400.0, 65, 2052.3, 17, "Agriculture"),
        ("2023-10", 148900.0, 74, 2012.2, 24, "Electronics"),
        ("2023-11", 162300.0, 80, 2028.8, 30, "Agriculture"),
        ("2023-12", 189500.0, 93, 2037.6, 35, "Agriculture"),
    ]
    conn.executemany("INSERT OR IGNORE INTO monthly_metrics VALUES (?,?,?,?,?,?)", months)
    conn.commit()


def main() -> None:
    if DB_PATH.exists():
        print(f"DB already exists at {DB_PATH}. Delete it to re-seed.")
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    create_schema(conn)
    seed_data(conn)
    conn.close()
    print(f"Sample database created at {DB_PATH}")
    print("Tables: products, customers, orders, monthly_metrics")


if __name__ == "__main__":
    main()
