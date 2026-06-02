# Build Plan — Phase 4: Output Filtering, Pipe Syntax, and Output Caching

> **Status:** Planning
> **Created:** 2026-06-02
> **References:** [Requirements](REQUIREMENTS.md) · [Architecture](ARCHITECTURE.md) · [Specs](SPECS.md) · [Phase 4 design conversation](../CHANGELOG.md)

Legend:

`[ ]` Planned → `[~]` In progress → `[o]` Implemented → `[x]` Verified

---

## Overview

Adds three optional input parameters to every MCP tool (`pipe`, `cache`, `cache_id`) and extends `CommandResult` with corresponding output fields. The `pipe` parameter accepts a Unix-style pipeline string that is parsed and executed by the bridge (not passed to shell), enabling AI assistants to filter and truncate output using familiar idioms. The `cache`/`cache_id` parameters let callers store and re-filter full output without re-running the command.

### New input parameters (added to every tool schema)

| Parameter | Type | Purpose |
|---|---|---|
| `pipe` | `string \| null` | Pipeline filter: `2>&1 \| grep [-E] 'pat' \| head/tail N` |
| `cache` | `boolean` | Store full pre-filter output; returns `cache_id` in response |
| `cache_id` | `string \| null` | UUID from prior result; skips re-execution, applies `pipe` to cached output |

### New `CommandResult` output fields

| Field | Type | Present when |
|---|---|---|
| `warnings` | `list[str] \| null` | Pipe contained unsupported flags |
| `cache_id` | `string \| null` | `cache: true` was requested |
| `cache_age_ms` | `int \| null` | `cache_id` was provided |

### `pipe` syntax

Supported operations (allowlisted; anything else is an error):

```
2>&1               — merge stderr into stdout before filtering
grep "pat"         — keep lines containing literal pattern (single or double quotes)
grep -E "pat"      — keep lines matching regex (ReDoS-safe, 1s timeout per segment)
grep -i "pat"      — case-insensitive literal match
grep -n "pat"      — prefix each matched line with its line number
grep -A N "pat"    — N lines of trailing context after each match
grep -B N "pat"    — N lines of leading context before each match
grep -C N "pat"    — N lines of context before and after each match
head N             — first N lines  (also accepts: head -n N)
tail N             — last N lines   (also accepts: tail -n N)
```

Flag bundling is supported: `-iE`, `-in`, `-iA 3`, `-Ei`, etc.

`head -c N` → warning in `CommandResult.warnings` ("head: -c (byte truncation) not supported, use `head N` for line truncation"), op is skipped.

Any other unknown flags on known commands → warning, best-effort execution without the unsupported flag.

Unknown command names → hard error (`isError: true`).

### Cache mechanics

```
cache=true, no cache_id → execute → apply pipe → write full raw output to /tmp/bridge_cache/<uuid4> → return filtered result + cache_id
cache_id provided       → skip execution → load file → apply pipe → return result + cache_age_ms
cache_id + no pipe      → return raw cached output
```

Cache files: `chmod 0o600`, 24-hour TTL, background cleanup task, UUID validated before path construction.

---

## Test structure additions

New test classes (in `tests/test_server.py`):

- `TestParsePipe` — pipe string tokenisation and PipeOp construction
- `TestApplyPipe` — per-operation filtering logic, stream merge, ReDoS timeout
- `TestCacheSubsystem` — save/load roundtrip, UUID validation, expiry, cleanup
- `TestPipeIntegration` — end-to-end handler tests: pipe filtering, cache roundtrip, warnings surfaced

Updates to existing classes:

- `TestBuildTools` — verify `pipe`, `cache`, `cache_id` appear in every tool's `inputSchema`
- `TestToolHandlers` — verify new params accepted; existing tests unaffected

---

## Tasks

---

### 4.1 — Extend `CommandResult` and define `PipeOp` types

**Purpose:** Add the three new output fields to `CommandResult` so downstream code can attach filter warnings, a cache UUID, and cache age. Define the `PipeOp` type union that the parser (4.2) and executor (4.3) will share.

**References:**
- `server.py:51-56` — current `CommandResult` model
- `server.py:23-49` — existing pydantic model patterns (`CommandEntry`, `CommandsConfig`)
- SPECS.md §6.1 — model definitions

