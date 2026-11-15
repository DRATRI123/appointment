# Deployment documentation

All documentation lives in `docs/` at the repository root. For deploying:

| Read | When |
|---|---|
| `docs/production-deployment.md` | preparing the VPS and every deploy, update and rollback |
| `docs/environment-configuration.md` | what goes in `.env` and what the app refuses |
| `docs/superadmin-setup.md` | creating and recovering the super admin |
| `docs/backup-restore.md` | backups, restore, a new server after a disaster |
| `docs/database-migrations.md` | how schema changes are applied safely |
| `docs/security.md`, `docs/encryption.md` | the protections and the keys |
| `docs/security-testing-report.md` | what was tested and the remaining risks |
| `docs/troubleshooting.md` | something is wrong |

The folders next to this one: `docker/` (Dockerfiles), `nginx/` (proxy configuration, baked into the Nginx image),
`scripts/` (setup-server, deploy, update, rollback, backup, restore, health-check), `monitoring/` (Prometheus and
alert rules), `backup/`.
