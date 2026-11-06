-- Force accounts created with the published seed password to choose a unique
-- password before using the protected dashboard.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS password_change_required BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE users
SET password_change_required = TRUE
WHERE password = crypt('password123', password)
  AND password_change_required = FALSE;

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_lower
    ON users (lower(email));
