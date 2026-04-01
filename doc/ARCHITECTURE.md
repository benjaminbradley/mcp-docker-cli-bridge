# Architecture — Docker CLI Access Bridge

> **Status:** Approved
> **Last updated:** 2026-03-31

---

## 1. System Overview

The bridge is a single-process HTTP server that translates incoming JSON requests into subprocess invocations, constrained by a read-only command whitelist. It runs inside a host project's Docker container during development, exposed only on an internal Docker bridge network.

```
┌──────────────────────────────────────────────────────────────────┐
│  Host Machine                                                    │
│                                                                  │
│  ┌──────────────────────┐       ┌──────────────────────────────┐ │
│  │ Controller Container │       │ Target Container (dev stage) │ │
│  │ (Claude Code)        │       │                              │ │
│  │                      │       │  ┌────────────────────────┐  │ │
│  │  curl / HTTP client ─┼──────▶│  │ Bridge Server (:7357)  │  │ │
│  │                      │  Docker│  │                        │  │ │
│  │  Volume: /app/src ───┼─bridge─│  │  Whitelist   Executor  │  │ │
│  │  (shared source)     │network │  │  Loader      ─────────▶│──┼─┤ subprocess.run
│  │                      │       │  │               Validator │  │ │ (shell=False)
│  └──────────────────────┘       │  │               Logger    │  │ │
│                                  │  └────────────────────────┘  │ │
│                                  │                              │ │
│                                  │  Application code + dev tools│ │
│                                  │  (pytest, ruff, mypy, etc.)  │ │
│                                  └──────────────────────────────┘ │
│                                                                  │
│  Volumes:                                                        │
│    ./src/              → /app/src/          (source code, rw)    │
│    ./commands.json     → /bridge/commands.json (whitelist, ro)   │
│    ./data/bridge-logs/ → /bridge/logs/      (JSONL audit, rw)   │
│                                                                  │
│  External network:                                               │
│    <project-bridge-net>  (created once, shared, not compose-     │
│                           managed)                               │
└──────────────────────────────────────────────────────────────────┘
```

The Controller (Claude Code) and Target are independent containers that share a source code volume and a Docker bridge network. The bridge server is the only communication channel between them for command execution. The human operator bypasses the bridge entirely, using `make` targets that `docker compose exec` into the running container or `docker compose run --rm` ephemeral containers.

---

## 2. Bridge Server Components

The server is a single Python file (`server.py`) with four internal responsibilities, not separate modules:

### 2.1 HTTP Handler

A subclass of `http.server.BaseHTTPRequestHandler`. Accepts `POST /execute` requests only. Parses JSON request bodies, dispatches to the executor, and serializes JSON responses. All other paths and methods return HTTP 404.

The server uses `http.server.HTTPServer` (single-threaded, blocking). One request is processed at a time. This is intentional — dev tool invocations are sequential and concurrency is a non-requirement.

### 2.2 Whitelist Loader

Reads and validates `commands.json` once at startup. Builds an in-memory lookup dict keyed by command name. If the config file is missing, malformed, or contains invalid entries, the server exits immediately with a clear error message. There is no hot-reload — changing the whitelist requires a container restart.

### 2.3 Executor

Resolves a command name to its whitelist entry, constructs the full argument vector (executable prefix + optional caller args), and calls `subprocess.run` with `shell=False`, `capture_output=True`, `text=True`, `timeout`, and `cwd` from the whitelist entry. Returns stdout, stderr, and exit code. Catches `subprocess.TimeoutExpired` and `FileNotFoundError` and translates them to appropriate error responses.

### 2.4 Argument Validator

A pure function called before execution. Checks that all caller-provided arguments are strings and do not contain shell metacharacters. This is defense-in-depth — `shell=False` already prevents injection — but rejects clearly malformed input early with a descriptive error.

### 2.5 Request Logger

Appends a single JSONL line per request to a log file. The log entry is written after the request completes (or fails), capturing metadata only: timestamp, command name, args, exit code, duration in milliseconds, stdout/stderr byte lengths, and rejection reason if applicable. Stdout/stderr content is not logged.

The logger opens and closes the file per write (append mode) to avoid holding file handles and to ensure log entries are flushed even if the server crashes.

---

## 3. Request Flow

```
Controller                    Bridge Server                    subprocess
    │                              │                               │
    │  POST /execute               │                               │
    │  {"command":"run_tests",     │                               │
    │   "args":["--tb=short"]}     │                               │
    │─────────────────────────────▶│                               │
    │                              │  1. Parse JSON body           │
    │                              │  2. Look up "run_tests"       │
    │                              │     in whitelist               │
    │                              │  3. Check allow_extra_args    │
    │                              │  4. Validate args             │
    │                              │  5. Build argv:               │
    │                              │     ["python","-m","pytest",  │
    │                              │      "--tb=short"]            │
    │                              │  6. subprocess.run(argv,      │
    │                              │     shell=False, cwd="/app")  │
    │                              │─────────────────────────────▶│
    │                              │                               │
    │                              │  stdout, stderr, returncode  │
    │                              │◀─────────────────────────────│
    │                              │  7. Log metadata (JSONL)     │
    │                              │  8. Build JSON response      │
    │  {"stdout":"...","stderr":"",│                               │
    │   "exit_code":0}             │                               │
    │◀─────────────────────────────│                               │
```