**TDD:**

- [ ] **RED:** In `TestCommandsConfig` (or a new `TestCommandResult` nested class), add:
  - `test_new_fields_default_to_none` — `CommandResult(stdout="", stderr="", exit_code=0)` constructs without error; `warnings`, `cache_id`, `cache_age_ms` are all `None`.
  - `test_warnings_field_serializes` — `CommandResult(..., warnings=["unsupported flag -i ignored"])` round-trips through `model_dump_json()` / `model_validate_json()` with the list intact.
  - `test_cache_fields_serialize` — `CommandResult(..., cache_id="abc", cache_age_ms=5000)` serializes both fields correctly.
  
  Confirm tests fail: `CommandResult` does not yet have the new fields.

- [ ] **GREEN:** Add to `CommandResult` in `server.py`:
  ```python
  warnings: list[str] | None = None
  cache_id: str | None = None
  cache_age_ms: int | None = None
  ```
  Run tests — all pass.

- [ ] **REFACTOR:** Add `PipeOp` union type after `CommandResult`:
  ```python
  @dataclass
  class StreamMergeOp: ...

  @dataclass
  class GrepOp:
      pattern: str
      regex: bool = False
      ignore_case: bool = False
      line_numbers: bool = False
      context_before: int = 0
      context_after: int = 0

  @dataclass
  class HeadOp:
      n: int

  @dataclass
  class TailOp:
      n: int

  PipeOp = StreamMergeOp | GrepOp | HeadOp | TailOp
  ```
  No tests needed for type definitions alone; types are exercised in 4.2.

**Verification criteria:**
- [ ] All existing tests still pass (`make test`)
- [ ] `CommandResult(stdout="a", stderr="b", exit_code=0).model_dump_json()` produces `{"stdout":"a","stderr":"b","exit_code":0}` — no `warnings`/`cache_id`/`cache_age_ms` keys present. Achieved by calling `model_dump_json(exclude_none=True)` at the serialisation call site (`server.py:290`).
- [ ] The call at `server.py:290` is updated from `result.model_dump_json()` to `result.model_dump_json(exclude_none=True)`
- **Files:** `server.py` (models section + line 290)

---

### 4.2 — Pipe parser: `parse_pipe()`

**Purpose:** Safely tokenise a `pipe` string into a list of `PipeOp` objects. The parser enforces the allowlist of supported operations, emits warnings for unsupported flags on known commands, and raises `ValueError` for unrecognised command names. No shell execution occurs here.

**References:**
- `server.py:131-142` — `BLOCKED_SEQUENCES` and `validate_args()` for the existing input-safety pattern
- `server.py:51` — `PipeOp` types defined in 4.1
- SPECS.md §3 — argument validation rationale

**Interface:**
```python
def parse_pipe(pipe_str: str) -> tuple[list[PipeOp], list[str]]:
    """Parse a pipe string. Returns (ops, warnings). Raises ValueError on unknown command."""
```

**TDD:**

