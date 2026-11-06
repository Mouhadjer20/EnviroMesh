"""Database operations for group administration."""

import logging

import psycopg2
from fastapi import HTTPException
from psycopg2 import errors
from psycopg2.extras import RealDictCursor

from services.database_access import _connect

logger = logging.getLogger("group_store")


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
        raise HTTPException(status_code=409, detail="Group already exists")
    except psycopg2.Error as exc:
        logger.error("Group query failed: %s", exc)
        raise HTTPException(status_code=503, detail="Database unavailable")


def list_groups(group_code=None):
    return _run(
        """
        SELECT g.group_code, g.description,
               (SELECT count(*) FROM users u WHERE u.group_id = g.id AND u.active) AS user_count,
               (SELECT count(*) FROM devices d WHERE d.group_id = g.id) AS device_count,
               COALESCE((
                   SELECT json_agg(json_build_object(
                       'device_id', d.device_id, 'zone', d.zone
                   ) ORDER BY d.device_id)
                   FROM devices d WHERE d.group_id = g.id
               ), '[]'::json) AS devices
        FROM groups g
        WHERE (%(group_code)s::text IS NULL OR g.group_code = %(group_code)s)
        ORDER BY g.group_code
        """,
        {"group_code": group_code},
    )


def create_group(group_code, description):
    _run(
        "INSERT INTO groups (group_code, description) VALUES (%(code)s, %(description)s)",
        {"code": group_code, "description": description},
        write=True,
    )
    return list_groups(group_code)[0]


def update_group(group_code, description):
    row = _run(
        "UPDATE groups SET description = %(description)s WHERE group_code = %(code)s "
        "RETURNING group_code",
        {"code": group_code, "description": description},
        write=True,
        one=True,
    )
    return list_groups(group_code)[0] if row else None


def assign_device(group_code, device_id):
    row = _run(
        "UPDATE devices SET group_id = (SELECT id FROM groups WHERE group_code = %(code)s) "
        "WHERE device_id = %(device)s AND EXISTS "
        "(SELECT 1 FROM groups WHERE group_code = %(code)s) RETURNING device_id",
        {"code": group_code, "device": device_id},
        write=True,
        one=True,
    )
    return row is not None
