# API Reference (overview)

Base URL: `/api/v1`. Interactive docs: `/docs` (Swagger UI) and `/redoc`; OpenAPI JSON at
`/api/v1/openapi.json`.

## Conventions

* JSON everywhere; `Content-Type: application/json` (multipart for uploads).
* Lists: `GET …?page=1&page_size=20&sort=-created_at&<filters>` → `{ "data": [...], "meta": { "page", "page_size", "total" } }`.
* Single resources return the object directly.
* Errors: `{ "detail": "message", "code": "machine_code", "errors": [ ...field errors ] }` with
  proper HTTP status codes (400 validation, 401 unauthenticated, 403 forbidden, 404 not found,
  409 conflict such as slot taken or duplicate UTR, 422 schema validation, 429 rate limited).
* Every response carries `X-Request-ID`.
* Authentication: `Authorization: Bearer <access_token>` or HttpOnly cookies set by `/auth/*`.
* Tenant selection for multi-organization users: `X-Organization-Id: <organization public id>`.

## Module map

| Prefix | Phase | Status |
|---|---|---|
| `/health`, `/health/ready` | 1 | implemented |
| `/meta` | 1 | implemented (version, environment) |
| `/auth` | 2 | planned |
| `/organizations` | 2 | planned |
| `/branches` | 3 | planned |
| `/professionals` | 3 | planned |
| `/service-categories`, `/services` | 3 | planned |
| `/schedules`, `/availability` | 4 | planned |
| `/appointments` | 4 | planned |
| `/customers` | 5 | planned |
| `/booking-forms` | 5 | planned |
| `/upi-accounts`, `/payments`, `/admin/payments` | 6 | planned |
| `/refunds`, `/bank-statements` | 7 | planned |
| `/notifications` | 8 | planned |
| `/integrations` | 9, 11 | planned |
| `/webhooks` | 11 | planned |
| `/reports`, `/admin` | 10 | planned |
| `/platform` | 10 | planned |

This file is updated at the end of every phase with the concrete endpoints delivered.
