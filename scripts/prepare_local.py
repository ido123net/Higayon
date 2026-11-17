"""Create private local deployment configuration from the development environment."""

import os
import secrets
from collections.abc import Mapping
from pathlib import Path


def prepare(directory: Path, source: Mapping[str, str]) -> None:
    required = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "OWNER_EMAIL", "ALLOWED_EMAILS")
    values = {key: source.get(key, "") for key in required}
    if any(not value or value.startswith("replace-") for value in values.values()):
        raise ValueError("Configure Google credentials, OWNER_EMAIL and ALLOWED_EMAILS first.")
    if any("\n" in value or "\r" in value for value in values.values()):
        raise ValueError("Deployment environment values must not contain newlines.")
    allowed = {email.strip().lower() for email in values["ALLOWED_EMAILS"].split(",")}
    if values["OWNER_EMAIL"].strip().lower() not in allowed:
        raise ValueError("OWNER_EMAIL must also appear in ALLOWED_EMAILS.")
    if directory.is_symlink():
        raise ValueError("The private configuration directory must not be a symlink.")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    filenames = ("app.env", "db.env", "tunnel.env")
    if any((directory / name).exists() or (directory / name).is_symlink() for name in filenames):
        raise FileExistsError(
            "Local deployment files already exist; edit them without regenerating."
        )

    password = secrets.token_urlsafe(32)
    db = {"POSTGRES_DB": "higayon", "POSTGRES_USER": "higayon", "POSTGRES_PASSWORD": password}
    app = {
        **values,
        "DEBUG": "false",
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
        "OWNER_API_TOKEN": secrets.token_urlsafe(48),
        "DATABASE_URL": f"postgresql://higayon:{password}@db:5432/higayon",
        "ALLOWED_HOSTS": "higayon.idofrenkel.com,localhost,127.0.0.1",
        "CSRF_TRUSTED_ORIGINS": "https://higayon.idofrenkel.com",
        "TRUST_PROXY": "true",
    }
    created = []
    try:
        for name, environment in zip(filenames, (app, db, {"TUNNEL_TOKEN": ""}), strict=True):
            target = directory / name
            with open(target, "x", opener=lambda p, flags: os.open(p, flags, 0o600)) as stream:
                created.append(target)
                stream.write("".join(f"{key}={value}\n" for key, value in environment.items()))
    except BaseException:
        for target in created:
            target.unlink()
        raise


if __name__ == "__main__":
    prepare(Path(__file__).resolve().parent.parent / ".local", os.environ)
    print("Created private .local/app.env, db.env and tunnel.env; no secret values printed.")
