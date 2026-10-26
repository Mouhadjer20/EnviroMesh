-- =========================================================
-- SEED DATA: ENVIRONMENTAL MONITORING SYSTEM
-- Tables: groups, students, sensors, devices, sensor_devices
-- Default password: password123
-- IMPORTANT: Change default passwords after first login.
-- PostgreSQL
-- =========================================================

BEGIN;

-- 1. Insert groups G1 through G7.
INSERT INTO
    groups (group_code, description)
VALUES ('G1', 'Group 1'),
    ('G2', 'Group 2'),
    ('G3', 'Group 3'),
    ('G4', 'Group 4'),
    ('G5', 'Group 5'),
    ('G6', 'Group 6'),
    ('G7', 'Group 7') ON CONFLICT (group_code) DO NOTHING;

-- 2. Prepare the student records.
-- A NULL group number means the student is not assigned
-- to a group until their correct group is confirmed.

WITH
    password_hash AS MATERIALIZED (
        SELECT crypt (
                'password123', gen_salt ('bf')
            ) AS hash
    ),
    student_data (
        student_code,
        last_name,
        first_name,
        group_number
    ) AS (
        VALUES (
                'UN31032025222237326201',
                'ABDELMOUMENE',
                'MOUHCINE',
                1
            ),
            (
                'UN31032025222237326310',
                'ABOURA',
                'YACINE',
                1
            ),
            (
                'UN31032025222238324820',
                'ALEM',
                'HALIMA',
                2
            ),
            (
                'UN31032025222237427010',
                'BENAINI',
                'MEROUA',
                2
            ),
            (
                'UN31032025222238125604',
                'BENAMARA',
                'FERIAL MARINA MANEL',
                3
            ),
            (
                'UN31032025222237350213',
                'BENDEHINA',
                'MOHAMMED BADR',
                4
            ),
            (
                'UN31032025222237336020',
                'BENTAYEB',
                'AHMED',
                5
            ),
            (
                'UN31032025222237420207',
                'CHAALAL',
                'DJAOUED',
                4
            ),
            (
                'UN31032025222237336003',
                'FERGANI',
                'AYA',
                6
            ),
            (
                'UN31032025222237378413',
                'GUELTA',
                'MOHAMED TAHAR',
                5
            ),
            (
                'UN31032025222237357501',
                'HADJ ABDERRAHMANE',
                'ADEM',
                5
            ),
            (
                'UN31032025222237357212',
                'KADDOUR',
                'YAZID',
                1
            ),
            (
                'UN31032025222237357602',
                'KARAR',
                'YAHIA MOHAMMED',
                5
            ),
            (
                'UN31032025222232009107',
                'KHELIFI',
                'Ayyoub',
                4
            ),
            (
                'UN31032025222237355915',
                'LAAZ',
                'ABDELAZIZ FAROUK',
                1
            ),
            (
                'UN31032025222237333401',
                'MELOUK',
                'ROMAISSA MALEK',
                6
            ),
            (
                'UN31032025222237362420',
                'MOUHADJER',
                'AISSA',
                4
            ),
            (
                'UN31032025222237357801',
                'SALAH',
                'OUSSAM',
                1
            ),
            (
                'UN31032025222237326304',
                'TAHA',
                'HANAA AMIRA',
                3
            ),
            (
                'UN31032025222237326306',
                'TAHA',
                'WAHIBA',
                3
            )
    )

-- 3. Insert users with their corresponding group UUIDs.
INSERT INTO users (
    first_name,
    last_name,
    email,
    password,
    group_id,
    role
)
SELECT
    s.first_name,
    s.last_name,
    substring(s.student_code FROM 11)
        || '@etu.uni-usto.dz',
    p.hash,
    g.id,
    'zone_technician'
FROM student_data AS s
CROSS JOIN password_hash AS p
LEFT JOIN groups AS g
    ON g.group_code = 'G' || s.group_number::TEXT
ON CONFLICT (email) DO NOTHING;

COMMIT;

-- =========================================================
-- 1. GROUPS
-- Preserve the seven groups used by the project.
-- =========================================================

INSERT INTO
    groups (group_code, description)
VALUES (
        'G1',
        'Group 1 - LoRa environmental node'
    ),
    ('G2', 'Group 2 - Reserved'),
    (
        'G3',
        'Group 3 - Wi-Fi environmental node'
    ),
    (
        'G4',
        'Group 4 - LoRa environmental node'
    ),
    ('G5', 'Group 5 - Reserved'),
    (
        'G6',
        'Group 6 - Wi-Fi servo and motion node'
    ),
    ('G7', 'Group 7 - Reserved') ON CONFLICT (group_code) DO NOTHING;

-- =========================================================
-- 2. SENSOR CATALOG
-- Insert only sensor models that do not already exist.
-- =========================================================

INSERT INTO
    sensors (name, description)
