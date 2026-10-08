"""All SQL for forms and feedback. Every query is parameterised."""
import re
import secrets
from datetime import datetime, timezone

import psycopg

from .config import settings
from .db import pool
from .schemas import FeedbackFilters, FeedbackIn

OVERALL_CODE = "overall"
NPS_CODE = "nps"
_REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class FeedbackError(ValueError):
    """Submission failed a check against the stored questions."""


# ------------------------------------------------------------------- form
def get_form(slug: str) -> dict | None:
    with pool.connection() as conn:
        form = conn.execute(
            "SELECT id, slug, title FROM forms WHERE slug = %s AND is_active", (slug,)
        ).fetchone()
        if form is None:
            return None
        rows = conn.execute(
            "SELECT s.id AS section_id, s.title AS section_title, q.code, q.question_type, "
            "       q.prompt, q.hint, q.options, q.detail_options, q.is_required "
            "FROM form_sections s JOIN questions q ON q.section_id = s.id "
            "WHERE s.form_id = %s AND q.is_active "
            "ORDER BY s.sort_order, s.id, q.sort_order, q.id",
            (form["id"],),
        ).fetchall()
        services = conn.execute(
            "SELECT id, name FROM service_types WHERE is_active ORDER BY sort_order, name"
        ).fetchall()

    sections: list[dict] = []
    for r in rows:
        if not sections or sections[-1]["id"] != r["section_id"]:
            sections.append({"id": r["section_id"], "title": r["section_title"], "questions": []})
        sections[-1]["questions"].append({
            "code": r["code"],
            "type": r["question_type"],
            "prompt": r["prompt"],
            "hint": r["hint"],
            "options": r["options"],
            "detail_options": r["detail_options"],
            "required": r["is_required"],
        })
    return {"id": form["id"], "slug": form["slug"], "title": form["title"],
            "sections": sections, "services": services}


def all_questions(form_id: int) -> list[dict]:
    """Every question ever on the form (active or not), in display order."""
    with pool.connection() as conn:
        return conn.execute(
            "SELECT q.id, q.code, q.question_type, q.prompt, q.detail_options, s.title AS section "
            "FROM questions q JOIN form_sections s ON s.id = q.section_id "
            "WHERE q.form_id = %s ORDER BY s.sort_order, s.id, q.sort_order, q.id",
            (form_id,),
        ).fetchall()


def list_services() -> list[dict]:
    with pool.connection() as conn:
        return conn.execute("SELECT id, name FROM service_types ORDER BY sort_order, name").fetchall()


# ------------------------------------------------------------- submission
def _validate_answers(payload: FeedbackIn, questions: dict[str, dict]) -> list[dict]:
    seen: set[str] = set()
    cleaned: list[dict] = []
    for a in payload.answers:
        q = questions.get(a.question_code)
        if q is None:
            raise FeedbackError(f"Unknown question '{a.question_code}'.")
        if a.question_code in seen:
            raise FeedbackError(f"Question '{a.question_code}' was answered twice.")
        seen.add(a.question_code)

        rating = choice = detail = None
        v = a.value
        if v is not None:
            if q["question_type"] in ("stars", "nps"):
                hi = 5 if q["question_type"] == "stars" else 10
                lo = 1 if q["question_type"] == "stars" else 0
                if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
                    raise FeedbackError(f"'{q['prompt']}' needs a score from {lo} to {hi}.")
                rating = v
            else:
                if not isinstance(v, str) or v not in q["options"]:
                    raise FeedbackError(f"Pick one of the listed options for '{q['prompt']}'.")
                choice = v
        if a.detail is not None:
            if a.detail not in q["detail_options"]:
                raise FeedbackError(f"Pick one of the listed options for '{q['prompt']}'.")
            detail = a.detail
        if rating is None and choice is None and detail is None and a.suggestion is None:
            continue
        cleaned.append({"question_id": q["id"], "code": q["code"], "rating": rating,
                        "choice": choice, "detail": detail, "suggestion": a.suggestion})

    answered = {c["code"] for c in cleaned if c["rating"] is not None or c["choice"] is not None}
    for code, q in questions.items():
        if q["is_required"] and code not in answered:
            raise FeedbackError(f"Please answer: {q['prompt']}")
    return cleaned


def _match_customer(conn, name: str, email: str | None, phone_digits: str | None) -> int:
    row = None
    if email:
        row = conn.execute(
            "SELECT id FROM customers WHERE lower(email) = lower(%s)", (email,)
        ).fetchone()
    if row is None and phone_digits and not email:
        row = conn.execute(
            "SELECT id FROM customers WHERE phone_digits = %s AND email IS NULL ORDER BY id LIMIT 1",
            (phone_digits,),
        ).fetchone()
    if row is not None:
        conn.execute("UPDATE customers SET last_seen_at = now() WHERE id = %s", (row["id"],))
        return row["id"]
    return conn.execute(
        "INSERT INTO customers (name, email, phone_digits) VALUES (%s, %s, %s) "
        "ON CONFLICT (lower(email)) WHERE email IS NOT NULL "
        "DO UPDATE SET last_seen_at = now() RETURNING id",
        (name, email, phone_digits),
    ).fetchone()["id"]


