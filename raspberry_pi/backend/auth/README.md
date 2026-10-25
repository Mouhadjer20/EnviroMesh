# Authentication — EnviroMesh Core Server

This folder contains the authentication and authorization logic for the
EnviroMesh platform API.

---

## Table of Contents

- [Responsibilities](#responsibilities)
- [Suggested Contents](#suggested-contents)
- [Security Notes](#security-notes)
- [Related Documentation](#related-documentation)

---

## Responsibilities

- **User registration & login** with email/password credentials.
- **Password hashing** using bcrypt (via `passlib` / `bcrypt`), matching the
  `pgcrypto` scheme used in the database layer (`db/migration/001_create_registry.sql`).
- **JWT token issuance & validation** (access tokens + optional refresh tokens).
- **Role-Based Access Control (RBAC):** `admin` and `zone_technician` roles.
- **Zone-scoped access:** Users can only access devices/telemetry within their
  assigned group/zone.

## Suggested Contents

```
auth/
├── dependencies.py      # FastAPI dependencies: get_current_user, require_admin, etc.
├── jwt_utils.py         # Token creation, decoding, expiration
├── password.py          # bcrypt hash / verify helpers
├── models.py            # User, Token, TokenData Pydantic/SQLAlchemy models
└── router.py            # /auth/register, /auth/login, /auth/refresh endpoints
```

## Security Notes

- Never log or return plaintext passwords.
- Use short-lived access tokens (e.g. 15–30 min) with refresh tokens for session renewal.
- Enforce HTTPS in production (WPA3-Enterprise / TLS-secured MQTT for device links).
- Validate the user's `allowed_zones` claim against the requested device's zone
  to prevent Broken Object Level Authorization (BOLA).

## Related Documentation

- Project architecture: [`../../README.md`](../../README.md)
- Database layer: [`../../db`](../../db)
- API routes: [`../routes`](../routes)