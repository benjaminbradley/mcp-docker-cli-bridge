"""Pytest configuration — workaround for Docker file bind mount inode issue.

Problem: Docker file bind mounts are inode-based. When the host editor replaces
a file with a new inode (atomic write), the container continues to see the old
inode. This makes the container's /bridge/server.py stale after edits.

Short-term fix: load server from /bridge/tests/server.py, which is a directory
bind mount and always reflects the latest content. Keep tests/server.py in sync
with server.py when editing.

Long-term fix: update docker-compose.yml to use a directory mount for server.py
(add `- .:/workspace` volume and PYTHONPATH=/workspace env var), then
`make down && make up`. After that, this conftest can be simplified or removed.
"""

import importlib.util
import sys
from pathlib import Path

_tests_server = Path("/bridge/tests/server.py")

if _tests_server.exists():
    # Load the fresh copy from the directory-mounted tests/ path.
    _spec = importlib.util.spec_from_file_location("server", str(_tests_server))
    _module = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
    _spec.loader.exec_module(_module)  # type: ignore[union-attr]
    sys.modules["server"] = _module
