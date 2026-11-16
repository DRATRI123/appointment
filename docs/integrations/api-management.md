# External API management

Admin → **Developers** → API keys, webhooks, usage and the in-app API documentation (`/admin/developers/docs`); OpenAPI
at `/api/v1/openapi.json`, Swagger at `/docs`, ReDoc at `/redoc`. Full guide: [../developer-guide.md](../developer-guide.md).

| Feature | How |
|---|---|
| Keys | `ak_live_…`, shown once, stored as a keyed hash; `X-API-Key` header or `Authorization: Bearer` |
| Permissions | scopes chosen per key (never payment verification, staff, roles, settings, keys or webhooks); you can only grant what you have |
| Rate limits | per key (default 120 per minute), shared between API processes (Redis on servers) |
| IP allow-list | optional, addresses or CIDR ranges |
| Expiry | optional date |
| **Rotation** | "Rotate": a new key with the same settings (shown once); the old key keeps working 24 hours (API: `grace_hours` 0–168) |
| **Access log** | the last 100 requests per key: method, route template (no query strings), status, time, address; 30 days |
| Usage | requests, client errors, server errors, rate-limited per day |
| Revocation | immediate |
| Versioning | `/api/v1`; webhook payloads carry `api_version` (`2026-11`) |

Public booking pages and Shopify/website snippets use only public endpoints and never contain a key. Never put an API key
in browser JavaScript or theme code.
