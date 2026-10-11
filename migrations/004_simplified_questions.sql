-- Replaces the long questionnaire with six star ratings plus the
-- recommendation question. Old questions are hidden (is_active = false),
-- not deleted, so earlier responses keep their answers.

UPDATE forms SET title = 'Help Us Serve You Better' WHERE slug = 'customer-feedback';

UPDATE questions SET is_active = false
WHERE form_id = (SELECT id FROM forms WHERE slug = 'customer-feedback');

INSERT INTO form_sections (form_id, title, sort_order)
SELECT f.id, s.title, s.ord
FROM forms f,
     (VALUES ('Overall Service', 101), ('Timeliness', 102), ('Driver Professionalism', 103),
             ('Safety', 104), ('Vehicle Cleanliness', 105), ('Customer Support', 106),
             ('Final Question', 107)) AS s(title, ord)
WHERE f.slug = 'customer-feedback'
ON CONFLICT (form_id, title) DO UPDATE SET sort_order = EXCLUDED.sort_order;

-- 'overall' and 'nps' keep their codes: the dashboard reads them for the
-- average rating and the recommendation score.
INSERT INTO questions (form_id, section_id, code, question_type, prompt, hint, options, detail_options,
                       is_required, is_active, sort_order)
SELECT f.id, s.id, q.code, q.qtype, q.prompt, NULL, '[]'::jsonb, '[]'::jsonb, q.req, true, q.ord
FROM forms f
JOIN form_sections s ON s.form_id = f.id
JOIN (VALUES
  ('Overall Service', 'overall', 'stars', 'How would you rate your overall experience with Ashwheelz?', true, 10),
  ('Timeliness', 'timeliness', 'stars', 'Was the service provided on time?', false, 20),
  ('Driver Professionalism', 'driver_professionalism', 'stars', 'How would you rate our driver''s professionalism?', false, 30),
  ('Safety', 'safety_standards', 'stars', 'How satisfied were you with our safety standards?', false, 40),
  ('Vehicle Cleanliness', 'vehicle_cleanliness', 'stars', 'How would you rate the cleanliness of the vehicle/equipment?', false, 50),
  ('Customer Support', 'customer_support', 'stars', 'How satisfied were you with our communication and support?', false, 60),
  ('Final Question', 'nps', 'nps', 'Would you recommend Ashwheelz to others?', false, 70)
) AS q(section, code, qtype, prompt, req, ord) ON q.section = s.title
WHERE f.slug = 'customer-feedback'
ON CONFLICT (form_id, code) DO UPDATE SET
  section_id     = EXCLUDED.section_id,
  question_type  = EXCLUDED.question_type,
  prompt         = EXCLUDED.prompt,
  hint           = EXCLUDED.hint,
  options        = EXCLUDED.options,
  detail_options = EXCLUDED.detail_options,
  is_required    = EXCLUDED.is_required,
  is_active      = true,
  sort_order     = EXCLUDED.sort_order;
