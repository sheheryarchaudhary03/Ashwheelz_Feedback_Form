-- New service list. Old services are hidden (is_active = false), not deleted,
-- so earlier responses keep showing the service they picked.
-- requires_detail marks a choice (e.g. "Other") that needs the customer to
-- type what they used; that text is stored in feedback_responses.service_other.

ALTER TABLE service_types ADD COLUMN requires_detail boolean NOT NULL DEFAULT false;
ALTER TABLE feedback_responses
  ADD COLUMN service_other text CHECK (length(service_other) BETWEEN 1 AND 200);

UPDATE service_types SET is_active = false;

INSERT INTO service_types (name, sort_order, requires_detail) VALUES
  ('Heavy Vehicle Rental', 101, false),
  ('Heavy Equipment Rental', 102, false),
  ('Light Vehicle Rental', 103, false),
  ('Transportation & Logistics', 104, false),
  ('Custom Clearance & Freight Forwarding', 105, false),
  ('Energy Rental Solutions', 106, false),
  ('Crane & Forklift Rental', 107, false),
  ('Trailer Rental', 108, false),
  ('Staff Transportation', 109, false),
  ('Other (Please Specify)', 110, true)
ON CONFLICT (name) DO UPDATE SET
  sort_order = EXCLUDED.sort_order,
  requires_detail = EXCLUDED.requires_detail,
  is_active = true;