- [ ] **RED:** Add `TestParsePipe` class with tests:
  - `test_empty_string_returns_no_ops` — `parse_pipe("")` → `([], [])`
  - `test_stream_merge` — `parse_pipe("2>&1")` → `([StreamMergeOp()], [])`
  - `test_grep_literal` — `parse_pipe('grep "FAIL"')` → `([GrepOp("FAIL", regex=False)], [])`
  - `test_grep_regex` — `parse_pipe("grep -E 'ERR.*'")` → `([GrepOp("ERR.*", regex=True)], [])`
  - `test_grep_single_quotes` — `parse_pipe("grep 'foo'")` → `([GrepOp("foo", regex=False)], [])`
  - `test_head_bare` — `parse_pipe("head 20")` → `([HeadOp(20)], [])`
  - `test_head_n_flag` — `parse_pipe("head -n 20")` → `([HeadOp(20)], [])`
  - `test_tail_bare` — `parse_pipe("tail 5")` → `([TailOp(5)], [])`
  - `test_tail_n_flag` — `parse_pipe("tail -n 5")` → `([TailOp(5)], [])`
  - `test_chained_pipe` — `parse_pipe("2>&1 | grep 'ERR' | head 10")` → `([StreamMergeOp(), GrepOp("ERR", False), HeadOp(10)], [])`
  - `test_unknown_command_raises` — `parse_pipe("awk '{print}'")` raises `ValueError`
  - `test_grep_case_insensitive` — `parse_pipe("grep -i 'pat'")` → `([GrepOp("pat", ignore_case=True)], [])`
  - `test_grep_line_numbers` — `parse_pipe("grep -n 'pat'")` → `([GrepOp("pat", line_numbers=True)], [])`
  - `test_grep_context_after` — `parse_pipe("grep -A 3 'pat'")` → `([GrepOp("pat", context_after=3)], [])`
  - `test_grep_context_before` — `parse_pipe("grep -B 2 'pat'")` → `([GrepOp("pat", context_before=2)], [])`
  - `test_grep_context_symmetric` — `parse_pipe("grep -C 5 'pat'")` → `([GrepOp("pat", context_before=5, context_after=5)], [])`
  - `test_grep_flag_bundling_iE` — `parse_pipe("grep -iE 'pat'")` → `GrepOp("pat", regex=True, ignore_case=True)`, no warnings
  - `test_grep_flag_bundling_in` — `parse_pipe("grep -in 'pat'")` → `GrepOp("pat", ignore_case=True, line_numbers=True)`, no warnings
  - `test_grep_flag_bundling_with_context` — `parse_pipe("grep -iA 3 'pat'")` → `GrepOp("pat", ignore_case=True, context_after=3)`, no warnings
  - `test_grep_unknown_flag_warns` — `parse_pipe("grep -v 'pat'")` → `([GrepOp("pat")], ["grep: flag -v not supported, ignored"])`
  - `test_head_c_flag_warns_and_skips` — `parse_pipe("head -c 100")` → `([], ["head: -c (byte truncation) not supported, use \`head N\` for line truncation"])`; the HeadOp is omitted entirely since there is no meaningful fallback
  - `test_grep_fully_unknown_flag_warns` — `parse_pipe("grep -Ei -v 'pat'")` → regex=True, warns about `-v`
  
  Confirm all fail: `parse_pipe` does not yet exist.

- [ ] **GREEN:** Implement `parse_pipe()` in `server.py`. Approach:
  1. Split on ` | ` (with surrounding whitespace)
  2. For each segment, strip and match against the allowlist using a small hand-written token parser (no `re` for the pipe syntax itself — avoids recursion concerns)
  3. Collect warnings for unrecognised flags, raise `ValueError` for unrecognised command names

- [ ] **REFACTOR:** Extract token-matching helpers if the function body exceeds ~50 lines. Keep `parse_pipe` as the single public entry point.

**Verification criteria:**
- [ ] All `TestParsePipe` tests pass
- [ ] `parse_pipe` never calls `subprocess`, `os.system`, `eval`, or `exec`
- [ ] The function is a pure sync function with no side effects
- **Files:** `server.py`, `tests/test_server.py`

---

### 4.3 — Pipe executor: `apply_pipe()`

**Purpose:** Apply a list of `PipeOp` objects to `(stdout, stderr)` strings in order, returning the filtered `(stdout, stderr)`. The regex grep path runs in a thread with a 1-second timeout to prevent ReDoS from freezing the event loop; on timeout, returns all lines unfiltered with a warning added.

**References:**
- `server.py:150-168` — `execute_command()` uses `asyncio.to_thread` for the same CPU/blocking-protection rationale
- `server.py:51` — `PipeOp` types (task 4.1)
- `.autocode/lang/python/testing.md` — async test patterns (`@pytest.mark.asyncio`)

**Interface:**
```python
async def apply_pipe(
    ops: list[PipeOp], stdout: str, stderr: str
) -> tuple[str, str, list[str]]:
    """Apply ops in order. Returns (stdout, stderr, additional_warnings)."""
```

**TDD:**

