# Backup and Restore

## Backup

Run the backup command:

```bash
python manage.py backup
```

Or with dry-run (no upload, no rotation):

```bash
python manage.py backup --dry-run
```

## Restore

### Database (PostgreSQL)

```bash
# Decrypt and decompress
gpg --batch --pinentry-mode loopback --passphrase "$BACKUP_ENCRYPTION_PASSPHRASE" --decrypt smartline_db_<stamp>.sql.gz.gpg | gunzip > dump.sql

# Restore
psql -h <host> -p <port> -U <user> -d <db> < dump.sql
```

### Database (SQLite)

```bash
gpg --batch --pinentry-mode loopback --passphrase "$BACKUP_ENCRYPTION_PASSPHRASE" --decrypt smartline_db_<stamp>.sqlite.gz.gpg | gunzip > db.sqlite3
```

### Git Repository

```bash
git clone smartline_repo_<stamp>.bundle restored_repo
cd restored_repo
git checkout main
```