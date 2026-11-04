"""Lecture de la base (registre + télémétrie) pour les routes de l'API.

Les écritures restent dans services/database_writer.py. Les paramètres de
connexion sont les mêmes (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, ou
POSTGRES_*). Une connexion courte par requête suffit à ce volume.
"""

import logging
import os

import psycopg2
from fastapi import HTTPException
from psycopg2.extras import RealDictCursor

logger = logging.getLogger("database_access")


def _connect():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME", os.getenv("POSTGRES_DB", "enviromesh")),
        user=os.getenv("DB_USER", os.getenv("POSTGRES_USER", "enviromesh_app")),
        password=os.getenv("DB_PASSWORD", os.getenv("POSTGRES_PASSWORD", "")),
        connect_timeout=5,
    )


def _query(sql, params=None, what="data"):
    try:
        conn = _connect()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params or {})
                return cur.fetchall()
        finally:
            conn.close()
    except psycopg2.Error as exc:
        logger.error("Could not read %s: %s", what, exc)
        raise HTTPException(status_code=503, detail="Database unavailable")


def list_groups():
    return _query("SELECT group_code, description FROM groups ORDER BY group_code", what="groups")


def list_devices(device_id=None):
    return _query(
        """
        SELECT d.device_id, d.zone, d.latitude, d.longitude, g.group_code,
               COALESCE(
                   json_agg(json_build_object('name', s.name, 'status', sd.status))
                       FILTER (WHERE s.id IS NOT NULL),
                   '[]'::json
               ) AS sensors
        FROM devices d
        LEFT JOIN groups g ON g.id = d.group_id
        LEFT JOIN sensor_devices sd ON sd.device_id = d.device_id
        LEFT JOIN sensors s ON s.id = sd.sensor_id
        WHERE (%(device_id)s::text IS NULL OR d.device_id = %(device_id)s)
        GROUP BY d.device_id, g.group_code
        ORDER BY d.device_id
        """,
        {"device_id": device_id},
        what="device inventory",
    )


_TELEMETRY = """
    SELECT t.timestamp, t.device_id, t.zone, t.metrics, t.received_at,
           t.protocol, t.rssi, t.metadata,
           COALESCE(g.group_code, t.metadata->>'group_code') AS group_code
    FROM sensor_telemetry t
    LEFT JOIN devices d ON d.device_id = t.device_id
    LEFT JOIN groups g ON g.id = d.group_id
"""


def list_telemetry(device_id=None, start=None, end=None, limit=100):
    return _query(
        _TELEMETRY
        + """
        WHERE (%(device_id)s::text IS NULL OR t.device_id = %(device_id)s)
          AND (%(start)s::timestamptz IS NULL OR t.timestamp >= %(start)s)
          AND (%(end)s::timestamptz IS NULL OR t.timestamp <= %(end)s)
        ORDER BY t.timestamp DESC
        LIMIT %(limit)s
        """,
        {"device_id": device_id, "start": start, "end": end, "limit": limit},
        what="telemetry",
    )


def latest_telemetry(device_id=None):
    """Dernière mesure de chaque nœud (ou d'un seul nœud)."""
    sql = _TELEMETRY.replace("SELECT t.timestamp", "SELECT DISTINCT ON (t.device_id) t.timestamp", 1)
    return _query(
        sql
        + """
        WHERE (%(device_id)s::text IS NULL OR t.device_id = %(device_id)s)
        ORDER BY t.device_id, t.timestamp DESC
        """,
        {"device_id": device_id},
        what="latest telemetry",
    )
