import sys

# Ensure /workspace/server.py (directory-mounted, always fresh) takes precedence
# over /bridge/server.py (Dockerfile-baked, stale). PYTHONPATH=/workspace alone is
# insufficient because the cwd /bridge is added to sys.path before PYTHONPATH entries.
if "/workspace" not in sys.path:
    sys.path.insert(0, "/workspace")
