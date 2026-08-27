"""Backup database and git repository to Yandex Disk with GPG encryption."""
import gzip
import logging
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Create encrypted backup of database and git repository to Yandex Disk."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Perform all steps except actual upload to Yandex Disk and rotation.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        # Read settings
        yandex_token = getattr(settings, "YANDEX_DISK_TOKEN", None)
        yandex_backup_dir = getattr(settings, "YANDEX_DISK_BACKUP_DIR", "/Smartline/backups")
        encryption_passphrase = getattr(settings, "BACKUP_ENCRYPTION_PASSPHRASE", None)

        if not yandex_token:
            raise CommandError("YANDEX_DISK_TOKEN is not configured in settings")
        if not encryption_passphrase:
            raise CommandError("BACKUP_ENCRYPTION_PASSPHRASE is not configured in settings")

        db_config = settings.DATABASES["default"]
        db_engine = db_config.get("ENGINE", "")

        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # 1. Database dump
            db_dump_path = self._create_db_dump(db_config, db_engine, timestamp, tmp_path)
            logger.info("Created database dump: %s", db_dump_path.name)

            # 2. GPG encryption
            encrypted_path = self._encrypt_file(db_dump_path, encryption_passphrase, tmp_path)
            logger.info("Encrypted database dump: %s", encrypted_path.name)

            # 3. Git bundle (best-effort: skipped if no git repo, e.g. production image)
            repo_bundle_path = self._create_git_bundle(timestamp, tmp_path)
            if repo_bundle_path is None:
                logger.warning("Git bundle skipped (no git repository or bundle failed).")
            else:
                logger.info("Created git bundle: %s", repo_bundle_path.name)

            # 4. Upload to Yandex Disk (skip in dry-run)
            if not dry_run:
                self._upload_to_yandex_disk(
                    yandex_token,
                    yandex_backup_dir,
                    encrypted_path,
                    repo_bundle_path,
                )
                logger.info("Uploaded backup files to Yandex Disk")

                # 5. Rotation
                self._rotate_backups(yandex_token, yandex_backup_dir)
            else:
                extra = f" and {repo_bundle_path.name}" if repo_bundle_path is not None else ""
                logger.info(
                    "DRY-RUN: Would upload %s%s to %s",
                    encrypted_path.name,
                    extra,
                    yandex_backup_dir,
                )
                logger.info("DRY-RUN: Would rotate old backups in %s", yandex_backup_dir)

        self.stdout.write(self.style.SUCCESS("Backup completed successfully"))

    def _create_db_dump(self, db_config, db_engine, timestamp, tmp_path):
        """Create database dump (PostgreSQL or SQLite) and gzip it."""
        if db_engine == "django.db.backends.postgresql":
            dump_file = tmp_path / f"smartline_db_{timestamp}.sql"
            gz_file = tmp_path / f"smartline_db_{timestamp}.sql.gz"

            host = db_config.get("HOST", "localhost")
            port = db_config.get("PORT", "5432")
            user = db_config.get("USER", "postgres")
            db_name = db_config.get("NAME", "postgres")
            password = db_config.get("PASSWORD", "")

            env = {**os.environ, "PGPASSWORD": password}
            cmd = [
                "pg_dump",
                "-h", host,
                "-p", str(port),
                "-U", user,
                "-d", db_name,
                "-F", "p",  # plain text format
                "-f", str(dump_file),
            ]
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if result.returncode != 0:
                raise CommandError(f"pg_dump failed: {result.stderr}")

            # gzip the dump
            with open(dump_file, "rb") as f_in:
                with gzip.open(gz_file, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            dump_file.unlink()
            return gz_file

        elif db_engine == "django.db.backends.sqlite3":
            db_file = Path(db_config.get("NAME", "db.sqlite3"))
            gz_file = tmp_path / f"smartline_db_{timestamp}.sqlite.gz"

            if not db_file.exists():
                raise CommandError(f"SQLite database file not found: {db_file}")

            with open(db_file, "rb") as f_in:
                with gzip.open(gz_file, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            return gz_file

        else:
            raise CommandError(f"Unsupported database engine: {db_engine}")

    def _encrypt_file(self, input_path, passphrase, tmp_path):
        """Encrypt file using GPG symmetric encryption (AES256)."""
        output_path = tmp_path / f"{input_path.name}.gpg"

        cmd = [
            "gpg",
            "--batch",
            "--symmetric",
            "--pinentry-mode", "loopback",
            "--passphrase", passphrase,
            "--cipher-algo", "AES256",
            "--yes",
            "-o", str(output_path),
            str(input_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise CommandError(f"GPG encryption failed: {result.stderr}")

        return output_path

    def _create_git_bundle(self, timestamp, tmp_path):
        """Create git bundle of the entire repository (best-effort).

        Returns the bundle path, or None if no git repository is available
        (e.g. production Docker image without .git) or bundling fails.
        """
        # commands -> management -> core -> root
        repo_root = Path(__file__).resolve().parents[3]
        bundle_path = tmp_path / f"smartline_repo_{timestamp}.bundle"

        # Skip if there is no git repository (common in production images)
        if not (repo_root / ".git").is_dir():
            logger.warning(
                "Git repository not found at %s; skipping git bundle.", repo_root
            )
            return None

        cmd = ["git", "-C", str(repo_root), "bundle", "create", str(bundle_path), "--all"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning("Git bundle creation failed: %s", result.stderr)
            return None

        return bundle_path

    def _upload_to_yandex_disk(self, token, backup_dir, db_file, repo_bundle):
        """Upload backup files to Yandex Disk."""
        import yadisk

        client = yadisk.Client(token=token)
        try:
            # Create backup directory if it doesn't exist
            if not client.exists(backup_dir):
                client.mkdir(backup_dir)

            # Upload database dump
            db_remote_path = f"{backup_dir.rstrip('/')}/{db_file.name}"
            client.upload(str(db_file), db_remote_path)

            # Upload git bundle (only if it was created)
            if repo_bundle is not None:
                bundle_remote_path = f"{backup_dir.rstrip('/')}/{repo_bundle.name}"
                client.upload(str(repo_bundle), bundle_remote_path)
        finally:
            client.close()

    def _rotate_backups(self, token, backup_dir):
        """Keep only the 14 most recent backups for each prefix."""
        import yadisk

        client = yadisk.Client(token=token)
        try:
            # Get list of files in backup directory
            items = list(client.listdir(backup_dir))

            # Group by prefix
            db_files = []
            repo_files = []

            for item in items:
                name = getattr(item, "name", "")
                if name.startswith("smartline_db_") and name.endswith(".gpg"):
                    db_files.append((name, getattr(item, "path", "")))
                elif name.startswith("smartline_repo_") and name.endswith(".bundle"):
                    repo_files.append((name, getattr(item, "path", "")))

            # Sort by name (timestamp) descending - newest first
            db_files.sort(key=lambda x: x[0], reverse=True)
            repo_files.sort(key=lambda x: x[0], reverse=True)

            # Remove old files (keep 14 most recent)
            for files, prefix in [(db_files, "smartline_db_"), (repo_files, "smartline_repo_")]:
                if len(files) > 14:
                    to_remove = files[14:]
                    for name, path in to_remove:
                        client.remove(path, permanently=True)
                        logger.info("Removed old backup: %s", name)

                    self.stdout.write(
                        f"Rotated {prefix}: removed {len(to_remove)} old backup(s)"
                    )
        finally:
            client.close()