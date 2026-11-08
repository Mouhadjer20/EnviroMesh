"""Interactively create the first administrator without storing credentials in source."""

import getpass
import re
import sys
import os

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from services.database_access import _connect


def main():
    email = input("Administrator email: ").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 255:
        raise SystemExit("Enter a valid email address.")
    first_name = input("First name: ").strip()
    last_name = input("Last name: ").strip()
    if not first_name or len(first_name) > 100 or not last_name or len(last_name) > 100:
        raise SystemExit("First and last names are required (maximum 100 characters each).")
    password = getpass.getpass("Administrator password (12+ characters): ")
    if len(password) < 12 or len(password) > 200:
        raise SystemExit("The administrator password must be between 12 and 200 characters.")
    if password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords do not match.")

    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('enviromesh:first-admin'))")
            cur.execute("SELECT EXISTS (SELECT 1 FROM users WHERE role = 'admin' AND active)")
            if cur.fetchone()[0]:
                raise SystemExit("An active administrator already exists; bootstrap refused.")
            cur.execute(
                """
                INSERT INTO users
                    (first_name, last_name, email, password, role, active, password_change_required)
                VALUES (%s, %s, %s, crypt(%s, gen_salt('bf', 12)), 'admin', TRUE, FALSE)
                """,
                (first_name, last_name, email, password),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print("Administrator account created.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAdministrator bootstrap cancelled.")
        sys.exit(130)
