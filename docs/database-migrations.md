# Database migrations

Database changes ship as Alembic migrations in `backend/migrations/versions/`. The same files run on SQLite (your PC)
and PostgreSQL (servers). CI runs every migration on an empty database of each kind and fails if the models and the
migrations disagree (`alembic check`).

## Writing one (developers)

From `backend\`, virtual environment active:

```powershell
alembic revision --autogenerate -m "describe the change"
```

Read the generated file, then apply it locally:

```powershell
alembic upgrade head
```

Rules:
* **Add, don't remove** in the same release. Add the new column, ship code that uses it, and drop the old one in a
  later release, after a backup. New columns on big tables should allow NULL or have a server default.
* `render_as_batch=True` is on, so `ALTER TABLE` works on SQLite too.
* New indexes on large PostgreSQL tables: `CREATE INDEX CONCURRENTLY` (see the existing migrations).
* Write a working `downgrade()`. Drops belong there, not in `upgrade()`.

## The safety net on servers

`deploy.sh` runs `python -m app.ops.migration_check` before anything changes. It lists the pending migrations and
inspects each one's `upgrade()`. It flags anything that **removes or rewrites data**:
* `drop_table`;
* `drop_column`;
* `alter_column(..., type_=...)`;
* raw `DELETE` / `TRUNCATE` / `DROP` SQL.

| Situation | What deploy.sh does |
|---|---|
| nothing pending | continues |
| new, empty database | creates the schema |
| pending, additive only | takes a **verified backup**, then migrates |
| pending, flagged as removing data | takes the backup, then **stops and asks you to type `apply`** (or `--allow-destructive` after reading the migration) |
| a migration fails | the old containers keep running; `docker compose logs migrate` shows why |

A test (`test_migration_check.py`) also fails when a new migration's `upgrade()` is destructive, until its revision is
added to `REVIEWED_DESTRUCTIVE`. That forces a deliberate second look before it can reach a server. All shipped
migrations are additive.

The `migrate` container runs `python -m app.ops.setup`: `alembic upgrade head`, then it grants any new permissions
to the built-in roles. The API and worker start only after it succeeds.

## On your PC

`START-APP.bat` applies pending migrations every time it starts. Super admin → **Database** shows waiting updates
with an **Apply updates** button (saving pauses for a moment while they run).

## Rolling back

Prefer **fixing forward**: a new migration that undoes the change. `rollback.sh` switches code only, and refuses
when the schema has moved on since that release. To return to the exact earlier state, restore the backup that
deploy.sh took just before the migration ([backup-restore.md](backup-restore.md)). `alembic downgrade -1` is for
development.

## SQLite → PostgreSQL

From the browser: Super admin → **Database** → Move to PostgreSQL (copy, verify checksums, switch, undo). By hand,
and server details: [database.md](database.md#moving-existing-data-from-sqlite-to-postgresql).
