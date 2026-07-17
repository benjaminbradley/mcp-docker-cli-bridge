# Security Model — MCP Docker CLI Bridge

> **Last updated:** 2026-07-16

---

## 1. What Problem Does This Actually Solve?

The bridge exists because Claude Code runs inside a VS Code Dev Container that is deliberately locked down:

- **No Docker socket access.** Claude Code cannot call `docker exec`, `docker run`, or interact with the Docker daemon in any way.
- **Restricted network egress.** The devcontainer firewall blocks most outbound traffic.

Without the bridge, the only way Claude Code could run commands inside the app container would be to have a human paste output, or to be granted Docker socket access. **Granting Docker socket access is equivalent to granting root on the host machine** — the socket owner can launch privileged containers, mount the host filesystem, and escape the container entirely. The bridge avoids this completely.

The bridge provides a **controlled, audited path** from the devcontainer to specific, operator-approved CLI commands in the app container — without requiring Docker socket access, SSH, or a full shell.

**Core value proposition:**

| Without bridge | With bridge |
|---|---|
| Human pastes output manually | Claude Code calls tools autonomously |
| Or: grant Docker socket (= host root) | Named command allowlist only |
| No audit trail | Every call logged to JSONL |
| No isolation | Firewall limits Claude Code to port 7357 only |

---

## 2. What the Bridge Does and Does Not Prevent

### 2.1 What it prevents

**Shell injection via argument manipulation.**  
`subprocess.run(shell=False)` + metacharacter blocklist means Claude Code cannot break out of argv into a shell. An argument like `--flag; rm -rf /` is rejected at validation; even if it were not, it would be passed as a single literal string to the subprocess, not interpreted as shell syntax.

**Expanding the command surface at runtime.**  
`commands.json` is mounted read-only (`:ro`). There is no API to register new commands, change the allowlist, or modify timeouts at runtime. The set of callable tools is fixed when the container starts.

**Calling arbitrary executables.**  
The bridge performs a allowlist lookup before execution. Only commands declared in `commands.json` can run. Claude Code cannot call `bash`, `curl`, `ssh`, or any other executable not on the list.

**Reaching the Docker host machine.**  
Without Docker socket access and with the firewall rule blocking the bridge gateway IP (`W.X.Y.1`), Claude Code has no path to the host machine. The bridge runs inside a sibling container, not on the host.

**Network pivot to other containers.**  
The recommended firewall configuration allows the devcontainer to reach only port 7357 on the bridge subnet. Other containers on other networks, and the host's bridge gateway, are blocked.

**Audit evasion.**  
Every tool call — including rejections — is logged with full arguments, stdout, stderr, exit code, and timing. The log is append-only from the server's perspective and volume-mounted to the host.

---

### 2.2 What it does NOT prevent

**Code execution of content written by Claude Code.**  
This is the most important nuance. If Claude Code can write files (it can — that is its primary capability), and a allowlisted command executes those files, then **allowlisting that command grants code execution**.

The commands split into two distinct risk categories:

#### Category A — Static analysis: no code execution

| Command | What it does | Can Claude Code weaponize it? |
|---|---|---|
| `ruff check` | Parses Python, reports lint errors | No — reads AST only, never executes |
| `ruff format` | Rewrites Python formatting | No — syntactic transformation only |
| `mypy` | Type-checks Python | No — static analysis, does not import user code at runtime[^1] |

For Category A commands, the threat surface is:

- **Reading the container filesystem.** Ruff, mypy, and similar tools can read any file in their configured path. This includes application secrets, `.env` files, and environment variables exported to the subprocess environment. However, Claude Code already has filesystem read access via its volume mount, so this grants no new capability.
- **Resource exhaustion.** A crafted file could cause excessive CPU or memory usage. The `timeout` field in `commands.json` bounds the time window; subprocess resource caps are not enforced beyond this.

**For Category A-only allowlists, the bridge provides meaningful containment.** Claude Code cannot execute arbitrary code through static analysis tools.

[^1]: mypy may import stub packages and plugins at startup, but does not execute user-written test or application code.

#### Category B — Test runners and interpreters: full code execution

