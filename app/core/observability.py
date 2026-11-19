
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from app.core import logger
from app.core.request_context import get_request_id


# Project directories
BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "llmops.db"
LOG_PATH = LOG_DIR / "observability.log"


# JSON structured logger
class JSONFormatter(logging.Formatter):

    def format(self, record):
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }

        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id

        if record.exc_info:
            log_data["exception"] = self.formatException(
                record.exc_info
            )

        return json.dumps(log_data)


logger = logging.getLogger("llmops.observability")
logger.setLevel(logging.INFO)
logger.propagate = False

if not logger.handlers:
    file_handler = logging.FileHandler(
        LOG_PATH,
        encoding="utf-8"
    )
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)





@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)

    try:
        yield conn
        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def initialize_observability_db():

    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT,
                timestamp TEXT NOT NULL,
                provider TEXT,
                model TEXT,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                latency_seconds REAL DEFAULT 0,
                status TEXT NOT NULL,
                error_type TEXT,
                question_length INTEGER DEFAULT 0,
                answer_length INTEGER DEFAULT 0
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_llm_requests_timestamp
            ON llm_requests(timestamp)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_llm_requests_request_id
            ON llm_requests(request_id)
        """)


def migrate_cost_columns():

    columns = {
        "input_cost": "REAL DEFAULT 0",
        "output_cost": "REAL DEFAULT 0",
        "total_cost": "REAL DEFAULT 0"
    }

    with get_connection() as conn:

        # Enable dictionary-style SQLite row access.
        conn.row_factory = sqlite3.Row

        existing = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(llm_requests)"
            ).fetchall()
        }

        for name, column_type in columns.items():

            if name not in existing:
                conn.execute(
                    f"ALTER TABLE llm_requests "
                    f"ADD COLUMN {name} {column_type}"
                )

    logger.info("Cost columns migration completed")




def record_llm_request(
    *,
    provider,
    model,
    status,
    input_tokens=0,
    output_tokens=0,
    total_tokens=0,
    latency_seconds=0,
    error_type=None,
    question_length=0,
    answer_length=0,
    input_cost=0,
output_cost=0,
total_cost=0
):

    request_id = get_request_id()

    try:
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO llm_requests (
                    request_id,
                    timestamp,
                    provider,
                    model,
                    input_tokens,
                    output_tokens,
                    total_tokens,
                    latency_seconds,
                    status,
                    error_type,
                    question_length,
                    answer_length,
                    input_cost,
                    output_cost,
                    total_cost
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                request_id,
                datetime.now(timezone.utc).isoformat(),
                provider,
                model,
                input_tokens,
                output_tokens,
                total_tokens,
                latency_seconds,
                status,
                error_type,
                question_length,
                answer_length,
                input_cost,
                output_cost,
                total_cost
            ))

        logger.info(
            "LLM request recorded",
            extra={"request_id": request_id}
        )

    except Exception:
        # Monitoring failure must not break LLM inference.
        logger.exception(
            "Failed to save LLM request",
            extra={"request_id": request_id}
        )



import math


def get_request_metrics():

    with get_connection() as conn:
        conn.row_factory = sqlite3.Row

        row = conn.execute("""
            SELECT
                COUNT(*) AS total_requests,

                SUM(CASE WHEN status = 'success'
                    THEN 1 ELSE 0 END) AS successful_requests,

                SUM(CASE WHEN status = 'failed'
                    THEN 1 ELSE 0 END) AS failed_requests,

                COALESCE(SUM(total_tokens), 0)
                    AS total_tokens,

                COALESCE(SUM(input_tokens), 0)
                    AS total_input_tokens,

                COALESCE(SUM(output_tokens), 0)
                    AS total_output_tokens,

                COALESCE(AVG(CASE
                    WHEN status = 'success'
                    THEN latency_seconds END), 0)
                    AS average_latency,

                COALESCE(MIN(CASE
                    WHEN status = 'success'
                    THEN latency_seconds END), 0)
                    AS minimum_latency,

                COALESCE(MAX(CASE
                    WHEN status = 'success'
                    THEN latency_seconds END), 0)
                    AS maximum_latency

            FROM llm_requests
        """).fetchone()

        # P95 latency: calculate from successful requests only.
        latency_rows = conn.execute("""
            SELECT latency_seconds
            FROM llm_requests
            WHERE status = 'success'
            ORDER BY latency_seconds ASC
        """).fetchall()

        # Model-level statistics.
        model_rows = conn.execute("""
            SELECT
                provider,
                model,
                COUNT(*) AS total_requests,
                SUM(CASE WHEN status = 'success'
                    THEN 1 ELSE 0 END) AS successful_requests,
                SUM(CASE WHEN status = 'failed'
                    THEN 1 ELSE 0 END) AS failed_requests,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COALESCE(AVG(CASE
                    WHEN status = 'success'
                    THEN latency_seconds END), 0)
                    AS average_latency
            FROM llm_requests
            GROUP BY provider, model
        """).fetchall()

    metrics = dict(row)

    total = metrics["total_requests"]
    successful = metrics["successful_requests"] or 0

    metrics["success_rate_percent"] = (
        round(successful / total * 100, 2)
        if total else 0
    )

    latencies = [r["latency_seconds"] for r in latency_rows]

    if latencies:
        p95_index = math.ceil(0.95 * len(latencies)) - 1
        metrics["p95_latency"] = round(
            latencies[p95_index], 4
        )
    else:
        metrics["p95_latency"] = 0

    metrics["average_latency"] = round(
        metrics["average_latency"], 4
    )

    metrics["minimum_latency"] = round(
        metrics["minimum_latency"], 4
    )

    metrics["maximum_latency"] = round(
        metrics["maximum_latency"], 4
    )

    metrics["models"] = [dict(r) for r in model_rows]

    return metrics



def get_recent_requests(limit=20):

    with get_connection() as conn:
        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
            SELECT *
            FROM llm_requests
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()

    return [dict(row) for row in rows]



def get_cost_metrics():

    with get_connection() as conn:
        conn.row_factory = sqlite3.Row

        row = conn.execute("""
            SELECT
                COALESCE(SUM(input_cost), 0)
                    AS total_input_cost,
                COALESCE(SUM(output_cost), 0)
                    AS total_output_cost,
                COALESCE(SUM(total_cost), 0)
                    AS total_cost,
                COUNT(*) AS total_requests,
                COALESCE(AVG(total_cost), 0)
                    AS average_cost_per_request
            FROM llm_requests
            WHERE status = 'success'
        """).fetchone()

    return dict(row)



def get_request_trends(days=7):

    days = max(1, min(int(days), 90))

    with get_connection() as conn:
        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
            SELECT
                substr(timestamp, 1, 10) AS date,

                COUNT(*) AS total_requests,

                SUM(CASE WHEN status = 'success'
                    THEN 1 ELSE 0 END) AS successful_requests,

                SUM(CASE WHEN status = 'failed'
                    THEN 1 ELSE 0 END) AS failed_requests,

                COALESCE(SUM(total_tokens), 0)
                    AS total_tokens,

                COALESCE(SUM(total_cost), 0)
                    AS total_cost,

                COALESCE(AVG(CASE
                    WHEN status = 'success'
                    THEN latency_seconds END), 0)
                    AS average_latency

            FROM llm_requests

            WHERE timestamp >= datetime('now', ?)

            GROUP BY substr(timestamp, 1, 10)

            ORDER BY date ASC
        """, (f"-{days} days",)).fetchall()

    return [dict(row) for row in rows]