- [ ] **RED:** Add `TestApplyPipe` class:
  - `test_no_ops_returns_unchanged` — empty ops → stdout and stderr unchanged
  - `test_stream_merge` — `StreamMergeOp` → stdout = stdout + stderr, stderr = `""`
  - `test_stream_merge_ordering` — merge happens before grep/head/tail when first in list
  - `test_grep_literal_filters_lines` — keeps only lines containing pattern
  - `test_grep_literal_empty_match` — no matching lines → stdout = `""`, no error
  - `test_grep_regex_filters_lines` — `GrepOp("ERR.*", regex=True)` keeps matching lines
  - `test_grep_regex_timeout_returns_unfiltered_with_warning` — pathological regex on long input → returns all lines + warning `"grep -E: regex timed out, returning unfiltered output"`
  - `test_grep_case_insensitive` — `GrepOp("error", ignore_case=True)` matches lines containing "Error", "ERROR", "error"
  - `test_grep_case_insensitive_regex` — `GrepOp("err.*", regex=True, ignore_case=True)` matches case-insensitively
  - `test_grep_line_numbers` — `GrepOp("FAIL", line_numbers=True)` prefixes each matched line with `N:` where N is the 1-based line number in the original input
  - `test_grep_context_after` — `GrepOp("FAIL", context_after=2)` returns each matched line plus the 2 lines following it
  - `test_grep_context_before` — `GrepOp("FAIL", context_before=2)` returns each matched line plus the 2 lines preceding it
  - `test_grep_context_symmetric` — `GrepOp("FAIL", context_before=1, context_after=1)` returns the line before, the match, and the line after
  - `test_grep_context_overlapping_matches` — adjacent matches whose context windows overlap produce deduplicated output (no line repeated), preserving order
  - `test_grep_context_at_boundaries` — match on first line with `context_before=2` does not error; match on last line with `context_after=2` does not error
  - `test_head_n_lines` — `HeadOp(3)` on 10-line input returns first 3 lines
  - `test_tail_n_lines` — `TailOp(3)` on 10-line input returns last 3 lines
  - `test_head_larger_than_input` — `HeadOp(100)` on 5-line input returns all 5 lines
  - `test_grep_applies_to_stdout_only_when_not_merged` — grep does not filter stderr
  - `test_chained_merge_grep_head` — `[StreamMergeOp, GrepOp("E"), HeadOp(2)]` applied in order
  
  Confirm all fail: `apply_pipe` does not exist.

- [ ] **GREEN:** Implement `apply_pipe()`:
  - `StreamMergeOp`: `stdout = stdout + stderr; stderr = ""`
  - `GrepOp` (literal, no flags): `[l for l in lines if pattern in l]`
  - `GrepOp` (ignore_case): use `pattern.lower()` against `l.lower()` for matching; display original line
  - `GrepOp` (line_numbers): prefix each kept line with `{original_1based_index}:` before joining
  - `GrepOp` (context_before/after): collect matched line indices, expand each to a window, merge overlapping windows, deduplicate while preserving order
  - `GrepOp` (regex): compile with `re.IGNORECASE` if `ignore_case=True`; run in `asyncio.to_thread` with `asyncio.wait_for(..., timeout=1.0)`; on `asyncio.TimeoutError`, return unfiltered + warning
  - `HeadOp`: `lines[:n]`
  - `TailOp`: `lines[-n:]`
  - Preserve trailing newline: if original stdout ends with `\n` and result is non-empty, ensure result ends with `\n`
  - Context window ordering: `line_numbers` is applied after context expansion (numbers reflect position in original input, not in filtered output)

- [ ] **REFACTOR:** Extract `_grep_sync(lines, pattern, regex, ignore_case, line_numbers, context_before, context_after) -> list[str]` as a single sync helper covering all grep modes (called via `to_thread` for regex; called directly for literal). This keeps the async path clean and the sync logic independently testable.

**Verification criteria:**
- [ ] All `TestApplyPipe` tests pass, including the ReDoS timeout test
- [ ] `apply_pipe` is `async`; it does not block the event loop on long regex
- [ ] No `subprocess` calls; no shell execution
- **Files:** `server.py`, `tests/test_server.py`

---

### 4.4 — Cache subsystem

**Purpose:** Persist full pre-filter command output to a temp file keyed by UUID4, load it back by ID (with age), and clean up files older than 24 hours. Security: UUID validated against strict format before constructing the file path; files written at `0o600`.