| Command | What it executes | Risk |
|---|---|---|
| `pytest` | Test files — arbitrary Python | Full code execution |
| `python -m pytest` | Same | Full code execution |
| `npm test`, `cargo test`, etc. | Test files in respective language | Full code execution |
| `python -c "..."` | Inline code | Full code execution |
| `make`, `bash`, shell scripts | Arbitrary shell commands | Full code execution |

For Category B commands: **if Claude Code can write to files in the test directory (or anywhere that the test runner discovers), it can execute arbitrary code inside the container.** This is intentional and expected — Claude Code needs to write code that gets tested — but it means the bridge does not add a security boundary for test execution.

**What does Category B contain, then?**

Even for test runners, the bridge still provides:
1. No Docker socket access. Code runs in the app container, not as host root.
2. Network firewall still limits outbound connections from the devcontainer.
3. Audit log records every invocation.
4. The container's own resource limits (memory, CPU) apply.
5. The container's non-root user limits direct system impact.

The containment is the **container boundary itself**, not the bridge. The bridge controls *which container* gets the execution and *which named command* triggers it.

---

## 3. Threat Model Summary

### Attacker: compromised or jailbroken AI model

The bridge is designed for a trusted AI model in a dev workflow. The question is what a malicious or jailbroken model could do.

| Attack vector | Blocked? | How |
|---|---|---|
| Shell injection via args (`; rm -rf /`) | Yes | shell=False + metacharacter blocklist |
| Calling unlisted commands | Yes | Allowlist lookup; unknown names rejected |
| Modifying the allowlist at runtime | Yes | commands.json mounted :ro |
| Docker socket access | Yes | Not mounted; no path to daemon |
| Reaching host via bridge gateway | Yes (with recommended firewall) | iptables REJECT on gateway IP |
| Reaching other containers | Yes (with recommended firewall) | iptables allows only port 7357 on bridge subnet |
| Executing code via `pytest` (Category B) | **No** | Test runner executes written files; by design |
| Reading container secrets/env vars | **No** | Container filesystem and env fully accessible |
| Resource exhaustion within timeout | **No** | Timeout caps duration, not CPU/memory |
| Forging or deleting audit log | **No** | Log is a plain file; container process can delete it |

### Attacker: network-adjacent container

Any container on the same Docker bridge subnet can call the MCP endpoint. There is no per-caller authentication. The firewall limits which containers can reach the subnet, but within the subnet it is open.

| Risk | Mitigation |
|---|---|
| Any subnet container calls tools | Firewall limits devcontainer subnet access; no host port binding |
| Lateral movement from a compromised app container | App container is already inside the same container; no escalation via bridge |
| Sniffing traffic (no TLS) | Traffic is localhost-to-container; doesn't leave the host machine |

---

## 4. Effective Security Profiles

### Profile 1: Lint and format only (high containment)

```json
{
  "commands": {
    "run_lint":        {"command": ["ruff", "check", "src/"], ...},
    "run_format_check":{"command": ["ruff", "format", "--check", "src/"], ...},
    "run_typecheck":   {"command": ["mypy", "src/"], ...}
  }
}
```

**What is contained:** All Category A. Claude Code cannot execute arbitrary code through these tools. The bridge meaningfully restricts what can happen.