SELECT v.name, v.description
FROM (
        VALUES (
                'MQ-2', 'Gas and smoke detection sensor'
            ), (
                'DHT11', 'Temperature and relative humidity sensor'
            ), (
                'Water Sensor', 'Water presence and leak detection sensor'
            ), (
                'BMP280', 'Barometric pressure and temperature sensor'
            ), (
                'PIR', 'Passive infrared motion detection sensor'
            )
    ) AS v (name, description)
WHERE
    NOT EXISTS (
        SELECT 1
        FROM sensors AS s
        WHERE
            s.name = v.name
    );

-- =========================================================
-- 3. PHYSICAL DEVICES
-- Device IDs follow the format: group code + device number.
-- Zones below are illustrative; update them to actual sites.
-- =========================================================

INSERT INTO devices (
    device_id,
    zone,
    latitude,
    longitude,
    group_id
)
SELECT
    d.device_id,
    d.zone,
    d.latitude,
    d.longitude,
    g.id
FROM (
    VALUES
        (
            'G11',
            'Sector_A_Warehouse',
            NULL::DOUBLE PRECISION,
            NULL::DOUBLE PRECISION,
            'G1'
        ),
        (
            'G41',
            'Sector_B_Warehouse',
            NULL::DOUBLE PRECISION,
            NULL::DOUBLE PRECISION,
            'G4'
        ),
        (
            'G31',
            'Sector_C_Utility_Room',
            NULL::DOUBLE PRECISION,
            NULL::DOUBLE PRECISION,
            'G3'
        ),
        (
            'G61',
            'Sector_A_Valve',
            NULL::DOUBLE PRECISION,
            NULL::DOUBLE PRECISION,
            'G6'
        )
) AS d(device_id, zone, latitude, longitude, group_code)
JOIN groups AS g
    ON g.group_code = d.group_code
ON CONFLICT (device_id) DO NOTHING;

-- =========================================================
-- 4. SENSOR-DEVICE ASSIGNMENTS
-- Each pair links one catalog sensor to one physical device.
-- =========================================================

WITH sensor_catalog AS (
    -- Handle any pre-existing duplicate sensor names by
    -- selecting one catalog entry per name for assignments.
    SELECT DISTINCT ON (name)
        id,
        name
    FROM sensors
    ORDER BY name, id
),
assignments (device_id, sensor_name, configuration) AS (
    VALUES
        -- G1: ESP32 Node 1
        (
            'G11', 'MQ-2',
            '{"measurement": "gas_and_smoke"}'::JSONB
        ),
        (
            'G11', 'DHT11',
            '{"measurements": ["temperature_c", "humidity_pct"]}'::JSONB
        ),
        (
            'G11', 'Water Sensor',
            '{"measurement": "water_leak_detected"}'::JSONB
        ),

-- G4: ESP32 Node 2
(
            'G41', 'MQ-2',
            '{"measurement": "gas_and_smoke"}'::JSONB
        ),
        (
            'G41', 'DHT11',
            '{"measurements": ["temperature_c", "humidity_pct"]}'::JSONB
        ),
        (
            'G41', 'Water Sensor',
            '{"measurement": "water_leak_detected"}'::JSONB
        ),

-- G3: ESP32 Node 3
(
            'G31', 'BMP280',
            '{"measurements": ["pressure_hpa", "temperature_c"]}'::JSONB
        ),
        (
            'G31', 'MQ-2',
            '{"measurement": "gas_and_smoke"}'::JSONB
        ),
        (
            'G31', 'Water Sensor',
            '{"measurement": "water_leak_detected"}'::JSONB
        ),

-- G6: ESP32 Servo Node
(
            'G61', 'MQ-2',
            '{"measurement": "gas_and_smoke"}'::JSONB
        ),
        (
            'G61', 'DHT11',
            '{"measurements": ["temperature_c", "humidity_pct"]}'::JSONB
        ),
        (
            'G61', 'Water Sensor',
            '{"measurement": "water_leak_detected"}'::JSONB
        ),
        (
            'G61', 'PIR',
            '{"measurement": "motion_detected"}'::JSONB
        )
)
INSERT INTO sensor_devices (
    id,
    sensor_id,
    device_id,
    installed_at,
    status,
    configuration
)
SELECT
    gen_random_uuid(),
    s.id,
    a.device_id,
    CURRENT_TIMESTAMP,
    'active',
    a.configuration
FROM assignments AS a
JOIN sensor_catalog AS s
    ON s.name = a.sensor_name
JOIN devices AS d
    ON d.device_id = a.device_id
ON CONFLICT (sensor_id, device_id) DO NOTHING;

COMMIT;

-- =========================================================
-- 5. VERIFY THE SEEDED TOPOLOGY
-- =========================================================

SELECT
    d.device_id,
    g.group_code,
    d.zone,
    s.name AS sensor_name,
    sd.status AS assignment_status,
    sd.configuration
FROM
    devices AS d
    JOIN groups AS g ON g.id = d.group_id
    JOIN sensor_devices AS sd ON sd.device_id = d.device_id
    JOIN sensors AS s ON s.id = sd.sensor_id
ORDER BY d.device_id, s.name;