Error paths short-circuit at the relevant step: unknown command at step 2, disallowed extra args at step 3, metacharacter rejection at step 4, timeout or exec failure at step 6. All error paths still log (step 7) with the rejection reason.

---

## 4. Deployment Topology

### 4.1 Multi-stage Dockerfile (in host project)

The bridge integrates into the host project's Dockerfile as an additional build stage. The bridge server file is copied from its sibling project directory at build time.

```
FROM python:3.x AS base
# ... application setup, production dependencies ...

FROM base AS dev
# ... dev dependencies (pytest, ruff, mypy) ...
COPY ../docker-cli-access-bridge/server.py /bridge/server.py
CMD ["python", "/bridge/server.py"]
```

The `base` stage is the production image. The `dev` stage extends it. The bridge file never appears in production builds. The exact `COPY` path depends on the Docker build context; the host project's compose override configures this.

### 4.2 Compose Override (in host project)

The host project provides a `docker-compose.dev.yml` that:
- Targets the `dev` stage of the Dockerfile.
- Keeps the container running (bridge server as entrypoint).
- Mounts the commands whitelist read-only.
- Mounts the log directory read-write.
- Attaches to the external bridge network.
- Exposes port 7357 on the bridge network only (no host port binding).

The base `docker-compose.yml` is unchanged. The dev override is additive.

### 4.3 External Bridge Network

Created once by the operator: `docker network create <network-name>`. Not managed by any project's compose lifecycle. Both the Controller container and the Target container (via their respective compose configs) attach to this network. The network name is a per-deployment convention, documented in each consumer project.

---

## 5. Integration Model

The bridge project is a **sibling directory dependency** — it lives alongside consumer projects on the host filesystem, not inside them.

```
parent/
├── docker-cli-access-bridge/    # This project (shared tool)
│   ├── server.py                # The bridge server (single file)
│   ├── README.md
│   └── doc/
│       ├── REQUIREMENTS.md
│       ├── ARCHITECTURE.md
│       ├── SPECS.md
│       └── TODO.md
│
├── find-work-bot/               # Consumer project A
│   ├── commands.json            # FWB-specific whitelist
│   ├── docker-compose.dev.yml   # Dev override referencing bridge
│   ├── doc/DEVELOPMENT.md       # Documents bridge dependency
│   ├── CLAUDE.md                # Documents bridge for CC
│   └── ...
│
└── other-project/               # Consumer project B
    ├── commands.json            # Its own whitelist
    ├── docker-compose.dev.yml   # Its own dev override
    └── ...
```

Each consumer provides four integration touchpoints:

1. **`commands.json`** — the project-specific command whitelist, mounted read-only into the dev container.
2. **`docker-compose.dev.yml`** — dev compose override that builds the dev stage, mounts the whitelist and logs, and joins the bridge network.
3. **Dockerfile dev stage** — extends the production image with dev tools and the bridge server.
4. **Documentation** — `doc/DEVELOPMENT.md` for humans, `CLAUDE.md` for the Controller.

Optional:
5. **Pre-commit hook** — shell script that calls the bridge for lint/typecheck/test checks.
6. **Makefile dual-mode** — targets that detect the running dev container and use `exec` instead of `run --rm`.

---

## 6. Data Model

The bridge has no persistent data model. Its only data structures are:

### 6.1 Whitelist Entry (in-memory, loaded from commands.json)

Per-command configuration read at startup:
- `name` — symbolic identifier (the lookup key).
- `command` — executable prefix as an array of strings.
- `allow_extra_args` — boolean, whether caller may append arguments.
- `cwd` — working directory for the subprocess.

### 6.2 Log Entry (appended to JSONL file)

Per-request metadata, written after each request completes:
- `timestamp` — ISO 8601.
- `command` — command name from request (or `null` if parse failed).
- `args` — arguments array from request.
- `exit_code` — subprocess exit code (or `null` if not executed).
- `duration_ms` — wall-clock execution time in milliseconds.
- `stdout_bytes` — length of captured stdout.
- `stderr_bytes` — length of captured stderr.
- `rejected` — boolean.
- `rejection_reason` — string (or `null` if not rejected).

---

## 7. Security Boundaries

The bridge's security posture is designed for a trusted dev-only network, not hostile environments.

- **Network isolation:** The bridge port is reachable only from the Docker bridge network. No host port binding by default.
- **Command restriction:** Only whitelisted commands execute. The whitelist file is mounted read-only.
- **No shell:** `subprocess.run` with `shell=False` eliminates the shell injection surface entirely.
- **Argument validation:** Defense-in-depth rejection of shell metacharacters in caller-provided args.
- **No auth:** Intentional. Network isolation is the access control. Adding auth would increase complexity without meaningful security improvement in the dev context.
- **No file transfer:** The bridge does not read or write files on behalf of the caller. Filesystem access happens through volume mounts, orthogonal to the bridge.

---

## 8. Constraints and Dependencies

- **Python 3.x stdlib only.** No `pip install`. The server uses `http.server`, `json`, `subprocess`, `datetime`, `os`, and `pathlib`.
- **Single-threaded.** One request at a time. Sufficient for sequential dev tool invocations.
- **No hot-reload.** Whitelist changes require a container restart. This is a feature — it prevents runtime config mutation.
- **Docker required.** The bridge assumes it runs inside a Docker container on a Docker bridge network. It has no standalone mode.
- **Consumer provides the Dockerfile.** The bridge project ships only `server.py`. The consumer project owns the Dockerfile, compose files, whitelist, and all integration wiring.
