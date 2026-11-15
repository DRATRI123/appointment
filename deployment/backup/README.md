# Backups

Backups are made by the app itself (`backend/app/ops/backup.py`), so they are the same on a PC and on a server:
database + uploaded files, AES-256-GCM encrypted with `BACKUP_ENCRYPTION_KEY`, verified after writing, pruned (7
daily, 4 weekly, 6 monthly), optionally copied to an S3-compatible bucket.

On a server:

| Task | Command |
|---|---|
| automatic daily backup | the `backup` container (`BACKUP_AT`, default 02:30 India time) |
| back up now | `deployment/scripts/backup.sh` |
| list | `deployment/scripts/backup.sh list` |
| copy out of Docker | `deployment/scripts/backup.sh copy /home/deploy/backups` |
| restore (typed confirmation, safety backup first) | `deployment/scripts/restore.sh <file>` |

deploy.sh also backs up before every release that changes the database. Full guide: `docs/backup-restore.md`.
