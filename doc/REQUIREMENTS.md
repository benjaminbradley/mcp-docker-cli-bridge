# Requirements — Docker CLI Access Bridge MCP

> **Status:** Approved
> **Last updated:** 2026-04-01

---

## 1. Problem Statement

AI-assisted development tools (e.g., Claude Code) run inside their own container with restricted access. They can read and write source files, but cannot execute host-level commands or interact with the Docker daemon. This means they cannot run tests, linters, type checkers, or other CLI tools that live inside an application container.

The current workaround — asking a human operator to run `make test` and paste the output — breaks the autonomous development loop and adds significant friction to iterative workflows.

## 2. Solution Overview

An MCP (Model Context Protocol) server that runs inside the application's Docker container during development. It exposes whitelisted CLI commands as MCP tools over Streamable HTTP transport. An external AI agent discovers and calls these tools over a shared Docker bridge network using the container's DNS name.

The bridge is **dev-only infrastructure**. It must not exist in production images and must be removable without any changes to the application's source code.

---

## 3. Actors

- **Controller:** The AI development agent (Claude Code) running in its own container. Connects to the bridge as an MCP client. Has filesystem access to the application's source code but no Docker socket access.
- **Target:** The application container running the bridge server. Hosts the application code, dev tools (pytest, ruff, mypy, etc.), and the bridge MCP server process.
- **Human Operator:** Sets up the dev environment, starts the dev container, configures the command whitelist. Uses the application's Makefile directly (not the bridge) for interactive work.

---

## 4. Functional Requirements

### 4.1 Command Execution

The bridge must expose each whitelisted command as an MCP tool. When a tool is called, the bridge executes the corresponding command inside the container and returns the result.

- **Tool discovery:** The bridge must respond to MCP `tools/list` requests with a tool definition for each command in the whitelist. Each tool definition includes the command name, a human-readable description (derived from the executable prefix), and an input schema.
- **Tool invocation:** When a tool is called via MCP `tools/call`, the bridge executes the command via Python's `subprocess.run` with `shell=False`. The bridge constructs the full argument vector by prepending the command's configured executable prefix to any caller-provided arguments.
- **Tool result:** The bridge returns a structured result containing `stdout` (string), `stderr` (string), and `exit_code` (integer). Non-zero exit codes are reported as successful tool results (the bridge faithfully reports what the subprocess returned). Only bridge-level failures (unknown command, validation errors, timeouts) are reported as MCP tool errors.
- **Timeout:** A configurable global timeout (default: 60 seconds). Processes exceeding the timeout are killed and a tool error is returned.

### 4.2 Command Whitelist

The bridge must restrict execution to a predefined set of named commands. The whitelist is the **sole authorization mechanism** — any request for an unlisted command is rejected.

Each whitelist entry defines:
- **Name:** A symbolic identifier that becomes the MCP tool name (e.g., `run_tests`, `run_lint`).
- **Executable prefix:** The base command and any fixed arguments (e.g., `["python", "-m", "pytest"]`).
- **Extra arguments allowed:** A boolean flag. When `true`, the generated MCP tool schema includes an `args` parameter that accepts additional arguments. When `false`, the tool schema exposes no `args` parameter — the constraint is enforced at the protocol level.
- **Working directory:** The directory from which the command executes (e.g., `/app`).

The whitelist must be:
- **Externally configured:** Defined in a JSON file, not hardcoded in the server.
- **Immutable at runtime:** The config file must be mounted read-only into the container so that neither the bridge server nor any process invoked through it can modify the whitelist.
- **Instance-specific:** Each project defines its own whitelist for its own dev tools. The bridge server reads the config on startup.

### 4.3 Argument Safety

