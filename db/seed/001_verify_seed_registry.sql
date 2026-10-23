
-- Verify groups and student counts.
SELECT
    g.group_code,
    g.description,
    COUNT(u.id) AS student_count
FROM groups AS g
LEFT JOIN users AS u
    ON u.group_id = g.id
GROUP BY g.id, g.group_code, g.description
ORDER BY g.group_code;


-- Verify students and their group assignments.
SELECT
    u.first_name,
    u.last_name,
    u.email,
    g.group_code,
    u.role
FROM users AS u
LEFT JOIN groups AS g
    ON g.id = u.group_id
ORDER BY g.group_code NULLS LAST, u.last_name;


-- Verify users without a group assignment.
SELECT id, first_name, last_name, email
FROM users
WHERE group_id IS NULL;


-- Verify sensor catalog.
SELECT id, name, description
FROM sensors
ORDER BY name;
