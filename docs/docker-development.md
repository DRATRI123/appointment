# Docker development and tests

Docker is optional on your PC (`START-APP.bat` needs none). Use it to work against PostgreSQL exactly like production,
or to run the tests in a clean, isolated container.

## Files

| File | Used for |
|---|---|
| `compose.yaml` | what every environment shares (API, worker, migrate, website, PostgreSQL) and the hardening of every container |
| `compose.dev.yaml` | development: hot reload, local PostgreSQL, ports only on 127.0.0.1 |
| `compose.test.yaml` | the test suite against a throw-away in-memory PostgreSQL, no internet |
| `compose.production.yaml` | staging and production: Nginx + HTTPS, Redis, backups, resource limits ([production-deployment.md](production-deployment.md)) |
| `deployment/docker/Dockerfile.backend` | API/worker image: `runtime` (servers) and `dev` (tools + reload) targets |
| `deployment/docker/Dockerfile.frontend` | website image: `runtime` (standalone server) and `dev` (`next dev`) targets |
| `deployment/docker/Dockerfile.nginx` | Nginx with this release's configuration |

Each environment has its own project name (`appointment-dev`, `appointment-test`, `appointment`), so their data
volumes can never mix.

## Development stack

```bash
docker compose -f compose.yaml -f compose.dev.yaml up --build
```

* Website http://localhost:3000, API http://localhost:8000/docs, PostgreSQL on `localhost:5433` (user `app`,
  password `dev-only-password`; servers refuse such values).
* Saving a file in `backend/` or `frontend/` reloads that service. Polling is on, so this works on Windows too.
* Messages are printed in the logs (`docker compose -f compose.yaml -f compose.dev.yaml logs -f api`), never sent.
* On Linux, if your user id is not 1000, start with your own ids so the website can write into your folder:
  `DEV_UID=$(id -u) DEV_GID=$(id -g) docker compose -f compose.yaml -f compose.dev.yaml up`.

Stop with `Ctrl+C`. Add `down -v` to delete the development database as well.

## Tests in Docker

```bash
docker compose -f compose.yaml -f compose.test.yaml run --rm backend-tests
```

```bash
docker compose -f compose.yaml -f compose.test.yaml down -v
```

This runs, in order:
1. lint (`ruff`);
2. every migration on an empty PostgreSQL;
3. a check that the migrations match the code (`alembic check`);
4. the whole backend suite.

The project is mounted **read-only**, so tests cannot change your files. The container has **no internet access**, so
no real message, payment or webhook can leave. Measured: 351 passed, 2 skipped.

## How the containers are hardened (all environments)

* Non-root users everywhere; every Linux capability dropped; `no-new-privileges`.
* Read-only filesystems on servers, with only `/tmp` and data volumes writable.
* No Docker socket inside any container. No secrets inside any image: they arrive from `.env` at run time.
* PostgreSQL and Redis sit on an `internal` network with no route to the internet and no published ports.
* Exact versions: Python packages from `requirements.lock` (hash-checked), npm from `package-lock.json`, and every base
  image pinned to a patch version.
* Final images contain no compilers, no pip, no npm and no tests. The application code is owned by root, so the app
  user cannot modify it.

## Building behind a proxy that inspects TLS

Pass its certificate bundle as a build secret. It is used only during the build and never stored in an image:

```bash
docker build --secret id=extra_ca,src=corp-ca.pem -f deployment/docker/Dockerfile.backend backend
```

`INSTALL_PG_CLIENT=false` / `OS_UPGRADE=false` skip the Debian/Alpine package steps for test builds where those
mirrors are unreachable. Never use them for a server image: backups need `pg_dump`, and security updates matter.
