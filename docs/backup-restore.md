# Backups and restore

## What is backed up, and how

One file per backup: the PostgreSQL dump (or a consistent SQLite copy on a PC), every uploaded file (logos, payment
screenshots, patient documents) and a manifest with SHA-256 checksums, row counts and the schema revision.

* **Encrypted** with `BACKUP_ENCRYPTION_KEY` (AES-256-GCM in authenticated 1 MiB chunks). A damaged, cut-off or altered
  file is rejected, never half-restored. Keep the key off the server: without it, nobody can read the backup.
* **Verified** right after writing (decrypted, checksums compared, database readable).
* **Pruned:** the newest of each of the last 7 days, 4 weeks and 6 months are kept (`BACKUP_KEEP_*`).
* **Off-site** when `BACKUP_S3_BUCKET` is set: do set it, with versioning or object lock on the bucket, so a lost
  or compromised server cannot take the backups with it.
* **Daily** at `BACKUP_AT` (02:30 India time by default) by the `backup` container. **Also before every deploy**
  that applies migrations, and a baseline after the first deploy.

The result of every run is shown on Super admin → System health. The `BackupMissing` alert and `health-check.sh`
report when there has been no good backup for 26 hours.

## On a server

| Task | Command |
|---|---|
| Back up now | `deployment/scripts/backup.sh` |
| List backups | `deployment/scripts/backup.sh list` |
| Copy the newest out of Docker | `deployment/scripts/backup.sh copy /home/deploy/backups` (then move it off the server) |
| Restore | `deployment/scripts/restore.sh backup-20261115-023000.tar.gz.enc` |

To fetch a copy to Windows (PowerShell):

```powershell
scp deploy@<server-ip>:/home/deploy/backups/backup-20261115-023000.tar.gz.enc .
```

### Restore

`restore.sh` replaces **all** current data with the backup. In order:

1. Verifies the backup can be read (checksums, encryption, database).
2. Asks you to type the site's domain (or `--confirm <domain>` for a scripted drill). Anything else stops it with
   nothing changed.
3. Stops the website, API, worker and scheduled backups.
4. Takes a **safety backup of the current data**, so even a restore can be undone.
5. Restores the database and uploads. The previous uploads folder is kept as `uploads.before-restore-<time>`.
6. Starts everything. `migrate` brings the schema up to the current release; then it runs the health check.

Patients cannot book for those few minutes.

**Rehearsed:** a backup was taken, a new account was added, then the backup was restored. The account disappeared
and the earlier data was back, with the safety backup written first.

### Restore on a new server (the server is gone)

1. Prepare the new server and clone the code ([production-deployment.md](production-deployment.md) §2).
2. Put your saved `.env` in place (from your password manager), or at least the same `DATA_ENCRYPTION_KEY`,
   `BACKUP_ENCRYPTION_KEY` and `SECRET_KEY`. Then run `deployment/scripts/deploy.sh`.
3. Copy the backup onto the server, then run `deployment/scripts/restore.sh /path/to/backup-....tar.gz.enc`.

## On your PC (development)

From `backend\` with the virtual environment active:

```powershell
python -m app.ops.backup create
```

```powershell
python -m app.ops.backup list
```

Restore only with the API and worker stopped:

```powershell
python -m app.ops.backup restore <file> --yes
```

Super admin → Database also snapshots the SQLite file automatically before it moves data to PostgreSQL.

## Practise

A backup you have never restored is a hope, not a backup. Once a month, restore the latest backup on a spare server
or a staging server, and check a few recent appointments and payments.
