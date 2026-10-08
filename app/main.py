"""Ashwheelz feedback server: public form, admin dashboard and JSON API."""
import hashlib
import hmac
import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from . import auth, repository
from .config import settings
from .db import pool, run_migrations
from .export import build_workbook
from .schemas import FeedbackFilters, FeedbackIn, LoginIn, PasswordChangeIn, StatusIn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ashwheelz")

STATIC = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    run_migrations()
    pool.open(wait=True)
    auth.ensure_default_admin()
    yield
    pool.close()


app = FastAPI(title="Ashwheelz Feedback", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


@app.middleware("http")
async def security(request: Request, call_next):
    # Admin writes must come from this site (defence in depth on top of SameSite=Strict).
    if request.url.path.startswith("/api/admin") and request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail": "Request blocked."}, status_code=403)
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if settings.cookie_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith("/api/admin") or request.url.path == "/admin":
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    msg = str(first.get("msg", "Some fields are not valid.")).removeprefix("Value error, ")
    field = ".".join(str(p) for p in first.get("loc", [])[1:])
    return JSONResponse({"detail": msg, "field": field}, status_code=422)


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# ------------------------------------------------------------ rate limiting
class RateLimit:
    def __init__(self, limit: int, window_seconds: int):
        self.limit, self.window = limit, window_seconds
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


submit_limit = RateLimit(limit=10, window_seconds=600)


# -------------------------------------------------------------------- pages
@app.get("/", include_in_schema=False)
def form_page():
    return FileResponse(STATIC / "form.html")


@app.get("/admin", include_in_schema=False)
def admin_page():
    return FileResponse(STATIC / "admin.html")


@app.get("/healthz", include_in_schema=False)
def health():
    with pool.connection() as conn:
        conn.execute("SELECT 1")
    return {"ok": True}


# --------------------------------------------------------------- public API
@app.get("/api/form")
def get_form():
    form = repository.get_form(settings.form_slug)
    if form is None:
        raise HTTPException(404, "This feedback form is not available.")
    form.pop("id")
    for s in form["sections"]:
        s.pop("id")
    return form


@app.post("/api/feedback", status_code=201)
def submit_feedback(payload: FeedbackIn, request: Request):
    ip = client_ip(request) or "unknown"
    if not submit_limit.allow(ip):
        raise HTTPException(429, "Too many submissions from this connection. Please try again in a few minutes.")
    if payload.website:  # honeypot filled: pretend success, store nothing
        return {"reference": "AW-000000-RECVD0"}
    ip_hash = hmac.new(settings.secret_key.encode(), ip.encode(), hashlib.sha256).hexdigest()
    try:
        ref = repository.create_feedback(
            payload, settings.form_slug, ip_hash, request.headers.get("user-agent")
        )
    except repository.FeedbackError as e:
        raise HTTPException(422, str(e))
    return {"reference": ref}


# ---------------------------------------------------------------- admin API
@app.post("/api/admin/login")
def login(body: LoginIn, request: Request, response: Response):
    ip = client_ip(request) or "unknown"
    wait = auth.login_throttle.retry_after(ip)
    if wait:
        raise HTTPException(429, f"Too many failed sign-ins. Try again in {max(1, wait // 60)} minutes.")
    admin = auth.authenticate(body.username, body.password)
    if admin is None:
        auth.login_throttle.fail(ip)
        log.warning("Failed admin sign-in for '%s' from %s", body.username[:50], ip)
        raise HTTPException(401, "Wrong username or password.")
    auth.login_throttle.reset(ip)
    token = auth.create_session(admin["id"], client_ip(request), request.headers.get("user-agent"))
    response.set_cookie(
        auth.SESSION_COOKIE, token, max_age=settings.session_hours * 3600, httponly=True,
        secure=settings.cookie_secure, samesite="strict", path="/",
    )
    return {"username": admin["username"]}


@app.post("/api/admin/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(auth.SESSION_COOKIE)
    if token:
        auth.delete_session(token)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return {"ok": True}


@app.get("/api/admin/me")
def me(admin=Depends(auth.current_admin)):
    return {"username": admin["username"], "default_password": _uses_default_password(admin)}


def _uses_default_password(admin) -> bool:
    if admin["username"] != settings.admin_username or settings.admin_password != "1234":
        return False
    with pool.connection() as conn:
        row = conn.execute("SELECT password_hash FROM admin_users WHERE id = %s", (admin["id"],)).fetchone()
    return auth.verify_password("1234", row["password_hash"].encode("ascii"))


@app.post("/api/admin/password")
def change_password(body: PasswordChangeIn, admin=Depends(auth.current_admin)):
    if not auth.change_password(admin["id"], body.current_password, body.new_password):
        raise HTTPException(400, "Your current password is not correct.")
    auth.delete_other_sessions(admin["id"], admin["token"])
    return {"ok": True}


@app.get("/api/admin/meta")
def meta(admin=Depends(auth.current_admin)):
    return {"services": repository.list_services(), "statuses": ["new", "reviewed", "actioned", "archived"]}


def filters_dep(
    q: str | None = Query(None), date_from: str | None = Query(None), date_to: str | None = Query(None),
    service_id: str | None = Query(None), rating_min: str | None = Query(None),
    rating_max: str | None = Query(None), status: str | None = Query(None),
) -> FeedbackFilters:
    try:
        return FeedbackFilters(q=q, date_from=date_from, date_to=date_to, service_id=service_id,
                               rating_min=rating_min, rating_max=rating_max, status=status)
    except ValidationError as e:
        err = e.errors()[0]
        raise HTTPException(422, f"Filter '{err['loc'][0]}' is not valid.")


@app.get("/api/admin/feedback")
def list_feedback(
    f: FeedbackFilters = Depends(filters_dep), page: int = Query(1, ge=1, le=100_000),
    page_size: int = Query(25, ge=5, le=100), sort: str = Query("newest"),
    admin=Depends(auth.current_admin),
):
    return repository.list_feedback(f, page, page_size, sort)


@app.get("/api/admin/stats")
def get_stats(f: FeedbackFilters = Depends(filters_dep), admin=Depends(auth.current_admin)):
    return repository.stats(f)


@app.get("/api/admin/feedback/{response_id}")
def get_feedback(response_id: UUID, admin=Depends(auth.current_admin)):
    item = repository.feedback_detail(str(response_id))
    if item is None:
        raise HTTPException(404, "This response no longer exists.")
    return item


@app.patch("/api/admin/feedback/{response_id}")
def set_status(response_id: UUID, body: StatusIn, admin=Depends(auth.current_admin)):
    if not repository.update_status(str(response_id), body.status):
        raise HTTPException(404, "This response no longer exists.")
    return {"ok": True}


@app.get("/api/admin/export.xlsx")
def export_xlsx(f: FeedbackFilters = Depends(filters_dep), admin=Depends(auth.current_admin)):
    form = repository.get_form(settings.form_slug)
    if form is None:
        raise HTTPException(404, "This feedback form is not available.")
    rows, answers = repository.export_rows(f)
    data = build_workbook(rows, answers, repository.all_questions(form["id"]),
                          repository.stats(f), _filters_label(f, form["services"]))
    stamp = datetime.now(ZoneInfo(settings.timezone)).strftime("%Y%m%d-%H%M")
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="ashwheelz-feedback-{stamp}.xlsx"'},
    )


def _filters_label(f: FeedbackFilters, services: list[dict]) -> str:
    parts = []
    if f.q:
        parts.append(f'search "{f.q}"')
    if f.date_from or f.date_to:
        parts.append(f"dates {f.date_from or '…'} to {f.date_to or '…'}")
    if f.service_id:
        name = next((s["name"] for s in services if s["id"] == f.service_id), f"#{f.service_id}")
        parts.append(f"service {name}")
    if f.rating_min or f.rating_max:
        parts.append(f"overall {f.rating_min or 1}–{f.rating_max or 5} stars")
    if f.status:
        parts.append(f"status {f.status}")
    return ", ".join(parts) or "All responses"
