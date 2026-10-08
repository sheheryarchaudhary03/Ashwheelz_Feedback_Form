"""Vercel entrypoint (see pyproject.toml).

Loads the real app. If it cannot even be imported, usually because an
environment variable is missing, every page explains what to fix instead of
the function crashing with a bare 500.
"""
import logging

try:
    from app.main import app
except Exception as exc:  # noqa: BLE001
    logging.exception("Ashwheelz app failed to load")
    from fastapi import FastAPI
    from fastapi.responses import PlainTextResponse

    # Our own configuration errors are safe to show; anything else stays in the logs.
    _reason = str(exc) if isinstance(exc, RuntimeError) else "The server could not start. Details are in the server logs."

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.api_route("/{path:path}", methods=["GET", "POST", "PATCH", "PUT", "DELETE", "HEAD"])
    def setup_problem(path: str):
        return PlainTextResponse(
            "Ashwheelz feedback is not set up yet.\n\n" + _reason, status_code=503,
            headers={"Cache-Control": "no-store"},
        )
