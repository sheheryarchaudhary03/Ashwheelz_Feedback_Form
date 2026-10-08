-- Sign-in lockouts and submission limits, kept in the database so they hold
-- across every server instance (Vercel runs many short-lived ones).
CREATE TABLE rate_limit_hits (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  bucket      text        NOT NULL CHECK (bucket IN ('login_fail', 'submit')),
  key_hash    text        NOT NULL CHECK (length(key_hash) = 64),
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_rate_limit_lookup ON rate_limit_hits (bucket, key_hash, created_at);
