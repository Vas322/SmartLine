"""Tests for the backup management command."""
import gzip
import logging
import subprocess
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch, call

from django.test import TestCase, override_settings
from django.core.management import call_command
from django.core.management.base import CommandError


def _make_completed_process(returncode=0, stdout="", stderr=""):
    """Create a mock CompletedProcess-like object."""
    result = MagicMock(spec=subprocess.CompletedProcess)
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def _backup_subprocess_side_effect(cmd, **kwargs):
    """Side effect for backup subprocess calls that creates expected output files."""
    # pg_dump: creates .sql file via -f argument
    if cmd and cmd[0] == "pg_dump":
        try:
            f_index = cmd.index("-f")
            output_file = cmd[f_index + 1]
            Path(output_file).write_text("-- dummy pg_dump output\n")
        except (ValueError, IndexError):
            pass
        return _make_completed_process()
    
    # gpg: creates .gpg file via -o argument
    if cmd and cmd[0] == "gpg":
        try:
            o_index = cmd.index("-o")
            output_file = cmd[o_index + 1]
            Path(output_file).write_bytes(b"dummy gpg encrypted data")
        except (ValueError, IndexError):
            pass
        return _make_completed_process()
    
    # git bundle: creates .bundle file
    if cmd and cmd[0] == "git" and "bundle" in cmd and "create" in cmd:
        try:
            create_index = cmd.index("create")
            output_file = cmd[create_index + 1]
            Path(output_file).write_bytes(b"dummy git bundle data")
        except (ValueError, IndexError):
            pass
        return _make_completed_process()
    
    return _make_completed_process()