**References:**
- `server.py:75-83` — `BridgeConfig`; consider whether `BRIDGE_CACHE_DIR` env var is needed (per design: fixed `/tmp/bridge_cache`, no env var)
- `server.py:176-181` — `log_request()` for the open/write/close file pattern
- `.autocode/lang/python/testing.md` — filesystem/permission test patterns

**Interface:**
```python
_CACHE_DIR = "/tmp/bridge_cache"
_CACHE_TTL_SECONDS = 86400  # 24 hours

@dataclass
class CacheEntry:
    stdout: str
    stderr: str
    exit_code: int
    created_at: float  # time.time()

def save_cache(stdout: str, stderr: str, exit_code: int) -> str:
    """Write entry to cache dir, return UUID string."""

def load_cache(cache_id: str) -> CacheEntry:
    """Load cache entry. Raises ValueError on invalid UUID format.
    Raises FileNotFoundError if missing. Raises RuntimeError if expired (>24h)."""

def cleanup_stale_cache() -> int:
    """Delete files older than TTL. Returns count of deleted files."""
```

**TDD:**

- [ ] **RED:** Add `TestCacheSubsystem` class:
  - `test_save_returns_uuid_string` — `save_cache("out", "err", 0)` returns a string matching `uuid4` format
  - `test_save_load_roundtrip` — save then load returns identical `stdout`, `stderr`, `exit_code`
  - `test_load_invalid_uuid_raises_value_error` — `load_cache("../../etc/passwd")` raises `ValueError`
  - `test_load_invalid_uuid_no_traversal` — `load_cache("../secret")` raises `ValueError` without touching the filesystem outside cache dir
  - `test_load_missing_raises_file_not_found` — `load_cache("00000000-0000-4000-8000-000000000000")` (valid format, no file) raises `FileNotFoundError`
  - `test_load_expired_raises_runtime_error` — save, backdate mtime by 25 hours, load raises `RuntimeError` containing "expired"
  - `test_cleanup_removes_old_files` — write two files: one 25h old (backdated mtime), one fresh; `cleanup_stale_cache()` removes only the old one, returns `1`
  - `test_cleanup_returns_zero_when_nothing_stale` — fresh cache dir → returns `0`
  - `test_cache_file_permissions` — saved file has `stat.S_IMODE(os.stat(path).st_mode) == 0o600`
  
  Confirm all fail: `save_cache`, `load_cache`, `cleanup_stale_cache` do not exist.

- [ ] **GREEN:** Implement the three functions. Key decisions:
  - `save_cache`: `uuid.uuid4()`, create `_CACHE_DIR` if absent (`0o700`), write JSON via `json.dumps`, `os.chmod(path, 0o600)`
  - `load_cache`: validate UUID with `re.fullmatch(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$', cache_id)`, check age vs `_CACHE_TTL_SECONDS`
  - `cleanup_stale_cache`: `Path(_CACHE_DIR).glob("*")`, `os.stat().st_mtime`, unlink if stale

- [ ] **REFACTOR:** Extract `_validate_cache_id(cache_id)` if the format check is reused.

**Verification criteria:**
- [ ] All `TestCacheSubsystem` tests pass
- [ ] A `cache_id` containing `..` or `/` never produces a file access outside `_CACHE_DIR`
- [ ] Cache dir is only created when first needed (not at import time)
- **Files:** `server.py`, `tests/test_server.py`

---

### 4.5 — Tool schema updates: `build_tools()` and handler signatures

**Purpose:** Expose `pipe`, `cache`, `cache_id` in every tool's `inputSchema` so MCP clients (including Claude Code) can discover and use them. Update `_create_tool_handler()`, `handler_with_args`, and `handler_no_args` to accept and thread these parameters to `_run()`.

**References:**
- `server.py:189-211` — `build_tools()` constructs `inputSchema` per command
- `server.py:219-316` — `_create_tool_handler()`, `handler_with_args`, `handler_no_args`
- SPECS.md §1.2 — `tools/list` response schema

