-- Seeds the customer feedback form, its questions and service types.
-- To change questions later, add a new migration (e.g. 003_...sql) that
-- inserts rows or sets is_active = false; never edit applied migrations.

INSERT INTO forms (slug, title) VALUES ('customer-feedback', 'How was your delivery?');

INSERT INTO form_sections (form_id, title, sort_order)
SELECT f.id, s.title, s.ord
FROM forms f,
     (VALUES ('Time & punctuality', 1), ('Safety', 2), ('Driver & crew', 3),
             ('Hygiene & cleanliness', 4), ('Service & support', 5), ('Overall', 6)) AS s(title, ord)
WHERE f.slug = 'customer-feedback';

INSERT INTO questions (form_id, section_id, code, question_type, prompt, hint, options, detail_options, is_required, sort_order)
SELECT f.id, s.id, q.code, q.qtype, q.prompt, q.hint, q.options::jsonb, q.detail::jsonb, q.req, q.ord
FROM forms f
JOIN form_sections s ON s.form_id = f.id
JOIN (VALUES
  ('Time & punctuality', 'pickup_time', 'stars', 'Was the pickup on time?', 'Did the vehicle arrive at the agreed pickup time?', '[]', '[]', false, 10),
  ('Time & punctuality', 'delivery_time', 'stars', 'Was the delivery on time?', 'Compared with the delivery date or time we promised.', '[]',
     '["Early","On time","Few hours late","1 day late","More than 1 day late"]', false, 20),
  ('Safety', 'goods_condition', 'choice', 'In what condition did your goods arrive?', NULL,
     '["Perfect condition","Minor damage","Major damage","Some items missing"]', '[]', false, 30),
  ('Safety', 'goods_safety', 'stars', 'How safely were your goods handled?', 'Loading, strapping, covering and unloading.', '[]', '[]', false, 40),
  ('Safety', 'driving_safety', 'stars', 'How safe was the driving?', 'Speed, following traffic rules, careful driving.', '[]', '[]', false, 50),
  ('Safety', 'vehicle_condition', 'choice', 'Was the vehicle in good condition?', NULL,
     '["Yes, well maintained","Average","No, poorly maintained"]', '[]', false, 60),
  ('Driver & crew', 'driver_behaviour', 'stars', 'How was the driver''s behaviour?', 'Polite, respectful and helpful.', '[]', '[]', false, 70),
  ('Driver & crew', 'driver_communication', 'stars', 'Did the driver keep you informed?', 'Calls or messages about arrival and delays.', '[]', '[]', false, 80),
  ('Driver & crew', 'driver_id', 'choice', 'Was the driver in uniform or carrying an Ashwheelz ID?', NULL,
     '["Yes","No","Didn''t notice"]', '[]', false, 90),
  ('Hygiene & cleanliness', 'vehicle_hygiene', 'stars', 'How clean was the vehicle / container?', 'Free of dust, dirt, smell, pests or leftover cargo.', '[]', '[]', false, 100),
  ('Hygiene & cleanliness', 'crew_hygiene', 'stars', 'How was the personal hygiene of the driver and crew?', NULL, '[]', '[]', false, 110),
  ('Hygiene & cleanliness', 'packaging', 'stars', 'How clean and intact was the packaging at delivery?', NULL, '[]', '[]', false, 120),
  ('Service & support', 'booking_ease', 'stars', 'How easy was booking with us?', NULL, '[]', '[]', false, 130),
  ('Service & support', 'tracking', 'stars', 'How useful were the tracking updates?', NULL, '[]', '[]', false, 140),
  ('Service & support', 'support', 'stars', 'How helpful was our customer support team?', NULL, '[]', '[]', false, 150),
  ('Service & support', 'pricing', 'stars', 'Was the price fair and transparent?', 'No hidden or surprise charges.', '[]', '[]', false, 160),
  ('Overall', 'overall', 'stars', 'Overall, how would you rate Ashwheelz?', NULL, '[]', '[]', true, 170),
  ('Overall', 'nps', 'nps', 'How likely are you to recommend Ashwheelz to a friend or business?', NULL, '[]', '[]', false, 180),
  ('Overall', 'use_again', 'choice', 'Would you book with Ashwheelz again?', NULL, '["Definitely","Maybe","No"]', '[]', false, 190)
) AS q(section, code, qtype, prompt, hint, options, detail, req, ord) ON q.section = s.title
WHERE f.slug = 'customer-feedback';

INSERT INTO service_types (name, sort_order) VALUES
  ('Full truck load (FTL)', 1),
  ('Part truck load (PTL)', 2),
  ('Express / courier', 3),
  ('Last-mile delivery', 4),
  ('Warehousing', 5),
  ('Household / office shifting', 6),
  ('Other', 7);