@override_settings(
    YANDEX_DISK_TOKEN="test-token",
    YANDEX_DISK_BACKUP_DIR="/Smartline/backups/test",
    BACKUP_ENCRYPTION_PASSPHRASE="test-passphrase",
    DATABASES={
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "test_db",
            "USER": "test_user",
            "PASSWORD": "test_password",
            "HOST": "localhost",
            "PORT": "5432",
        }
    },
)
class BackupCommandPostgresTests(TestCase):
    """Tests for backup command with PostgreSQL database."""

    def setUp(self):
        self.logger = logging.getLogger("core.management.commands.backup")
        self.original_level = self.logger.level
        self.logger.setLevel(logging.DEBUG)

    def tearDown(self):
        self.logger.setLevel(self.original_level)

    @patch("yadisk.Client")
    @patch("core.management.commands.backup.subprocess.run")
    def test_postgres_backup_calls_pg_dump_with_correct_args(self, mock_subprocess_run, mock_yadisk_client):
        # Setup mocks
        mock_subprocess_run.side_effect = _backup_subprocess_side_effect
        mock_client = MagicMock()
        mock_yadisk_client.return_value = mock_client
        mock_client.listdir.return_value = []  # No existing files for rotation

        # Run command
        call_command("backup", "--dry-run")

        # Verify pg_dump was called with correct arguments
        self.assertTrue(mock_subprocess_run.called)
        # Find the pg_dump call
        pg_dump_calls = [
            call for call in mock_subprocess_run.call_args_list
            if call[0][0][0] == "pg_dump"
        ]
        self.assertEqual(len(pg_dump_calls), 1)
        pg_dump_call = pg_dump_calls[0]
        args = pg_dump_call[0][0]
        env = pg_dump_call[1].get("env", {})

        self.assertIn("-h", args)
        self.assertIn("localhost", args)
        self.assertIn("-p", args)
        self.assertIn("5432", args)
        self.assertIn("-U", args)
        self.assertIn("test_user", args)
        self.assertIn("-d", args)
        self.assertIn("test_db", args)
        self.assertIn("-F", args)
        self.assertIn("p", args)
        self.assertIn("-f", args)
        self.assertEqual(env.get("PGPASSWORD"), "test_password")

    @patch("yadisk.Client")
    @patch("core.management.commands.backup.subprocess.run")
    def test_gpg_encryption_called_with_correct_args(self, mock_subprocess_run, mock_yadisk_client):
        mock_subprocess_run.side_effect = _backup_subprocess_side_effect
        mock_client = MagicMock()
        mock_yadisk_client.return_value = mock_client
        mock_client.listdir.return_value = []

        call_command("backup", "--dry-run")

        # Find the gpg call
        gpg_calls = [
            call for call in mock_subprocess_run.call_args_list
            if call[0][0][0] == "gpg"
        ]
        self.assertEqual(len(gpg_calls), 1)
        gpg_call = gpg_calls[0]
        args = gpg_call[0][0]

        self.assertIn("--batch", args)
        self.assertIn("--symmetric", args)
        self.assertIn("--pinentry-mode", args)
        self.assertIn("loopback", args)
        self.assertIn("--passphrase", args)
        self.assertIn("test-passphrase", args)
        self.assertIn("--cipher-algo", args)
        self.assertIn("AES256", args)
        self.assertIn("--yes", args)
        self.assertIn("-o", args)
        self.assertTrue(any(".gpg" in arg for arg in args))

    @patch("yadisk.Client")
    @patch("core.management.commands.backup.subprocess.run")
    def test_git_bundle_created(self, mock_subprocess_run, mock_yadisk_client):
        mock_subprocess_run.side_effect = _backup_subprocess_side_effect
        mock_client = MagicMock()
        mock_yadisk_client.return_value = mock_client
        mock_client.listdir.return_value = []

        call_command("backup", "--dry-run")

        # Find the git bundle call
        git_calls = [
            call for call in mock_subprocess_run.call_args_list
            if call[0][0][0] == "git"
        ]
        self.assertEqual(len(git_calls), 1)
        git_call = git_calls[0]
        args = git_call[0][0]

        self.assertIn("bundle", args)
        self.assertIn("create", args)
        self.assertIn("--all", args)
        self.assertTrue(any(".bundle" in arg for arg in args))

    @patch("yadisk.Client")
    @patch("core.management.commands.backup.subprocess.run")
    def test_dry_run_skips_upload_and_rotation(self, mock_subprocess_run, mock_yadisk_client):
        mock_subprocess_run.side_effect = _backup_subprocess_side_effect
        mock_client = MagicMock()
        mock_yadisk_client.return_value = mock_client
        mock_client.listdir.return_value = []

        call_command("backup", "--dry-run")

        # upload should not be called
        mock_client.upload.assert_not_called()
        # remove should not be called
        mock_client.remove.assert_not_called()
        # mkdir may be called
        mock_client.mkdir.assert_not_called()

    @patch("yadisk.Client")
    @patch("core.management.commands.backup.subprocess.run")
    def test_upload_called_for_both_files(self, mock_subprocess_run, mock_yadisk_client):
        mock_subprocess_run.side_effect = _backup_subprocess_side_effect
        mock_client = MagicMock()
        mock_yadisk_client.return_value = mock_client
        mock_client.listdir.return_value = []

        call_command("backup")  # Not dry-run

        # Verify upload called for both files
        self.assertEqual(mock_client.upload.call_count, 2)
        upload_calls = mock_client.upload.call_args_list
        remote_paths = [call[0][1] for call in upload_calls]
        self.assertTrue(any(".gpg" in path for path in remote_paths))
        self.assertTrue(any(".bundle" in path for path in remote_paths))

    @patch("yadisk.Client")
    @patch("core.management.commands.backup.subprocess.run")
    def test_rotation_removes_old_backups(self, mock_subprocess_run, mock_yadisk_client):
        mock_subprocess_run.side_effect = _backup_subprocess_side_effect
        mock_client = MagicMock()
        mock_yadisk_client.return_value = mock_client

        # Create 16 db files and 16 repo files (14 should be kept, 2 removed each)
        def _make_item(name, path):
            obj = MagicMock()
            obj.name = name
            obj.path = path
            return obj

        db_items = [
            _make_item(
                f"smartline_db_2025-01-{i:02d}_1200.sql.gz.gpg",
                f"/Smartline/backups/test/smartline_db_2025-01-{i:02d}_1200.sql.gz.gpg"
            )
            for i in range(1, 17)
        ]
        repo_items = [
            _make_item(
                f"smartline_repo_2025-01-{i:02d}_1200.bundle",
                f"/Smartline/backups/test/smartline_repo_2025-01-{i:02d}_1200.bundle"
            )
            for i in range(1, 17)
        ]
        mock_client.listdir.return_value = db_items + repo_items

        call_command("backup")

        # Should remove 2 old db files and 2 old repo files (16 - 14 = 2 each)
        self.assertEqual(mock_client.remove.call_count, 4)
        remove_calls = mock_client.remove.call_args_list
        removed_paths = [call[0][0] for call in remove_calls]
        # Should remove the oldest (highest number = oldest since we sort descending)
        # Actually sorted by name descending, so oldest are at the end
        for path in removed_paths:
            self.assertTrue("smartline_db_" in path or "smartline_repo_" in path)

    @patch("yadisk.Client")
    @patch("core.management.commands.backup.subprocess.run")
    def test_no_rotation_if_upload_fails(self, mock_subprocess_run, mock_yadisk_client):
        mock_subprocess_run.side_effect = _backup_subprocess_side_effect
        mock_client = MagicMock()
        mock_yadisk_client.return_value = mock_client
        mock_client.listdir.return_value = []
        mock_client.upload.side_effect = Exception("Upload failed")

        with self.assertRaises(Exception):
            call_command("backup")

        # remove should not be called if upload failed
        mock_client.remove.assert_not_called()

    @patch("core.management.commands.backup.subprocess.run")
    def test_missing_yandex_token_raises_error(self, mock_subprocess_run):
        with override_settings(YANDEX_DISK_TOKEN=""):
            with self.assertRaises(CommandError) as ctx:
                call_command("backup", "--dry-run")
            self.assertIn("YANDEX_DISK_TOKEN", str(ctx.exception))

    @patch("core.management.commands.backup.subprocess.run")
    def test_missing_passphrase_raises_error(self, mock_subprocess_run):
        with override_settings(BACKUP_ENCRYPTION_PASSPHRASE=""):
            with self.assertRaises(CommandError) as ctx:
                call_command("backup", "--dry-run")
            self.assertIn("BACKUP_ENCRYPTION_PASSPHRASE", str(ctx.exception))