def _new_reference() -> str:
    day = datetime.now(timezone.utc).strftime("%y%m%d")
    return f"AW-{day}-" + "".join(secrets.choice(_REF_ALPHABET) for _ in range(6))


def create_feedback(payload: FeedbackIn, form_slug: str, ip_hash: str | None, user_agent: str | None) -> str:
    with pool.connection() as conn:
        form = conn.execute(
            "SELECT id FROM forms WHERE slug = %s AND is_active", (form_slug,)
        ).fetchone()
        if form is None:
            raise FeedbackError("This feedback form is not available.")
        questions = {
            r["code"]: r for r in conn.execute(
                "SELECT id, code, question_type, prompt, options, detail_options, is_required "
                "FROM questions WHERE form_id = %s AND is_active",
                (form["id"],),
            ).fetchall()
        }
        answers = _validate_answers(payload, questions)

        if payload.service_type_id is not None:
            ok = conn.execute(
                "SELECT 1 FROM service_types WHERE id = %s AND is_active", (payload.service_type_id,)
            ).fetchone()
            if not ok:
                raise FeedbackError("Pick a service from the list.")

        c = payload.customer
        phone_digits = re.sub(r"\D", "", c.phone or "") or None
        overall = next((a["rating"] for a in answers if a["code"] == OVERALL_CODE), None)
        nps = next((a["rating"] for a in answers if a["code"] == NPS_CODE), None)

        with conn.transaction():
            customer_id = _match_customer(conn, c.name, c.email, phone_digits)
            for attempt in range(5):
                ref = _new_reference()
                try:
                    with conn.transaction():
                        response_id = conn.execute(
                            "INSERT INTO feedback_responses (reference_code, form_id, customer_id, "
                            " service_type_id, customer_name, customer_company, customer_phone, "
                            " customer_email, overall_rating, nps_score, other_suggestions, "
                            " ip_hash, user_agent) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                            (ref, form["id"], customer_id, payload.service_type_id, c.name,
                             c.company, c.phone, c.email, overall, nps, payload.other_suggestions,
                             ip_hash, (user_agent or "")[:500] or None),
                        ).fetchone()["id"]
                    break
                except psycopg.errors.UniqueViolation:
                    if attempt == 4:
                        raise
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO feedback_answers (response_id, question_id, rating, choice_value, "
                    " detail_value, suggestion) VALUES (%s,%s,%s,%s,%s,%s)",
                    [(response_id, a["question_id"], a["rating"], a["choice"], a["detail"],
                      a["suggestion"]) for a in answers],
                )
    return ref


# --------------------------------------------------------------- dashboard
def _where(f: FeedbackFilters) -> tuple[str, list]:
    clauses, args = ["TRUE"], []
    if f.q:
        like = "%" + f.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        clauses.append(
            "(r.customer_name ILIKE %s OR r.customer_company ILIKE %s OR r.customer_email ILIKE %s"
            " OR r.customer_phone ILIKE %s OR r.reference_code ILIKE %s OR r.other_suggestions ILIKE %s"
            " OR EXISTS (SELECT 1 FROM feedback_answers a WHERE a.response_id = r.id"
            "            AND a.suggestion ILIKE %s))"
        )
        args += [like] * 7
    if f.date_from:
        clauses.append("r.submitted_at >= (%s::date)::timestamp AT TIME ZONE %s")
        args += [f.date_from, settings.timezone]
    if f.date_to:
        clauses.append("r.submitted_at < (%s::date + 1)::timestamp AT TIME ZONE %s")
        args += [f.date_to, settings.timezone]
    if f.service_id:
        clauses.append("r.service_type_id = %s")
        args.append(f.service_id)
    if f.rating_min:
        clauses.append("r.overall_rating >= %s")
        args.append(f.rating_min)
    if f.rating_max:
        clauses.append("r.overall_rating <= %s")
        args.append(f.rating_max)
    if f.status:
        clauses.append("r.status = %s")
        args.append(f.status)
    return " AND ".join(clauses), args


SORTS = {
    "newest": "r.submitted_at DESC",
    "oldest": "r.submitted_at ASC",
    "rating_low": "r.overall_rating ASC NULLS LAST, r.submitted_at DESC",
    "rating_high": "r.overall_rating DESC NULLS LAST, r.submitted_at DESC",
}

_LIST_COLUMNS = (
    "r.id, r.reference_code, r.submitted_at, r.status, r.customer_name, r.customer_company, "
    "r.customer_phone, r.customer_email, r.overall_rating, r.nps_score, r.other_suggestions, "
    "r.form_id, s.name AS service"
)


