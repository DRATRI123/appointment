# File storage: this server or S3-compatible (AWS S3, Cloudflare R2, MinIO …)

Uploaded files: logos and website images (public), patient documents, payment screenshots and refund proofs (private).
Private files are AES-256-GCM encrypted by the app **before** they reach the disk or the bucket, so the bucket only ever
holds ciphertext. The bucket stays private: nothing is ever public or permanently linked. Patient documents open only
through the app, after a permission check, with a link that works 60 seconds. The database stores each file's key,
size, type and checksum; the file content is in the storage.

## Set up a bucket

| Provider | Endpoint URL | Region |
|---|---|---|
| AWS S3 | (empty) | e.g. `ap-south-1` |
| Cloudflare R2 | `https://<account id>.r2.cloudflarestorage.com` | `auto` |
| Backblaze B2 | `https://s3.<region>.backblazeb2.com` | the bucket region |
| DigitalOcean Spaces | `https://<region>.digitaloceanspaces.com` | e.g. `blr1` |
| MinIO (self-hosted) | e.g. `http://minio:9000` | any |

Create a **private** bucket and an access key limited to that bucket (read, write, delete, list).

Super admin → Integrations → **File storage**: bucket, region, endpoint, optional folder, access key, secret → Save →
**Test connection** (writes, reads back and deletes a small file). Or `.env`: `S3_BUCKET`, `S3_REGION`,
`S3_ENDPOINT_URL`, `S3_PREFIX`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`.

## Move files and switch

**Move files to the bucket and switch** (needs a passed test):

1. The worker copies every file byte for byte, reads each copy back and compares checksums. Progress shows on screen.
2. Only when all files match does the app switch. Nothing is deleted from this server.
3. For a while, a file missing in the bucket is read from the old storage, and a second pass copies late uploads.
4. **Finish** stops reading from the old storage. Delete the old files yourself when you are sure.

It works in 2-minute slices so reminders and messages keep going. If a copy fails, nothing switches; press again to
continue (verified files are skipped). The same button moves files back to this server.

**Show usage**: files and bytes in the active storage.

## Backups

Off-site backup copy: Super admin → Integrations → **Off-site backup copy** (bucket and folder; uses the same keys).
See [../backup-restore.md](../backup-restore.md). Retention of patient documents: Admin → Settings → Privacy.
