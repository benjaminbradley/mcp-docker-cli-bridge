import sys

# Ensure /workspace/server.py (directory-mounted, always fresh) takes precedence
# over /bridge/server.py (Dockerfile-baked, stale). PYTHONPATH=/workspace alone is
# insufficient: the Dockerfile sets WORKDIR /bridge, which Python adds to sys.path
# *before* PYTHONPATH entries, so /bridge/server.py would win without this insert.
if "/workspace" not in sys.path:
    sys.path.insert(0, "/workspace")
