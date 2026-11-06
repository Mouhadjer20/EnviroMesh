"""User accounts in PostgreSQL. Passwords are never read back: they are checked and
written with pgcrypto (crypt / gen_salt('bf')), the same scheme as the seed data."""

import logging
import uuid

import psycopg2
from fastapi import HTTPException
from psycopg2 import errors
from psycopg2.extras import RealDictCursor

from services.database_access import _connect

logger = logging.getLogger("user_store")

_COLS = ("u.id::text AS id, u.first_name, u.last_name, u.email, u.role, u.active, "
         "u.password_change_required, g.group_code")
_FROM = "FROM users u LEFT JOIN groups g ON g.id = u.group_id"


def _run(sql, params=None, write=False, one=False):
    try:
        conn = _connect()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params or {})
                rows = cur.fetchall() if cur.description else []
            if write:
                conn.commit()
            return (rows[0] if rows else None) if one else rows
        finally:
            conn.close()
    except errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="Email already in use")
    except psycopg2.Error as exc:
        logger.error("User query failed: %s", exc)
        raise HTTPException(status_code=503, detail="Database unavailable")


def _valid_uuid(value):
    try:
        return str(uuid.UUID(str(value)))
    except ValueError:
        return None


def _check_group(group_code):
    if group_code and not _run("SELECT 1 FROM groups WHERE group_code = %(g)s", {"g": group_code}):
        raise HTTPException(status_code=422, detail=f"Unknown group {group_code}")


def authenticate(email, password):
    return _run(f"SELECT {_COLS} {_FROM} WHERE lower(u.email) = %(e)s AND u.active "
                "AND u.password = crypt(%(p)s, u.password)",
                {"e": email.lower(), "p": password}, one=True)


def get_user(user_id, include_inactive=False):
    uid = _valid_uuid(user_id)
    if not uid:
        return None
    return _run(f"SELECT {_COLS} {_FROM} WHERE u.id = %(id)s::uuid"
                + ("" if include_inactive else " AND u.active"), {"id": uid}, one=True)


def list_users():
    return _run(f"SELECT {_COLS} {_FROM} ORDER BY u.last_name, u.first_name")


def create_user(first_name, last_name, email, password, role, group_code):
    _check_group(group_code)
    row = _run("INSERT INTO users (first_name, last_name, email, password, group_id, role, password_change_required) "
               "VALUES (%(f)s, %(l)s, %(e)s, crypt(%(p)s, gen_salt('bf', 10)), "
               "(SELECT id FROM groups WHERE group_code = %(g)s::text), %(r)s, TRUE) RETURNING id::text",
               {"f": first_name, "l": last_name, "e": email.lower(), "p": password, "g": group_code, "r": role},
               write=True, one=True)
    return get_user(row["id"], include_inactive=True)


def update_user(user_id, changes):
    uid = _valid_uuid(user_id)
    if not uid:
        return None
    sets, params = [], {"id": uid}
    for col in ("first_name", "last_name", "email", "role", "active"):   # whitelist: no user-supplied column names
        if col in changes:
            sets.append(f"{col} = %({col})s")
            params[col] = changes[col].lower() if col == "email" else changes[col]
    if "group_code" in changes:
        _check_group(changes["group_code"])
        sets.append("group_id = (SELECT id FROM groups WHERE group_code = %(group_code)s::text)")
        params["group_code"] = changes["group_code"]
    if changes.get("password"):
        sets.append("password = crypt(%(password)s, gen_salt('bf', 10))")
        sets.append("password_change_required = TRUE")
        params["password"] = changes["password"]
    if sets:
        row = _run(f"UPDATE users SET {', '.join(sets)} WHERE id = %(id)s::uuid RETURNING id::text",
                   params, write=True, one=True)
        if not row:
            return None
    return get_user(uid, include_inactive=True)


def change_password(user_id, current, new):
    uid = _valid_uuid(user_id)
    if not uid:
        return False
    row = _run("UPDATE users SET password = crypt(%(n)s, gen_salt('bf', 10)), "
               "password_change_required = FALSE "
               "WHERE id = %(id)s::uuid AND active AND password = crypt(%(c)s, password) RETURNING id::text",
               {"n": new, "c": current, "id": uid}, write=True, one=True)
    return row is not None


def update_profile(user_id, first_name, last_name, email):
    uid = _valid_uuid(user_id)
    if not uid:
        return None
    _run("UPDATE users SET first_name = %(first_name)s, last_name = %(last_name)s, email = %(email)s "
         "WHERE id = %(id)s::uuid AND active",
         {"id": uid, "first_name": first_name, "last_name": last_name, "email": email.lower()},
         write=True)
    return get_user(uid)
