"""Database-backed rate limits, shared by every app instance."""
import hashlib
import hmac
import random

from .config import settings
from .db import pool

LOGIN_FAIL = "login_fail"
SUBMIT = "submit"


def key_for(ip: str) -> str:
    return hmac.new(settings.secret_key.encode(), ip.encode(), hashlib.sha256).hexdigest()


def retry_after(bucket: str, ip: str, limit: int, window_seconds: int) -> int:
    """Seconds until this IP may try again, or 0 if it is under the limit."""
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT count(*) AS n, min(created_at) AS oldest FROM rate_limit_hits "
            "WHERE bucket = %s AND key_hash = %s AND created_at > now() - make_interval(secs => %s)",
            (bucket, key_for(ip), window_seconds),
        ).fetchone()
        if row["n"] < limit:
            return 0
        wait = conn.execute(
            "SELECT ceil(extract(epoch FROM %s + make_interval(secs => %s) - now()))::int AS s",
            (row["oldest"], window_seconds),
        ).fetchone()["s"]
    return max(1, wait)


def record(bucket: str, ip: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO rate_limit_hits (bucket, key_hash) VALUES (%s, %s)", (bucket, key_for(ip))
        )
        if random.random() < 0.02:  # occasional housekeeping
            conn.execute("DELETE FROM rate_limit_hits WHERE created_at < now() - interval '1 day'")


def clear(bucket: str, ip: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            "DELETE FROM rate_limit_hits WHERE bucket = %s AND key_hash = %s", (bucket, key_for(ip))
        )


def allow(bucket: str, ip: str, limit: int, window_seconds: int) -> bool:
    """Record an attempt and say whether it is within the limit."""
    if retry_after(bucket, ip, limit, window_seconds):
        return False
    record(bucket, ip)
    return True
