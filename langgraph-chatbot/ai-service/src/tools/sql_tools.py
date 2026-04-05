"""LangChain tools wrapping Vanna SQL — bound to ReAct agent loops."""
import json

from langchain_core.tools import tool
from loguru import logger

from src.tools.vanna_setup import get_vanna


@tool
def query_data(question: str) -> str:
    """Query the database using natural language.

    Use this tool whenever you need data to answer the user.
    The question should be a clear natural language description of what data you need.
    Returns a JSON array of rows, or an error message.

    Examples:
      query_data("total revenue by month for 2023")
      query_data("top 5 products by sales quantity")
      query_data("orders grouped by region and status")
    """
    try:
        vn = get_vanna()
        sql = vn.generate_sql(question)
        logger.info(f"Vanna generated SQL: {sql}")
        df = vn.run_sql(sql)
        if df is None or df.empty:
            return json.dumps({"rows": [], "sql": sql, "message": "No data found."})
        rows = df.to_dict(orient="records")
        return json.dumps({"rows": rows, "sql": sql, "row_count": len(rows)}, default=str)
    except Exception as e:
        logger.error(f"query_data failed: {e}")
        return json.dumps({"error": str(e), "rows": []})


@tool
def list_tables() -> str:
    """List all available database tables with their columns and types.

    Call this first if you are unsure what tables or columns exist.
    Returns a text description of the schema.
    """
    try:
        import sqlite3
        from src.core.config import settings
        conn = sqlite3.connect(settings.db_abs_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        schema_parts = []
        for table in tables:
            cursor.execute(f"PRAGMA table_info({table})")
            cols = cursor.fetchall()
            col_defs = ", ".join(f"{c[1]} {c[2]}" for c in cols)
            schema_parts.append(f"{table}({col_defs})")
        conn.close()
        return "\n".join(schema_parts)
    except Exception as e:
        return f"Error reading schema: {e}"
