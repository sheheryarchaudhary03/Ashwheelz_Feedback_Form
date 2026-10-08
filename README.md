# Ashwheelz Customer Feedback

Customers open one link and rate their delivery: time, safety, driver, hygiene and
service, with a suggestion box under every question. Every response is stored in
PostgreSQL. A password-protected admin dashboard lets you view, search and filter
responses, mark them as reviewed or actioned, and export them to Excel with one click.

| Page | URL |
|---|---|
| Customer form (share this) | `https://your-domain/` |
| Admin dashboard | `https://your-domain/admin` |

## Admin sign-in

On first start the app creates one admin account from `ADMIN_USERNAME` /
`ADMIN_PASSWORD` (default **admin / 1234**). The dashboard shows a warning banner
until that password is changed. Use **Change password** in the dashboard straight
after your first sign-in: with `1234`, anyone who guesses it can read every customer's
name, phone number and comments.

## Deploy (Render, about 10 minutes)

1. Push this repository to GitHub (already done).
2. On [render.com](https://render.com): **New → Blueprint**, pick this repository.
   Render reads `render.yaml` and creates the web service and the PostgreSQL database.
3. When asked for `ADMIN_PASSWORD`, enter the first admin password.
4. When the deploy finishes, open the `.onrender.com` URL. Share `/` with customers
   and sign in at `/admin`.

Any host that runs Docker works the same way (Railway, Fly.io, a VPS). Set the
variables from `.env.example`, point `DATABASE_URL` at PostgreSQL 13 or newer, and
serve it over HTTPS.

## Run on your computer

With Docker:

```bash
docker compose up --build
```

Then open http://localhost:8000 (form) and http://localhost:8000/admin (dashboard).

Without Docker (Python 3.11+ and a PostgreSQL database):

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt python-dotenv
copy .env.example .env
.venv\Scripts\python -m uvicorn app.main:app --env-file .env --port 8000
```

Edit `.env` first: set `DATABASE_URL` and `COOKIE_SECURE=false` for local http.

## Database

Tables are created automatically on start-up from `migrations/*.sql`, applied in
order and recorded in `schema_migrations`.

```
forms ─┬─< form_sections ─< questions
       └─< feedback_responses >── customers
              │         └──> service_types
              └─< feedback_answers >── questions
admin_users ─< admin_sessions
```

- **forms / form_sections / questions**: the questions live in the database, so the
  customer page always shows what is stored there. Question types: `stars` (1–5),
  `choice` (pick one), `nps` (0–10).
- **customers**: one row per customer, matched by email (or phone if there is no email).
- **feedback_responses**: one row per submission, with the contact details exactly as
  typed, the overall rating and NPS copied out for fast filtering, a status
  (`new`, `reviewed`, `actioned`, `archived`) and timestamps.
- **feedback_answers**: one row per answered question: rating or chosen option,
  optional detail and the suggestion text.
- **admin_users / admin_sessions**: bcrypt password hashes; sessions store only a
  SHA-256 of the cookie token.

Every table has `created_at`, and editable tables have an `updated_at` kept by a trigger.
CHECK constraints enforce ratings, lengths, email shape and allowed statuses, so bad
data is refused by the database as well as by the API.

### Changing questions

Add a new migration file, for example `migrations/003_add_unloading_question.sql`:

```sql
INSERT INTO questions (form_id, section_id, code, question_type, prompt, sort_order)
SELECT f.id, s.id, 'unloading_time', 'stars', 'How quick was the unloading?', 125
FROM forms f JOIN form_sections s ON s.form_id = f.id
WHERE f.slug = 'customer-feedback' AND s.title = 'Time & punctuality';

-- Hide a question without losing its past answers:
UPDATE questions SET is_active = false WHERE code = 'driver_id';
```

Redeploy; the migration runs once on start-up. Never edit a migration that has
already run.

## Security

- Passwords hashed with bcrypt; failed sign-ins are slowed and an IP is locked out
  for 15 minutes after 5 failures.
- Session cookie is `HttpOnly`, `Secure` and `SameSite=Strict`; admin write requests
  from other sites are refused.
- All SQL is parameterised. Input is validated by the API (Pydantic) and the database
  (constraints).
- Customer text starting with `=` is written to Excel as text, so a response cannot
  plant a formula in your spreadsheet.
- Strict Content-Security-Policy and security headers on every page.
- Customer IPs are stored only as a keyed hash (for abuse checks). Submissions are
  limited to 10 per IP per 10 minutes, with a hidden spam trap field.
- Login and submit limits are kept in memory, so they apply per server instance.
  Run one instance, or move them to Redis if you scale out.

## Tests

```bash
set TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/ashwheelz_test
.venv\Scripts\pip install pytest httpx
.venv\Scripts\python -m pytest
```

The test database is wiped at the start of every run. Never point it at real data.

## Older version

`apps-script/` holds the first version of the form, which ran on Google Apps Script
and saved to a Google Sheet. It is kept for reference and is not used by this app.
