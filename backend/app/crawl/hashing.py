"""Salted author identifiers; raw author IDs must never be persisted."""

import hashlib
import os
from pathlib import Path
import re
import secrets
import tempfile
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
                salt = path.read_text(encoding="utf-8")
            except FileNotFoundError:
                fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as salt_file:
                        os.fchmod(salt_file.fileno(), 0o600)
                        salt_file.write(secrets.token_hex(32))
                        salt_file.flush()
                        os.fsync(salt_file.fileno())
                    try:
                        os.link(tmp, path)
                    except FileExistsError:
                        pass  # Another process published a complete salt first.
                finally:
                    os.unlink(tmp)
                salt = path.read_text(encoding="utf-8")
            salt = salt.strip()
            if re.fullmatch(r"[0-9a-fA-F]{64}", salt) is None:
                raise ValueError(f"Invalid author salt at {path}: expected 64 hexadecimal characters")
            _salts[path] = salt
        return _salts[path]


def author_hash(source: str, raw_id: str) -> str:
    """Return sha256(salt + source + raw_id) as 16 lowercase hex characters."""
    return hashlib.sha256((_read_salt() + source + raw_id).encode("utf-8")).hexdigest()[:16]