**Schema additions (to both `allow_extra_args` branches):**
```json
"pipe": {
  "type": "string",
  "description": "Filter output: 2>&1 | grep [-EinABC] 'pat' | head/tail N. Example: \"2>&1 | grep -iA 5 'FAILED' | tail 100\""
},
"cache": {
  "type": "boolean",
  "description": "Cache full output; returns cache_id for reuse"
},
"cache_id": {
  "type": "string",
  "description": "UUID from prior result — skips re-execution, applies pipe to cached output"
}
```

**TDD:**

- [ ] **RED:** In `TestBuildTools`, add:
  - `test_pipe_param_in_schema` — every tool's `inputSchema.properties` contains `pipe` with `type: string`
  - `test_cache_param_in_schema` — every tool's `inputSchema.properties` contains `cache` with `type: boolean`
  - `test_cache_id_param_in_schema` — every tool's `inputSchema.properties` contains `cache_id` with `type: string`
  - `test_existing_schema_structure_unchanged` — `allow_extra_args=True` still includes `args`; `allow_extra_args=False` still has no `args` key
  
  In `TestToolHandlers`, add:
  - `test_handler_accepts_pipe_param` — calling handler with `pipe="head 1"` does not raise a `TypeError`
  - `test_handler_accepts_cache_param` — calling handler with `cache=True` does not raise a `TypeError`
  - `test_handler_accepts_cache_id_param` — calling with a valid `cache_id` does not raise `TypeError` (use a pre-seeded cache entry)
  
  Confirm new tests fail.

- [ ] **GREEN:** Update `build_tools()` to include the three new schema properties in both schema branches. Update `handler_with_args` and `handler_no_args` signatures to accept `pipe: str | None = None`, `cache: bool = False`, `cache_id: str | None = None`, forwarding all three to `_run()`.

- [ ] **REFACTOR:** If the three new properties are repeated in both schema branches, extract a `_filter_schema_properties() -> dict` helper and merge.

**Verification criteria:**
- [ ] All `TestBuildTools` tests pass, including new ones
- [ ] All existing `TestToolHandlers` tests still pass (no regressions)
- [ ] `handler_no_args` (no `allow_extra_args`) correctly accepts the three new params without exposing an `args` param
- **Files:** `server.py`, `tests/test_server.py`

---

### 4.6 — Handler integration: `_run()` wires pipe + cache

**Purpose:** Extend `_run()` to accept the three new parameters and implement the two execution paths: (a) normal execution with optional pipe filter and optional cache write; (b) cache lookup with optional pipe filter. Log entries are extended to record `cache_id` usage where relevant.

**References:**
- `server.py:225-301` — `_run()` full implementation
- Tasks 4.2, 4.3, 4.4 — `parse_pipe()`, `apply_pipe()`, `save_cache()`, `load_cache()`
- `server.py:59-72` — `LogEntry` model (may need `cache_id` field — decide at implementation)

**Execution paths:**

```
cache_id provided:
  load_cache(cache_id) → get (stdout, stderr, exit_code, age_ms)
  if pipe: parse_pipe → apply_pipe → collect warnings
  return CommandResult(stdout, stderr, exit_code, warnings, cache_id, cache_age_ms=age_ms)
  [does NOT acquire the concurrency lock — no subprocess]

cache_id absent:
  acquire lock (existing busy-rejection logic unchanged)
  validate_args (unchanged)
  execute_command → CommandResult(stdout, stderr, exit_code)
  if pipe: parse_pipe → apply_pipe → collect warnings; apply to result
  if cache=True: save_cache(raw stdout, raw stderr, exit_code) → uuid
  release lock
  return CommandResult(filtered_stdout, filtered_stderr, exit_code, warnings, cache_id=uuid if cache else None)
```

**TDD:**