Even though `shell=False` prevents shell injection by design, the bridge must apply defense-in-depth validation on caller-provided arguments:
- Arguments must be strings. No nested structures.
- Arguments must not contain shell metacharacters (`;`, `&&`, `||`, `|`, `` ` ``, `$()`, `>`, `<`) as a defensive check. These would be harmless with `shell=False` but their presence suggests malformed or adversarial input.

### 4.4 Logging

The bridge must log every tool invocation and its outcome to a persistent JSONL file. Each log entry contains:
- Timestamp (ISO 8601)
- Command name requested
- Arguments provided
- Exit code returned
- Duration in milliseconds
- Stdout length (bytes)
- Stderr length (bytes)
- Whether the request was rejected (and the rejection reason, if applicable)

The log directory must be volume-mounted from the host so logs persist across container restarts and rebuilds.

Stdout/stderr content is **not** logged (to avoid unbounded log growth). The log captures metadata only.

### 4.5 Error Handling

The bridge must return structured errors for:
- Unknown command name → MCP tool error with the unknown name and a list of available tools.
- Extra arguments provided when `allow_extra_args` is `false` → enforced by tool schema (no `args` parameter exposed); if bypassed, MCP tool error.
- Argument validation failure → MCP tool error with the rejected argument.
- Command timeout → MCP tool error with timeout duration and any partial output.
- Subprocess failure (e.g., executable not found) → MCP tool error.

MCP tool errors use the `isError` flag in tool results. Connection-level errors (server unreachable, malformed protocol messages) are handled by the MCP transport layer.

---

## 5. Networking Requirements

### 5.1 Docker Bridge Network

The Controller and Target communicate over a Docker bridge network. This network must be:
- **External (manually managed):** Created once via `docker network create`, not managed by any project's `docker compose up/down` lifecycle. This ensures DNS persistence across independent container rebuilds.
- **Named predictably:** The network name is documented and consistent so both the Controller and Target can reference it.

### 5.2 DNS Resolution

Containers communicate using Docker service names as hostnames. No static IP management. The Controller reaches the Target's MCP endpoint at `http://<service-name>:<port>/mcp`.

### 5.3 Port Exposure

The bridge port (7357) is exposed within the Docker network only. It must **not** be published to the host machine unless the operator explicitly chooses to do so (e.g., for debugging). The default configuration does not publish the port.

### 5.4 No Docker Socket Access

The Controller must not have access to `/var/run/docker.sock`. The bridge exists specifically to avoid granting Docker daemon access to the Controller.

### 5.5 Egress

The bridge imposes no restrictions on the Target container's existing network egress. If the application needs external API access (e.g., for integration tests), that continues to work as configured by the application's own compose setup.

---

## 6. Lifecycle Requirements

### 6.1 Dev Container Startup

The host project must provide a mechanism (e.g., `make dev-up`) to:
1. Ensure the external Docker bridge network exists (create if absent).
2. Build the dev-stage Docker image (which includes the bridge server and MCP SDK).
3. Start the Target container in long-running mode (bridge server as entrypoint).

### 6.2 Dev Container Shutdown

The host project must provide a mechanism (e.g., `make dev-down`) to stop the dev container. The external bridge network is **not** removed on shutdown (it is shared infrastructure that may serve multiple projects).

### 6.3 Rebuild Transparency

Rebuilding the Target container between requests must be transparent to the Controller. The Controller does not maintain persistent connections — each MCP request is independent. After a rebuild and restart, the container re-registers on the Docker network with the same service name.

### 6.4 Independence from Application Lifecycle

The bridge server has no knowledge of or dependency on the application's runtime state (database, configuration, etc.). It is a process executor only. Application initialization (DB migrations, config loading, etc.) occurs within the commands the bridge executes, not within the bridge itself.

---

## 7. Integration Requirements

### 7.1 Host Project Makefile

The host project's Makefile must support dual-mode operation:
- **Dev container running:** Makefile targets detect the running container and use `docker compose exec` to run commands directly (bypassing the bridge). This is the path for human operators.
- **No dev container running:** Makefile targets fall back to `docker compose run --rm` (ephemeral container, original behavior).

The bridge is not involved in Makefile target execution. It serves only the Controller (Claude Code).

### 7.2 Controller Registration

The host project must provide an MCP server configuration (e.g., `.mcp.json` at project root) that registers the bridge with Claude Code. This tells the Controller where to find the bridge and enables automatic tool discovery.

### 7.3 Pre-commit Hook

The host project may install a pre-commit hook that uses the bridge to run checks before committing. The hook:
- Sends tool call requests to the bridge for each check (lint, typecheck, tests).
- Fails the commit if any check returns a non-zero exit code.
- Provides a clear error message if the bridge is unreachable, directing the operator to start the dev container.

### 7.4 Host Project Documentation

The host project must maintain a development guide (`doc/DEVELOPMENT.md`) that covers:
- Prerequisites for the dev workflow (Docker, the bridge network, the bridge project as a sibling dependency).
- Starting and stopping the dev environment.
- How the bridge works and what commands are available.
- Pre-commit hook setup.
- Reference to secrets/config setup (`_env.example`, etc.).

---

## 8. Removability Requirements

The bridge must be fully removable from a host project without modifying any application source code.

- **Bridge server code** lives outside the application's source tree (e.g., in a separate project directory, not inside `src/`).
- **Dockerfile integration** uses a multi-stage build. The production stage does not include the bridge. The dev stage extends the production stage with the bridge layer.
- **Compose integration** uses a separate override file (e.g., `docker-compose.dev.yml`). Removing the override file restores the original ephemeral-container behavior.
- **MCP registration** is a standalone config file (`.mcp.json`) or a CLI registration (`claude mcp remove`). Removing it deregisters the bridge from the Controller.
- **Whitelist config** is a standalone file mounted into the container, not part of the application's configuration.
- **No application code imports or references** the bridge. The bridge is infrastructure, not a library.

---

## 9. Reusability Requirements

The bridge must be usable across multiple CLI-based Docker projects without modification to the bridge code itself.

- Each host project provides its own `commands.json` whitelist.
- Each host project provides its own Dockerfile dev stage and compose override that reference the shared bridge server file.
- The bridge server is a single Python file that depends on the MCP Python SDK and Python stdlib. Dependencies are declared in a `requirements.txt` shipped alongside the server.
- The bridge makes no assumptions about the application's language, framework, or tooling — it executes arbitrary (whitelisted) CLI commands.

---

## 10. Non-Requirements (Explicit Exclusions)

- **Authentication/authorization** beyond the command whitelist. The bridge is accessible only within the Docker network, which is sufficient for the dev use case.
- **Concurrent request handling.** The bridge processes one request at a time. Dev tool invocations are sequential (run lint, then test, then typecheck). If concurrency becomes needed, it is a future enhancement.
- **HTTPS/TLS.** Traffic is container-to-container on an isolated Docker network.
- **Persistent state.** The bridge is stateless (aside from the append-only log file). No database, no session tracking.
- **File transfer.** The bridge does not upload or download files. The Controller and Target share access to source files via their respective volume mounts.
- **MCP resources or prompts.** The bridge exposes only MCP tools. It does not serve MCP resources (file content) or prompts (templated interactions).
