"""Salted author identifiers; raw author IDs must never be persisted."""

import hashlib
import os
from pathlib import Path
import secrets
from threading import Lock

from app.config import settings


_salts: dict[Path, str] = {}
_salt_lock = Lock()


def _read_salt() -> str:
    path = Path(settings.author_salt_path).resolve()
    with _salt_lock:
        if path not in _salts:
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                salt = path.read_text(encoding="utf-8")
            else:
                with os.fdopen(fd, "w", encoding="utf-8") as salt_file:
                    os.chmod(path, 0o600)
                    salt = secrets.token_hex(32)
                    salt_file.write(salt)
            _salts[path] = salt
        return _salts[path]


def author_hash(source: str, raw_id: str) -> str:
    """Return sha256(salt + source + raw_id) as 16 lowercase hex characters."""
    return hashlib.sha256((_read_salt() + source + raw_id).encode("utf-8")).hexdigest()[:16]