def list_feedback(f: FeedbackFilters, page: int, page_size: int, sort: str) -> dict:
    where, args = _where(f)
    order = SORTS.get(sort, SORTS["newest"])
    with pool.connection() as conn:
        total = conn.execute(
            f"SELECT count(*) AS n FROM feedback_responses r WHERE {where}", args
        ).fetchone()["n"]
        rows = conn.execute(
            f"SELECT {_LIST_COLUMNS}, "
            "  (SELECT count(*) FROM feedback_answers a WHERE a.response_id = r.id"
            "     AND a.suggestion IS NOT NULL) "
            "  + (r.other_suggestions IS NOT NULL)::int AS comment_count "
            "FROM feedback_responses r LEFT JOIN service_types s ON s.id = r.service_type_id "
            f"WHERE {where} ORDER BY {order} LIMIT %s OFFSET %s",
            args + [page_size, (page - 1) * page_size],
        ).fetchall()
    return {"total": total, "page": page, "page_size": page_size, "items": rows}


def feedback_detail(response_id: str) -> dict | None:
    with pool.connection() as conn:
        r = conn.execute(
            f"SELECT {_LIST_COLUMNS}, r.source FROM feedback_responses r "
            "LEFT JOIN service_types s ON s.id = r.service_type_id WHERE r.id = %s",
            (response_id,),
        ).fetchone()
        if r is None:
            return None
        r["answers"] = conn.execute(
            "SELECT sec.title AS section, q.code, q.question_type AS type, q.prompt, "
            "       a.rating, a.choice_value, a.detail_value, a.suggestion "
            "FROM questions q JOIN form_sections sec ON sec.id = q.section_id "
            "LEFT JOIN feedback_answers a ON a.question_id = q.id AND a.response_id = %s "
            "WHERE q.form_id = %s AND (q.is_active OR a.id IS NOT NULL) "
            "ORDER BY sec.sort_order, sec.id, q.sort_order, q.id",
            (response_id, r["form_id"]),
        ).fetchall()
    return r


def update_status(response_id: str, status: str) -> bool:
    with pool.connection() as conn:
        cur = conn.execute(
            "UPDATE feedback_responses SET status = %s WHERE id = %s", (status, response_id)
        )
        return cur.rowcount == 1


def stats(f: FeedbackFilters) -> dict:
    where, args = _where(f)
    with pool.connection() as conn:
        s = conn.execute(
            "SELECT count(*) AS total, "
            "  round(avg(r.overall_rating)::numeric, 2) AS avg_overall, "
            "  count(r.nps_score) AS nps_count, "
            "  count(*) FILTER (WHERE r.nps_score >= 9) AS promoters, "
            "  count(*) FILTER (WHERE r.nps_score <= 6) AS detractors, "
            "  count(*) FILTER (WHERE r.overall_rating <= 2) AS low_rated, "
            "  count(*) FILTER (WHERE r.status = 'new') AS unreviewed "
            f"FROM feedback_responses r WHERE {where}",
            args,
        ).fetchone()
        by_question = conn.execute(
            "SELECT q.code, q.prompt, sec.title AS section, "
            "  round(avg(a.rating)::numeric, 2) AS avg, count(a.rating) AS n "
            "FROM questions q JOIN form_sections sec ON sec.id = q.section_id "
            "LEFT JOIN feedback_answers a ON a.question_id = q.id AND a.response_id IN "
            f"  (SELECT r.id FROM feedback_responses r WHERE {where}) "
            "WHERE q.question_type = 'stars' AND q.is_active "
            "GROUP BY q.id, q.code, q.prompt, sec.title, sec.sort_order, q.sort_order "
            "ORDER BY sec.sort_order, q.sort_order",
            args,
        ).fetchall()
    nps = None
    if s["nps_count"]:
        nps = round(100 * (s["promoters"] - s["detractors"]) / s["nps_count"])
    return {
        "total": s["total"],
        "avg_overall": float(s["avg_overall"]) if s["avg_overall"] is not None else None,
        "nps": nps,
        "nps_count": s["nps_count"],
        "low_rated": s["low_rated"],
        "unreviewed": s["unreviewed"],
        "by_question": [
            {**q, "avg": float(q["avg"]) if q["avg"] is not None else None} for q in by_question
        ],
    }


def export_rows(f: FeedbackFilters, limit: int = 100_000) -> tuple[list[dict], dict[str, dict]]:
    """Responses matching the filters plus their answers keyed by response id."""
    where, args = _where(f)
    with pool.connection() as conn:
        rows = conn.execute(
            f"SELECT {_LIST_COLUMNS} FROM feedback_responses r "
            "LEFT JOIN service_types s ON s.id = r.service_type_id "
            f"WHERE {where} ORDER BY r.submitted_at DESC LIMIT %s",
            args + [limit],
        ).fetchall()
        answers: dict[str, dict] = {}
        if rows:
            for a in conn.execute(
                "SELECT a.response_id, q.code, a.rating, a.choice_value, a.detail_value, a.suggestion "
                "FROM feedback_answers a JOIN questions q ON q.id = a.question_id "
                "WHERE a.response_id = ANY(%s)",
                ([r["id"] for r in rows],),
            ):
                answers.setdefault(str(a["response_id"]), {})[a["code"]] = a
    return rows, answers