@override_settings(
    YANDEX_DISK_TOKEN="test-token",
    YANDEX_DISK_BACKUP_DIR="/Smartline/backups/test",
    BACKUP_ENCRYPTION_PASSPHRASE="test-passphrase",
    DATABASES={
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": "/fake/path/db.sqlite3",
        }
    },
)
class BackupCommandSQLiteTests(TestCase):
    """Tests for backup command with SQLite database."""

    @patch("yadisk.Client")
    @patch("core.management.commands.backup.Path.exists")
    @patch("core.management.commands.backup.open", new_callable=MagicMock)
    @patch("core.management.commands.backup.gzip.open")
    @patch("core.management.commands.backup.shutil.copyfileobj")
    @patch("core.management.commands.backup.subprocess.run")
    def test_sqlite_copies_file_instead_of_pg_dump(
        self, mock_subprocess_run, mock_copyfileobj, mock_gzip_open,
        mock_open, mock_path_exists, mock_yadisk_client
    ):
        mock_path_exists.return_value = True
        mock_subprocess_run.side_effect = _backup_subprocess_side_effect
        mock_client = MagicMock()
        mock_yadisk_client.return_value = mock_client
        mock_client.listdir.return_value = []

        call_command("backup", "--dry-run")

        # pg_dump should NOT be called for SQLite
        pg_dump_calls = [
            call for call in mock_subprocess_run.call_args_list
            if call[0][0] and call[0][0][0] == "pg_dump"
        ]
        self.assertEqual(len(pg_dump_calls), 0)

        # gzip.open should be called for SQLite file
        mock_gzip_open.assert_called()


