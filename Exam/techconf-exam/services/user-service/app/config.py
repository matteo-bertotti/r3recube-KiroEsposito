"""
Configuration module — single point of environment variable reading for user-service.

All other modules in app/ import constants from here; they never call os.environ
directly. This ensures configuration is resolved once at startup and is easy to audit.
"""

import os

# PORT is mandatory — KeyError with the variable name is raised if absent,
# which is descriptive enough to diagnose the problem immediately.
PORT: int = int(os.environ["PORT"])

# STORAGE_BACKEND selects the persistence layer: memory | json | sqlite
STORAGE_BACKEND: str = os.environ.get("STORAGE_BACKEND", "memory")

# DATA_DIR is the directory where json/sqlite backends store their files.
DATA_DIR: str = os.environ.get("DATA_DIR", "./data")
