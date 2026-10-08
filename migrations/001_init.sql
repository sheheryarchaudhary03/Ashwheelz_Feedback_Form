-- Ashwheelz feedback: core schema.
-- Requires PostgreSQL 13+ (gen_random_uuid is built in).

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------- admins
CREATE TABLE admin_users (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  username       text        NOT NULL UNIQUE CHECK (username ~ '^[a-z0-9_.-]{3,50}$'),
  password_hash  text        NOT NULL,
  is_active      boolean     NOT NULL DEFAULT true,
  last_login_at  timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_admin_users_updated BEFORE UPDATE ON admin_users
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Only a SHA-256 of the session token is stored, never the token itself.
CREATE TABLE admin_sessions (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  admin_user_id  bigint      NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
  token_hash     bytea       NOT NULL UNIQUE,
  ip_address     inet,
  user_agent     text        CHECK (length(user_agent) <= 500),
  created_at     timestamptz NOT NULL DEFAULT now(),
  expires_at     timestamptz NOT NULL
);
CREATE INDEX idx_admin_sessions_admin ON admin_sessions(admin_user_id);
CREATE INDEX idx_admin_sessions_expires ON admin_sessions(expires_at);

-- ---------------------------------------------------- forms & questions
-- A form owns ordered sections; sections own ordered questions. New forms
-- (e.g. a warehousing survey) are new rows, not schema changes.
CREATE TABLE forms (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  slug        text        NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9-]{2,60}$'),
  title       text        NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
  is_active   boolean     NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_forms_updated BEFORE UPDATE ON forms
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE form_sections (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  form_id     bigint      NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
  title       text        NOT NULL CHECK (length(title) BETWEEN 1 AND 120),
  sort_order  integer     NOT NULL DEFAULT 0,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (form_id, title)
);
CREATE TRIGGER trg_form_sections_updated BEFORE UPDATE ON form_sections
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE questions (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  form_id         bigint      NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
  section_id      bigint      NOT NULL REFERENCES form_sections(id) ON DELETE RESTRICT,
  code            text        NOT NULL CHECK (code ~ '^[a-z0-9_]{2,64}$'),
  question_type   text        NOT NULL CHECK (question_type IN ('stars', 'choice', 'nps')),
  prompt          text        NOT NULL CHECK (length(prompt) BETWEEN 1 AND 300),
  hint            text        CHECK (length(hint) <= 300),
  options         jsonb       NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(options) = 'array'),
  detail_options  jsonb       NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(detail_options) = 'array'),
  is_required     boolean     NOT NULL DEFAULT false,
  is_active       boolean     NOT NULL DEFAULT true,
  sort_order      integer     NOT NULL DEFAULT 0,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (form_id, code),
  CHECK (question_type <> 'choice' OR jsonb_array_length(options) > 0)
);
CREATE INDEX idx_questions_section ON questions(section_id);
CREATE TRIGGER trg_questions_updated BEFORE UPDATE ON questions
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE service_types (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name        text        NOT NULL UNIQUE CHECK (length(name) BETWEEN 1 AND 100),
  sort_order  integer     NOT NULL DEFAULT 0,
  is_active   boolean     NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_service_types_updated BEFORE UPDATE ON service_types
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ------------------------------------------------------------- customers
-- One row per real customer, matched on email (or phone when no email).
-- Responses keep their own copy of the contact details as typed, so a
-- stranger entering someone's email can never rewrite that customer.
CREATE TABLE customers (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name          text        NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
  email         text        CHECK (email ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$' AND length(email) <= 254),
  phone_digits  text        CHECK (phone_digits ~ '^[0-9]{6,20}$'),
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at  timestamptz NOT NULL DEFAULT now(),
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_customers_email ON customers (lower(email)) WHERE email IS NOT NULL;
CREATE INDEX idx_customers_phone ON customers (phone_digits) WHERE phone_digits IS NOT NULL;
CREATE TRIGGER trg_customers_updated BEFORE UPDATE ON customers
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ------------------------------------------------------------- feedback
CREATE TABLE feedback_responses (
  id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  reference_code     text        NOT NULL UNIQUE CHECK (reference_code ~ '^AW-[0-9]{6}-[A-Z0-9]{6}$'),
  form_id            bigint      NOT NULL REFERENCES forms(id) ON DELETE RESTRICT,
  customer_id        bigint      NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
  service_type_id    bigint      REFERENCES service_types(id) ON DELETE SET NULL,
  customer_name      text        NOT NULL CHECK (length(customer_name) BETWEEN 1 AND 120),
  customer_company   text        CHECK (length(customer_company) <= 160),
  customer_phone     text        CHECK (length(customer_phone) <= 30),
  customer_email     text        CHECK (length(customer_email) <= 254),
  -- Copied from the 'overall' and 'nps' answers so the dashboard can filter fast.
  overall_rating     smallint    CHECK (overall_rating BETWEEN 1 AND 5),
  nps_score          smallint    CHECK (nps_score BETWEEN 0 AND 10),
  other_suggestions  text        CHECK (length(other_suggestions) <= 4000),
  status             text        NOT NULL DEFAULT 'new'
                                 CHECK (status IN ('new', 'reviewed', 'actioned', 'archived')),
  source             text        NOT NULL DEFAULT 'web' CHECK (length(source) <= 30),
  ip_hash            text        CHECK (length(ip_hash) <= 64),
  user_agent         text        CHECK (length(user_agent) <= 500),
  submitted_at       timestamptz NOT NULL DEFAULT now(),
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_responses_submitted ON feedback_responses (submitted_at DESC);
CREATE INDEX idx_responses_customer ON feedback_responses (customer_id);
CREATE INDEX idx_responses_service ON feedback_responses (service_type_id);
CREATE INDEX idx_responses_overall ON feedback_responses (overall_rating);
CREATE INDEX idx_responses_status ON feedback_responses (status);
CREATE TRIGGER trg_responses_updated BEFORE UPDATE ON feedback_responses
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE feedback_answers (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  response_id    uuid        NOT NULL REFERENCES feedback_responses(id) ON DELETE CASCADE,
  question_id    bigint      NOT NULL REFERENCES questions(id) ON DELETE RESTRICT,
  rating         smallint    CHECK (rating BETWEEN 0 AND 10),
  choice_value   text        CHECK (length(choice_value) <= 200),
  detail_value   text        CHECK (length(detail_value) <= 200),
  suggestion     text        CHECK (length(suggestion) <= 2000),
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (response_id, question_id),
  CHECK (rating IS NOT NULL OR choice_value IS NOT NULL
         OR detail_value IS NOT NULL OR suggestion IS NOT NULL)
);
CREATE INDEX idx_answers_question ON feedback_answers (question_id, rating);