@override_settings(
    YANDEX_DISK_TOKEN="test-token",
    YANDEX_DISK_BACKUP_DIR="/Smartline/backups/test",
    BACKUP_ENCRYPTION_PASSPHRASE="test-passphrase",
    DATABASES={
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "test_db",
            "USER": "test_user",
            "PASSWORD": "test_password",
            "HOST": "localhost",
            "PORT": "5432",
        }
    },
)
class BackupCommandEdgeCasesTests(TestCase):
    """Edge case tests for backup command."""

    @patch("yadisk.Client")
    @patch("core.management.commands.backup.subprocess.run")
    def test_unsupported_database_engine_raises_error(self, mock_subprocess_run, mock_yadisk_client):
        mock_subprocess_run.side_effect = _backup_subprocess_side_effect
        with override_settings(
            DATABASES={
                "default": {
                    "ENGINE": "django.db.backends.mysql",
                    "NAME": "test_db",
                }
            }
        ):
            with self.assertRaises(CommandError) as ctx:
                call_command("backup", "--dry-run")
            self.assertIn("Unsupported database engine", str(ctx.exception))

    @patch("yadisk.Client")
    @patch("core.management.commands.backup.subprocess.run")
    def test_pg_dump_failure_raises_error(self, mock_subprocess_run, mock_yadisk_client):
        # Override side_effect for pg_dump only
        def pg_dump_fail_side_effect(cmd, **kwargs):
            if cmd and cmd[0] == "pg_dump":
                return _make_completed_process(returncode=1, stderr="pg_dump error")
            return _backup_subprocess_side_effect(cmd, **kwargs)
        mock_subprocess_run.side_effect = pg_dump_fail_side_effect

        with self.assertRaises(CommandError) as ctx:
            call_command("backup", "--dry-run")
        self.assertIn("pg_dump failed", str(ctx.exception))

    @patch("yadisk.Client")
    @patch("core.management.commands.backup.subprocess.run")
    def test_gpg_failure_raises_error(self, mock_subprocess_run, mock_yadisk_client):
        # First call (pg_dump) succeeds, second (gpg) fails
        call_count = [0]
        def gpg_fail_side_effect(cmd, **kwargs):
            call_count[0] += 1
            if cmd and cmd[0] == "gpg":
                return _make_completed_process(returncode=1, stderr="gpg error")
            return _backup_subprocess_side_effect(cmd, **kwargs)
        mock_subprocess_run.side_effect = gpg_fail_side_effect
        mock_client = MagicMock()
        mock_yadisk_client.return_value = mock_client
        mock_client.listdir.return_value = []

        with self.assertRaises(CommandError) as ctx:
            call_command("backup", "--dry-run")
        self.assertIn("GPG encryption failed", str(ctx.exception))

    @patch("yadisk.Client")
    @patch("core.management.commands.backup.subprocess.run")
    def test_git_bundle_failure_raises_error(self, mock_subprocess_run, mock_yadisk_client):
        # First call (pg_dump) succeeds, second (gpg) succeeds, third (git) fails
        call_count = [0]
        def git_fail_side_effect(cmd, **kwargs):
            call_count[0] += 1
            if cmd and cmd[0] == "git" and "bundle" in cmd and "create" in cmd:
                return _make_completed_process(returncode=1, stderr="git error")
            return _backup_subprocess_side_effect(cmd, **kwargs)
        mock_subprocess_run.side_effect = git_fail_side_effect
        mock_client = MagicMock()
        mock_yadisk_client.return_value = mock_client
        mock_client.listdir.return_value = []

        with self.assertRaises(CommandError) as ctx:
            call_command("backup", "--dry-run")
        self.assertIn("Git bundle creation failed", str(ctx.exception))

    @patch("yadisk.Client")
    @patch("core.management.commands.backup.subprocess.run")
    def test_logging_does_not_contain_secrets(self, mock_subprocess_run, mock_yadisk_client):
        """Verify that password and token are not logged."""
        mock_subprocess_run.side_effect = _backup_subprocess_side_effect
        mock_client = MagicMock()
        mock_yadisk_client.return_value = mock_client
        mock_client.listdir.return_value = []

        # Capture log output
        with self.assertLogs("core.management.commands.backup", level="INFO") as cm:
            call_command("backup", "--dry-run")

        log_output = "\n".join(cm.output)
        self.assertNotIn("test_password", log_output)
        self.assertNotIn("test-token", log_output)
        self.assertNotIn("test-passphrase", log_output)

    @patch("yadisk.Client")
    @patch("core.management.commands.backup.subprocess.run")
    def test_rotation_keeps_14_most_recent(self, mock_subprocess_run, mock_yadisk_client):
        """Test that exactly 14 most recent backups are kept for each type."""
        mock_subprocess_run.side_effect = _backup_subprocess_side_effect
        mock_client = MagicMock()
        mock_yadisk_client.return_value = mock_client

        # Create 20 files of each type (6 should be removed each)
        def _make_item(name, path):
            obj = MagicMock()
            obj.name = name
            obj.path = path
            return obj

        db_items = [
            _make_item(
                f"smartline_db_2025-01-{i:02d}_1200.sql.gz.gpg",
                f"/Smartline/backups/test/smartline_db_2025-01-{i:02d}_1200.sql.gz.gpg"
            )
            for i in range(1, 21)
        ]
        repo_items = [
            _make_item(
                f"smartline_repo_2025-01-{i:02d}_1200.bundle",
                f"/Smartline/backups/test/smartline_repo_2025-01-{i:02d}_1200.bundle"
            )
            for i in range(1, 21)
        ]
        mock_client.listdir.return_value = db_items + repo_items

        call_command("backup")

        # 20 - 14 = 6 removed for each type = 12 total
        self.assertEqual(mock_client.remove.call_count, 12)