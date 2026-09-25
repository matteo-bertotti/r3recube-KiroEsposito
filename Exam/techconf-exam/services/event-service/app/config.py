import os

# PORT is mandatory; fails fast with a clear message if absent or out of range
_raw_port = os.environ.get("PORT")
if _raw_port is None:
    raise KeyError(
        "Environment variable PORT is required but not set. "
        "Please set PORT to an integer in the range 1–65535."
    )
try:
    PORT = int(_raw_port)
except ValueError:
    raise ValueError(
        f"Environment variable PORT must be an integer, got: {_raw_port!r}"
    )
if not (1 <= PORT <= 65535):
    raise ValueError(
        f"Environment variable PORT must be in range 1–65535, got: {PORT}"
    )

USER_SERVICE_URL = os.environ.get("USER_SERVICE_URL", "http://localhost:5001")
STORAGE_BACKEND  = os.environ.get("STORAGE_BACKEND", "memory")
DATA_DIR         = os.environ.get("DATA_DIR", "./data")

# Fixed constant — never read from environment (platform-standards.md)
USER_SERVICE_TIMEOUT = 2  # seconds
