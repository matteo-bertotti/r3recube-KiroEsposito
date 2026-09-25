"""
Repository factory for user-service.

This is the **single backend-selection point** in the codebase (REQ-USR-08).
All other modules reference only ``UserRepository`` (the ABC); the concrete
class is chosen here and injected into ``UserService`` once at startup.

Usage (in ``app/__main__.py``)::

    from app.repository import get_repository
    repo = get_repository(STORAGE_BACKEND, DATA_DIR)
    service = UserService(repo)
"""

from app.repository.base import UserRepository
from app.repository.memory import MemoryUserRepository
from app.repository.json_repo import JsonUserRepository
from app.repository.sqlite_repo import SqliteUserRepository


def get_repository(backend: str, data_dir: str) -> UserRepository:
    """
    Return the appropriate ``UserRepository`` implementation.

    Args:
        backend:  One of ``"json"``, ``"sqlite"``, or any other value
                  (including ``"memory"`` or an empty string) which
                  falls back to the in-memory backend.
        data_dir: Filesystem path used by the file-based backends
                  (``json`` and ``sqlite``).  Ignored for ``memory``.

    Returns:
        A fully initialised ``UserRepository`` instance ready for use.

    REQ-USR-08: the switch must not require any modification to
    domain or API code.
    """
    if backend == "json":
        return JsonUserRepository(data_dir)
    if backend == "sqlite":
        return SqliteUserRepository(data_dir)
    return MemoryUserRepository()


__all__ = [
    "get_repository",
    "UserRepository",
    "MemoryUserRepository",
    "JsonUserRepository",
    "SqliteUserRepository",
]