- [ ] **RED:** Add `TestPipeIntegration` class (async, uses `_create_tool_handler` like `TestToolHandlers`):
  - `test_pipe_head_truncates_output` — command produces multi-line stdout; `pipe="head 2"` returns first 2 lines only
  - `test_pipe_grep_filters_lines` — command stdout has mixed lines; `grep "PASS"` returns only matching lines
  - `test_pipe_stream_merge` — command has both stdout and stderr; `2>&1` combines them into stdout
  - `test_pipe_warnings_in_result` — `pipe="grep -i 'pat'"` returns `warnings` containing the `-i` warning
  - `test_pipe_invalid_command_raises` — `pipe="awk '{print}'"` → `isError: true` response
  - `test_cache_true_returns_cache_id` — `cache=True` → result JSON contains `cache_id` (UUID format)
  - `test_cache_id_skips_execution` — save a cache entry manually; call handler with only `cache_id` and `pipe="head 1"`; result contains filtered output from cache, `cache_age_ms` is present, lock is NOT acquired
  - `test_cache_id_no_pipe_returns_raw` — `cache_id` with no `pipe` returns the full cached stdout
  - `test_cache_id_expired_returns_error` — expired cache entry → `isError: true`, message contains "expired"
  - `test_cache_id_invalid_format_returns_error` — `cache_id="../../etc"` → `isError: true`
  - `test_pipe_regex_timeout_warning_in_result` — (slow regex, long input) timeout warning appears in `warnings`
  - `test_normal_path_unaffected` — no `pipe`, no `cache`, no `cache_id` → result identical to existing tests (backward compat)

  Confirm all fail.

- [ ] **GREEN:** Extend `_run()` signature to `async def _run(args, pipe=None, cache=False, cache_id=None)`. Implement both execution paths as documented above.

- [ ] **REFACTOR:** If `_run()` exceeds ~80 lines, extract `_run_from_cache()` and `_run_execute()` as private helpers. Keep lock acquisition/release exclusively in `_run_execute()`.

**Verification criteria:**
- [ ] All `TestPipeIntegration` tests pass
- [ ] All pre-existing `TestToolHandlers` tests still pass (backward compat)
- [ ] `cache_id` path never acquires `_lock` — verify via `TestPipeIntegration.test_cache_id_skips_execution` by asserting `_lock.locked()` is False throughout
- [ ] `LogEntry` records cache_id usage if field is added; otherwise document why it was intentionally omitted
- **Files:** `server.py`, `tests/test_server.py`

---

### 4.7 — Background cache cleanup task and `main()` wiring

**Purpose:** Start a long-lived asyncio task in `main()` that periodically calls `cleanup_stale_cache()` so cache files are removed automatically after 24 hours without blocking the request path.

**References:**
- `server.py:334-347` — `main()` startup sequence
- Task 4.4 — `cleanup_stale_cache()`

**Interface:**
```python
async def _cache_cleanup_loop(interval_seconds: int = 3600) -> None:
    """Run cleanup_stale_cache() every interval_seconds. Never raises."""
```

**TDD:**

- [ ] **RED:** Add tests in `TestCacheSubsystem` (or a new `TestCacheCleanupLoop`):
  - `test_cleanup_loop_calls_cleanup` — mock `cleanup_stale_cache`; run `_cache_cleanup_loop` for two ticks with a very short interval; assert it was called at least twice
  - `test_cleanup_loop_swallows_exceptions` — `cleanup_stale_cache` raises; loop continues without propagating the exception
  - `test_main_starts_cleanup_task` — mock `mcp.run` so it returns immediately; assert `_cache_cleanup_loop` was scheduled as a task (check `asyncio.all_tasks()` or mock `asyncio.create_task`)
  
  Confirm tests fail.

- [ ] **GREEN:** Implement `_cache_cleanup_loop()`. In `main()`, add `asyncio.create_task(_cache_cleanup_loop())` before `mcp.run(...)`.

- [ ] **REFACTOR:** N/A — function is small by design.

**Verification criteria:**
- [ ] All three new cleanup-loop tests pass
- [ ] `make test` — full suite passes
- [ ] `make lint` and `make typecheck` pass with no new errors
- [ ] `_cache_cleanup_loop` is a top-level function (not nested in `main`) so it is independently testable
- **Files:** `server.py`, `tests/test_server.py`

---

## Pre-PR checklist

Run before opening Phase 4 PR:

- [ ] `make test` — all tests pass (count should grow by ~55-65 new tests)
- [ ] `make lint` — no ruff errors
- [ ] `make typecheck` — no mypy errors
- [ ] Backward compatibility: a tool call with no `pipe`/`cache`/`cache_id` returns the same JSON shape as Phase 3
- [ ] SPECS.md §1.3 and §6.1 updated to reflect new `CommandResult` fields and new tool schema parameters
- [ ] CHANGELOG.md entry added
