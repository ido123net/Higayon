import tempfile
import unittest
from pathlib import Path

from scripts.prepare_local import prepare


class LocalDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "private"
        self.source = {
            "GOOGLE_CLIENT_ID": "client.apps.googleusercontent.com",
            "GOOGLE_CLIENT_SECRET": "secret-with-$-characters",
            "OWNER_EMAIL": "owner@example.com",
            "ALLOWED_EMAILS": "owner@example.com,friend@example.com",
        }

    def test_private_configuration_keeps_credentials_and_refuses_overwrite(self):
        prepare(self.directory, self.source)
        app_file = self.directory / "app.env"
        original = app_file.read_text()
        values = dict(line.split("=", 1) for line in original.splitlines())
        database = dict(
            line.split("=", 1) for line in (self.directory / "db.env").read_text().splitlines()
        )
        self.assertEqual(values["GOOGLE_CLIENT_SECRET"], self.source["GOOGLE_CLIENT_SECRET"])
        self.assertEqual(values["DEBUG"], "false")
        self.assertEqual(values["TRUST_PROXY"], "true")
        self.assertIn(database["POSTGRES_PASSWORD"], values["DATABASE_URL"])
        self.assertGreaterEqual(len(values["DJANGO_SECRET_KEY"]), 64)
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
        for filename in ("app.env", "db.env", "tunnel.env"):
            self.assertEqual((self.directory / filename).stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            prepare(self.directory, self.source)
        self.assertEqual(app_file.read_text(), original)

    def test_invalid_source_and_symlink_cannot_create_secret_files(self):
        for replacement in (
            {"GOOGLE_CLIENT_SECRET": ""},
            {"ALLOWED_EMAILS": "friend@example.com"},
            {"GOOGLE_CLIENT_SECRET": "secret\nDEBUG=true"},
        ):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                prepare(self.directory, {**self.source, **replacement})
            self.assertFalse(self.directory.exists())
        self.directory.symlink_to(Path(self.temporary.name), target_is_directory=True)
        with self.assertRaises(ValueError):
            prepare(self.directory, self.source)