**Residual risk:** Container filesystem readable (same as Claude Code's volume access). Resource exhaustion within timeout window.

**Appropriate for:** CI-gate checking on a sensitive codebase where you want Claude Code to verify style and types but not execute tests.

---

### Profile 2: Test runner included (code execution granted)

```json
{
  "commands": {
    "run_tests": {"command": ["pytest", "tests/", "-v"], "allow_extra_args": true, ...},
    "run_lint":  {"command": ["ruff", "check", "src/"], ...}
  }
}
```

**What is contained:** Shell injection, Docker daemon access, network reach. The bridge still provides structured access, auditing, and limits escalation beyond the container.

**What is NOT contained:** Claude Code writes code to `tests/` → calls `run_tests` → that code executes. This is the intended workflow.

**Appropriate for:** The standard dev loop where Claude Code writes and runs tests. Accept that code execution happens within the container boundary.

---

### Profile 3: `allow_extra_args: true` on a test runner (maximum flexibility)

In addition to everything in Profile 2, this allows Claude Code to pass arbitrary additional arguments to pytest — including pointing to specific test files it has written anywhere in the filesystem.

**This is appropriate** and the common case. Claude Code needs to run specific tests it just wrote. The containment boundary is still the container.

**What changes vs `allow_extra_args: false`:** Claude Code can influence *which* test files run (e.g., `pytest /tmp/malicious.py`) not just whether tests run. In practice this is the same code execution risk, just with more flexibility in file path.

---

## 5. Deployment Checklist

### Absolute requirements (always apply)

- [ ] Bridge port NOT published to host (`expose:` not `ports:` in compose)
- [ ] `commands.json` mounted read-only (`:ro`)
- [ ] Bridge runs as non-root user inside container
- [ ] Devcontainer firewall blocks bridge gateway IP and restricts port access to 7357

### Strongly recommended

- [ ] Use a dedicated `/29` subnet per project so the firewall rule is precise
- [ ] Set `timeout` on all commands — especially test runners
- [ ] Volume-mount `bridge-logs/` to host for durable audit trail
- [ ] Review `bridge.jsonl` periodically when using Category B commands

### For Category B (test runners) specifically

- [ ] Accept that code execution is possible; rely on container boundary for containment
- [ ] Ensure the app container has no Docker socket access, no host mounts beyond necessary source/data
- [ ] Do not mount host credentials, SSH keys, or cloud provider token files into the app container
- [ ] Non-root execution in the container limits blast radius of any code Claude Code executes

---

## 6. Supply-Chain: Package Upload Cooldown

To reduce exposure to compromised package releases (typosquats, hijacked maintainer accounts, malicious minor bumps), every dependency resolution and install in this repo rejects packages uploaded more recently than a fixed window. That gives the ecosystem time to notice and yank a bad release before we consume it.

The window is enforced at **two independent chokepoints**:

- **Lock time** (`make lock` / `make lock-upgrade`) — `uv pip compile --exclude-newer=<cutoff>` prunes too-new candidate versions from the resolver's search space, so the lock file never pins a package inside the cooldown.
- **Install time** (Dockerfile, compose, CI) — `pip` honors `PIP_UPLOADED_PRIOR_TO`, refusing to install anything too new even if a lock somehow contained it.

Lock-time is the primary defense; install-time is a safety net that also protects against ad-hoc `pip install` calls that skip the lock.

> Historical note: an earlier version of this pipeline used `pip-tools` (`pip-compile`) for lock generation. `pip-tools` does **not** honor `PIP_UPLOADED_PRIOR_TO`, so lock files were pinned to whatever was latest, and install-time pip would then refuse those pins — a silent failure of the intended guarantee. The switch to `uv pip compile` closed that gap because uv respects `--exclude-newer` during resolution.

### 6.1 Value and source of truth

The default is a 3-day window. `COOLDOWN_DAYS` is the single source of truth; `PIP_UPLOADED_PRIOR_TO` is derived from it (as `P<N>D`, an ISO 8601 duration) and the uv cutoff timestamp is computed from it inside the lock container (as `date -u -d "<N> days ago"`, so both forms always agree).

```make
# Makefile
COOLDOWN_DAYS ?= 3
PIP_UPLOADED_PRIOR_TO ?= P$(COOLDOWN_DAYS)D
export PIP_UPLOADED_PRIOR_TO
```

Override for a one-off run with `COOLDOWN_DAYS=7 make lock`, or by exporting the shell env vars before running `docker compose` / CI.

### 6.2 Where the value must be honored

Every dependency-resolving and package-installing step across dev, lock generation, CI, and release builds must apply the cooldown. Missing any one of them leaves a hole.

| Location | Kind | How the value gets there |
|---|---|---|
| `Makefile` | Source of truth | `COOLDOWN_DAYS ?= 3` → derives `PIP_UPLOADED_PRIOR_TO = P3D` |
| `Makefile` `lock` / `lock-upgrade` | `docker run -e` + `uv pip compile --exclude-newer` | Passes `COOLDOWN_DAYS` into the throwaway `python:3.12-slim` container; the container converts it to an absolute RFC 3339 cutoff and passes it to `uv` |
| `Dockerfile` base stage | Build `ARG` + `ENV` | `ARG PIP_UPLOADED_PRIOR_TO=P3D` → `ENV`. Applies to `RUN pip install -r requirements.txt` and inherited by dev stage |
| `dev/docker-compose.yml` | Build args | `build.args.PIP_UPLOADED_PRIOR_TO: ${PIP_UPLOADED_PRIOR_TO:-P3D}` — reads exported Makefile var, defaults to P3D |
| `.github/workflows/ci.yml` | Workflow-level `env:` | Both `docker-validate` (compose build → args expansion) and `audit` (pip-audit's install phase) inherit |
| `.github/workflows/publish.yml` | Dockerfile ARG default | Uses `docker/build-push-action` with no explicit build-arg; falls back to the `ARG PIP_UPLOADED_PRIOR_TO=P3D` default in the Dockerfile |

### 6.3 Why lock-time enforcement is load-bearing

Lock files pin exact versions. Once `foo==1.2.3` is in `requirements.txt`, every downstream install goes to that version regardless of whether the cooldown blocks it or not — you either install what's pinned, or fail. The cooldown at install time is a fail-closed safety net; the cooldown at lock time is what prevents the failure from occurring in normal operation.

Concretely: if `make lock` pins a package uploaded 2 hours ago, then a fresh `docker build` or `pip-audit` run against that lock will fail with `No matching distribution found` — the pin exists, but the cooldown rejects installing it. Users then either wait N days or bypass the cooldown, both of which defeat the purpose. Lock-time enforcement (`uv --exclude-newer`) prevents this by ensuring only cooled-off versions can be pinned in the first place.

### 6.4 Changing the default

To change the window (e.g., 3 days → 7 days):

1. Edit `COOLDOWN_DAYS` in `Makefile`.
2. Update the `ARG PIP_UPLOADED_PRIOR_TO=P3D` default in `Dockerfile` and the `${…:-P3D}` fallback in `dev/docker-compose.yml` so direct (non-Make) invocations still get the new default.
3. Update the workflow-level `env: PIP_UPLOADED_PRIOR_TO: P3D` in `.github/workflows/ci.yml`.
4. Run `make lock-upgrade` and commit the resulting lock diff — this reflects the new cooldown in the pinned versions.
5. Rebuild (`make down && make build && make up && make connect`).

### 6.5 Threat coverage

| Attack | Mitigated? |
|---|---|
| Newly-published malicious minor version of a direct dep | Yes, as long as the window exceeds detection time |
| Newly-published malicious minor version of a transitive dep | Yes, same |
| Typosquat that has been on the index for months | No — cooldown is time-based, not reputation-based |
| Compromised existing version (retroactive) | No — pip doesn't re-check older uploads |
| Compromise of the index itself | No — cooldown is a client-side filter over what the index returns |

Cooldown is one control in depth. It composes with (does not replace) pinned versions, lock files, and — for stronger guarantees — hash pinning (`pip-compile --generate-hashes`), which this repo does not currently use.

---

## 7. Known Limitations and Non-Mitigations

**No authentication on the MCP endpoint.** Any container on the bridge subnet can call any tool. Authentication would require token management but is not implemented. Mitigation: network isolation via firewall.

**No TLS.** Traffic is plaintext on the Docker bridge network. Acceptable because it never leaves the host machine, but means the bridge should never be exposed on a routable interface.

**Audit log is not tamper-proof.** The JSONL file is a plain file on a volume mount. A process running in the container can delete or modify it. The log is useful for debugging and review, not forensic evidence.

**No resource caps beyond timeout.** A allowlisted command can use all available CPU and RAM until the timeout. Docker resource limits on the container are the appropriate mechanism; the bridge does not add additional caps.

**Shared container filesystem.** The bridge subprocess has the same filesystem access as the application. There is no chroot or additional isolation per tool invocation.

**Secrets in environment variables.** Environment variables set in the container (e.g., `DATABASE_URL`, `API_KEY`) are inherited by every subprocess the bridge spawns. Do not put secrets in the container environment that you would not want accessible to the commands being run.
