<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" 
            srcset="https://raw.githubusercontent.com/yurivski/DriftBrake/main/docs/img/db_banner_dark.svg">
    <img alt="DriftBrake-Banner" 
         src="https://raw.githubusercontent.com/yurivski/DriftBrake/main/docs/img/db_banner_white.svg" 
         width="560">
  </picture>
</div>

-----------------
<br>

<div align="center">

**DriftBrake reads the current PostgreSQL schema automatically, compares it against a versioned contract, classifies drifts by impact (BREAKING, WARNING, SAFE), and blocks pipelines when incompatible changes are detected, before they cause failures in production.**

</div>

> [!NOTE]
> - Reads the PostgreSQL schema
> - Compares it against a contract
> - Classifies changes by impact
> - Blocks pipelines on breaking changes
> - Generates JSON, HTML, and Markdown reports

<br>

> **Looking for classification rules?** See [`AUDIT.md`](AUDIT.md) — independent reference for every SAFE / WARNING / BREAKING decision, including the type compatibility matrix and `possible_rename` heuristic.

<br>

<div align="center">

### Shortcut by category: click the underlined title to expand.

</div>

<details>
<summary><b><code>API VERSIONS — v0.0.2 vs v0.1.0</code></b> — <i>Click here to view</i></summary>

<br>

Two APIs coexist in DriftBrake. Both are supported, fully functional, and use the same detection engine. The difference is in interface, output style, and extensibility.

### v0.0.2 API — `SchemaGuard`

The original API. Still available and unchanged. Existing pipelines keep working without modification.

| | |
|---|---|
| **Primary entry point** | `SchemaGuard.from_env(contract_path=...).assert_compatible()` |
| **Output style** | Verbose Rich panels, formatted tables (uses the `rich` library) |
| **Result object** | `DiffResult` — from `guard.check()` |
| **Configuration** | `driftbrake.yml` (YAML, `fail_on`, `tables.ignore`, `columns.ignore`) |
| **Constructor** | `SchemaGuard(database_url=..., contract_path=..., config_path=..., output_json=..., fail_on=[...])` |
| **Low-level entry** | `guard.check()` → `DiffResult` |
| **High-level entry** | `guard.assert_compatible()` → `sys.exit` on failure |

### v0.1.0 API — `DriftBrake`

The new facade. Designed for embedding in Python pipelines with concise output, policy overrides, custom reporters, and async support.

| | |
|---|---|
| **Primary entry points** | `DriftBrake.run_from_env()` or `DriftBrake.from_env().protect()` |
| **Output style** | Concise prefixed log lines: `[INFO]`, `[WARN]`, `[BLOCKED]` |
| **Result object** | `DiffResult` — from `evaluate()` or `protect()` |
| **Configuration** | `driftbrake.policy.yml` (`overrides`, `ignore_tables`, `ignore_columns`) |
| **Constructor** | `DriftBrake(database_url=..., policy=..., reporter=..., interactive=...)` |
| **Entry points** | `evaluate()`, `protect()`, `protect_or_exit()`, `run_from_env()` |

> [!NOTE]
> `DriftBrake` uses `SchemaGuard` internally. They are not competing implementations — `DriftBrake` is a higher-level wrapper around the same comparison engine.

---
</details>

<br>

<details>
<summary><b><code>INSTALLATION</code></b> — <i>Click here to view</i></summary>

#### Scenarios

DriftBrake supports three install paths depending on what you want to do.

**1. Bare install (CLI loads, database commands fail with a clear error):**

```bash
pip install driftbrake
```

The CLI is available immediately. Any command that touches the database (e.g. `driftbrake init`, `driftbrake check`) will fail with a clear error message pointing to the missing `psycopg2` driver. Use this only if you want to inspect the CLI options before committing to the full install.

**2. Full install — CLI and library, real usage (most common):**

```bash
pip install "driftbrake[postgres]"
```

The `[postgres]` extra installs `psycopg2-binary`, the driver needed to read a PostgreSQL database. This is what you want for every real use case — CLI or library.

**3. Development (contributing or local hacking):**

```bash
git clone https://github.com/yurivski/DriftBrake
cd DriftBrake
pip install -e ".[postgres,dev]"
pre-commit install
```

The `[dev]` extra adds `pytest`, `ruff`, `mypy`, `build`, `twine`, and `pre-commit`.

<br>

Verify the installation:

```bash
driftbrake --help
driftbrake --version
```

```
DriftBrake 0.1.0
```

> [!NOTE]
> If you `pip install driftbrake` without `[postgres]`, the CLI loads but the first command that touches the database fails with a clear error pointing to the missing driver. The error is intentional and descriptive, not a bug.

---
</details>

<br>

<details>
<summary><b><code>Quick reference by situation</code></b> — <i>Click here to view</i></summary>

<br>

| Situation | Command |
|---|---|
| Using the tool for the first time | `driftbrake init` |
| Verify whether the database changed before running the pipeline | `driftbrake check` |
| Compare two states without touching the contract | `driftbrake diff --old file1.json --new file2.json` |
| Save the current database state as a future reference | `driftbrake snapshot --output snapshots/name.json` |
| A migration was applied and the changes are intentional | `driftbrake update-contract --yes` |
| View the change report in HTML | `driftbrake check --html report.html` |
| Embed protection inside a Python pipeline | `from driftbrake import DriftBrake; DriftBrake.run_from_env()` |


### CLI commands at a glance

| Command | Description |
|---|---|
| `driftbrake init` | Generate `schema.lock.json` from the current database |
| `driftbrake check` | Compare the database against the contract and return an exit code |
| `driftbrake diff` | Compare two JSON files or a JSON file against the database |
| `driftbrake snapshot` | Capture the current schema without comparing |
| `driftbrake update-contract` | Update the contract to reflect the current state |

---
</details>

<br>

<details>
<summary><b><code>Configuring your .env file</code></b> — <i>Click here to view</i></summary>

<br>

The credentials below are an example of what your `.env` should contain. They are used automatically when you don't pass `--db-url`:

| Variable | Value |
|---|---|
| `DATABASE_URL` | `postgresql://user:pass@localhost:5432/mydb` |
| `DB_HOST` | `localhost` |
| `DB_PORT` | `5432` |
| `DB_NAME` | `mydb` |
| `DB_USER` | `postgres` |
| `DB_PASSWORD` | `secrets` |

**Database access:** the tool uses SQLAlchemy under the hood. When you run any command, it assembles the connection URL in the format `postgresql://user:password@host:port/database` and uses the `psycopg2` driver to connect. SQLAlchemy then uses the `Inspector`, an internal API that queries the PostgreSQL catalog (`information_schema` and `pg_catalog`) to read metadata about tables, columns, types, constraints, and indexes. None of your row data is read — only the structure.

**Connection priority:** if `DATABASE_URL` is defined in the environment, it takes full precedence. Only when it doesn't exist does the tool build the URL from `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`.

---
</details>

<br>

<details>
<summary><b><code>Configuring the YML file</code></b> — <i>Click here to view</i></summary>

<br>

Create a `driftbrake.yml` file based on `driftbrake.example.yml`:

```yaml
fail_on:
  - BREAKING

tables:
  ignore:
    - alembic_version
    - flyway_schema_history

columns:
  ignore:
    orders:
      - updated_at
      [...]
```

Pass the file to the CLI with `--config driftbrake.yml`, or to `SchemaGuard` with `config_path="driftbrake.yml"`.

> [!WARNING]
> **`driftbrake.yml` (v0.0.2 format) is deprecated as of v0.1.1.** The nested keys `tables.ignore` / `columns.ignore` will emit a `DeprecationWarning` at load time and will be removed in v0.2.0. Migrate to `driftbrake.policy.yml` with the flat keys `ignore_tables` / `ignore_columns`. See the [Policy files](#policy-files) section below.

> For the new policy file format used by the `DriftBrake` facade (`driftbrake.policy.yml` with `overrides`, `ignore_tables`, `ignore_columns`), see the [Policy files](#policy-files) section below.

---
</details>


<br>

<details>
<summary><b><code>Database connection</code></b> — <i>Click here to view</i></summary>

<br>

The tool accepts the database URL in three ways, in order of precedence:

**1. Direct CLI argument:**

```bash
driftbrake check --db-url "postgresql://user:pass@localhost:5432/mydb"
```

**2. Environment variable `DATABASE_URL`:**

```bash
export DATABASE_URL="postgresql://user:pass@localhost:5432/mydb"
driftbrake check
```

**3. Individual variables in `.env` or environment:**

```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mydb
DB_USER=postgres
DB_PASSWORD=secret
```

---
</details>

<br>

<details>
<summary><b><code>Commands and example outputs</code></b> — <i>Click here to view</i></summary>

<br>

### 0. `--version` and `--info` — Check version and environment

#### `driftbrake --version`

Displays the installed DriftBrake version and exits.

```bash
driftbrake --version
```

```
DriftBrake 0.1.0
```

<br>

#### `driftbrake --info`

Displays full information about the runtime environment and exits. Useful when reporting issues.

```bash
driftbrake --info
```

```
DriftBrake 0.1.0
Python 3.13.5
Platform Linux-6.5.0-parrot7-amd64
SQLAlchemy 2.0.49
```

<br>

---

### 1. `init` — Create the contract for the first time

Connects to your PostgreSQL, reads the complete database structure (tables, columns, types, constraints, indexes), and saves everything to a JSON file. That file becomes the contract — a "snapshot" of the current database state.

**First run:** without a contract, there's nothing to compare against. `init` is always the starting point. You run it once, commit the file to git, and from then on any database change can be detected. `init` comes before everything because it *creates* the reference point. It makes no sense to run `check` without a contract.

#### `driftbrake init`

Connects to the database, reads the current schema, and creates the contract `schema.lock.json`. This file should be versioned in Git.

```bash
driftbrake init \
  --db-url "$DATABASE_URL" \
  --schemas public \
  --output schema.lock.json
```

<br>

**Options:**

| Option | Default | What it does |
|---|---|---|
| `--db-url` | reads from `.env` | Full PostgreSQL connection URL |
| `--schemas` | `public` | Which PostgreSQL schemas to capture. Separate with commas for multiple |
| `--output` | `schema.lock.json` | Name and path of the generated contract file |

**Exit codes:** `0` success, `3` connection error, `6` filesystem write error.

<br>

```bash
# Simplest form — uses .env variables automatically
driftbrake init

# Explicitly specifying the database
driftbrake init --db-url "postgresql://user:pass@localhost:5432/mydb"

# Capturing specific schemas (besides public)
driftbrake init --schemas "public,analytics,staging"

# Saving the contract to a different path
driftbrake init --output "contracts/production_schema.lock.json"

# All together
driftbrake init \
  --db-url "postgresql://user:pass@localhost:5432/mydb" \
  --schemas "public" \
  --output "schema.lock.json"
```

<br>

**Example of the generated file:**
```json
{
  "contract_version": "1.0",
  "generated_by": "driftbrake",
  "driftbrake_version": "0.1.0",
  "database_type": "postgresql",
  "generated_at": "2026-05-19T10:30:00",
  "schemas": {
    "public": {
      "tables": {
        "users": {
          "columns": {
            "id": { "type": "INTEGER", "nullable": false, "primary_key": true },
            "name": { "type": "VARCHAR", "nullable": true }
          },
          "indexes": ["users_pkey"],
          "check_constraints": []
        }
      }
    }
  }
}
```

<br>

**Possible outputs:**
```
Connecting to the database and reading the schema (public)...
[OK] Schema contract saved to: schema.lock.json
     12 table(s) captured across 1 schema(s).
```

<br>

### 2. `check` — Verify whether the database has changed

Reads the current database and compares it to the existing contract (`schema.lock.json`). Lists every difference found, classifies each by severity, and returns an exit code suitable for CI/CD pipelines.

**Routine command:** `check` is the heart of the tool. You run it before any pipeline, migration, or deploy. If it returns exit code 0, you're good. If it returns 2, something critical has changed and the pipeline should be blocked.

**Compare contract → database (not database → database):** the contract represents the *agreed-upon* state of the database. Comparing against it lets you detect deviations from what was planned, regardless of when or how the change happened.

#### `driftbrake check`

Compares the current database against the contract. This is the central command for use in CI/CD.

```bash
driftbrake check \
  --db-url "$DATABASE_URL" \
  --contract schema.lock.json \
  --fail-on BREAKING \
  --json schema_diff.json \
  --html schema_report.html \
  --markdown schema_report.md
```

<br>

**Options:**

| Option | Default | What it does |
|---|---|---|
| `--db-url` | reads from `.env` | PostgreSQL connection URL |
| `--contract` | `schema.lock.json` | Path to the contract file to compare against |
| `--fail-on` | `BREAKING` | Levels that trigger exit code 2. Use `BREAKING,WARNING` to be stricter |
| `--json` | — | Path to save a JSON report |
| `--html` | — | Path to save an HTML report (visual, with colored tables) |
| `--markdown` | — | Path to save a Markdown report |
| `--config` | — | YAML file with additional settings (table exclusions, etc.) |

**Exit codes:** see the [Exit Codes section below](#exit-codes) for the full mapping.

<br>

```bash
# Simplest form — uses schema.lock.json in the current directory and .env variables
driftbrake check

# Specifying everything
driftbrake check \
  --db-url "postgresql://user:pass@localhost:5432/mydb" \
  --contract "schema.lock.json"

# Fail on warnings too (stricter)
driftbrake check --fail-on "BREAKING,WARNING"

# Generate reports alongside terminal output
driftbrake check \
  --json "reports/diff.json" \
  --html "reports/diff.html" \
  --markdown "reports/diff.md"

# Using a configuration file (yml)
driftbrake check --config "driftbrake.yml"

# Full command for CI use
driftbrake check \
  --db-url "postgresql://user:pass@localhost:5432/mydb" \
  --contract "schema.lock.json" \
  --fail-on "BREAKING" \
  --html "reports/diff.html"
```

<br>

**Practical example (compatible schema):**

```bash
driftbrake check --db-url "$DATABASE_URL" --contract schema.lock.json
```

```
Connecting to the database... OK
Comparing against schema.lock.json...

DRIFTBRAKE CHECK PASSED

Summary:
  BREAKING: 0
  WARNING:  0
  SAFE:     0

No changes detected. Pipeline cleared.
```

<br>

**Practical example (breaking change detected):**

```bash
driftbrake check \
  --db-url "$DATABASE_URL" \
  --contract schema.lock.json \
  --fail-on BREAKING \
  --json schema_diff.json \
  --html schema_report.html
```

```
Connecting to the database... OK
Comparing against schema.lock.json...

DRIFTBRAKE CHECK FAILED

Summary:
  BREAKING: 2
  WARNING:  1
  SAFE:     1

BREAKING
  public.customers    email              column removed
  public.orders       total_amount       type changed: numeric → text

WARNING
  public.orders       customer_id        foreign key added

SAFE
  public.customers    created_at         nullable column added

JSON:  schema_diff.json
HTML:  schema_report.html

Pipeline blocked. (exit code 2)
```

<br>

### 3. `diff` — Compare two schema versions without using the contract

Freely compares two schema sources: two JSON files, or a JSON file against a live database. It neither uses nor modifies `schema.lock.json`. It's an ad-hoc, exploratory comparison.

**Distinct from `check`:** `check` has a specific role — validate the database against the official contract. `diff` is more flexible: you can compare yesterday's snapshot to today's database, or two files from different environments (production and staging) without affecting the contract.

#### `driftbrake diff`

**File vs file:**

```bash
driftbrake diff \
  --old schema_before.json \
  --new schema_after.json \
  --json schema_diff.json
```

<br>

**File vs live database:**

```bash
driftbrake diff \
  --old schema.lock.json \
  --new-db "$DATABASE_URL" \
  --html schema_diff.html
```

<br>

**Options:**

| Option | Default | What it does |
|---|---|---|
| `--old` | required | Path to the JSON file representing the "expected" / "before" state |
| `--new` | — | Path to the JSON file representing the "current" / "after" state |
| `--new-db` | — | Database URL to use as the "current" state (alternative to `--new`) |
| `--json` | — | Path to save the JSON report |
| `--html` | — | Path to save the HTML report |

> [!CAUTION]
> You must pass either `--new` **or** `--new-db`, never both at the same time. If neither is passed, the tool returns an error.

<br>

### 4. `snapshot` — Capture a snapshot of the database without creating a contract

Connects to the database, reads the schema, and saves it to a JSON file — just like `init`, but with a different default filename (`schema.snapshot.json`) and without the intent of being the official contract.

**Purpose:** `init` creates the official contract of the project. `snapshot` is for keeping intermediate states — "how the database looked Friday before the migration," "state of the staging database," "version before the deploy." These files can later be used as `--old` in `diff` to investigate what changed.

#### `driftbrake snapshot`

```bash
driftbrake snapshot \
  --db-url "$DATABASE_URL" \
  --output history/schema_2026-05-19.json \
  --schemas public
```

<br>

**Options:**

| Option | Default | What it does |
|---|---|---|
| `--db-url` | reads from `.env` | PostgreSQL connection URL |
| `--output` | `schema.snapshot.json` | Path of the generated snapshot file |
| `--schemas` | `public` | PostgreSQL schemas to capture |

> [!NOTE]
> **Usage tip:** creating a snapshot before every migration is good practice. If anything goes wrong, you can run a `diff` to see exactly what changed.

<br>

### 5. `update-contract` — Accept the changes and update the contract

Reconnects to the database, reads the current schema, and overwrites `schema.lock.json` with this new state. In other words: "I'm aware of the changes, they are intentional, and I want them to become the new contract." When a change is planned and approved — a legitimate migration, a deliberate schema refactor — the contract needs to be updated to reflect the new state. Without this command, `check` would keep reporting the changes forever as if they were problems.

**Interactive confirmation:** overwriting the contract is irreversible without git. The confirmation exists as protection against accidental runs.

**`--yes` flag:** in CI/CD environments there is no interactive terminal. `--yes` (or `-y`) skips the confirmation so the command can run in automated scripts after human approval in the review process.

#### `driftbrake update-contract`

```bash
driftbrake update-contract \
  --db-url "$DATABASE_URL" \
  --contract schema.lock.json \
  --yes
```

<br>

**Options:**

| Option | Default | What it does |
|---|---|---|
| `--db-url` | reads from `.env` | PostgreSQL connection URL |
| `--contract` | `schema.lock.json` | Path to the contract to overwrite |
| `--yes` / `-y` | `false` | Skips the confirmation prompt |
| `--schemas` | `public` | Schemas to capture for the new contract |

> [!WARNING]
> Without `--yes`, the command asks for explicit confirmation before overwriting the contract.

---
</details>

<br>

<details>
<summary><b><code>Exit Codes</code></b> — <i>Click here to view</i></summary>

<br>

DriftBrake uses deterministic exit codes so CI/CD can decide success or failure based exclusively on the exit code.

| Code | Meaning | When it happens |
|---|---|---|
| `0` | Success — schema compatible or operation completed | `check` found no changes, or all changes are below the `--fail-on` threshold |
| `1` | Generic DriftBrake error | Base catch-all; specific subclasses below |
| `2` | Critical change detected — pipeline should be blocked | `check` found changes that match `--fail-on` |
| `3` | Database connection error | Wrong host/port/password, server unreachable, network issue |
| `4` | Contract missing or invalid | File not found, malformed JSON, missing required fields |
| `5` | Configuration error | Invalid YAML, policy syntax error, missing `DATABASE_URL`, schema configured but not in database |
| `6` | Filesystem write error | Can't write the contract file (read-only filesystem, permission denied) |
| `7` | User aborted | Interactive prompt got a "no" answer |

> [!NOTE]
> Every Python exception raised by the library maps to one of these codes. See the [Exception hierarchy](#exception-hierarchy) section for the full mapping.

---
</details>

<br>

<details>
<summary><b><code>Development shortcuts</code></b> — <i>Click here to view</i></summary>

<br>

The repository ships with a `Makefile` for common tasks:

```bash
pip install -e ".[dev]"
make test       # run all tests
make lint       # check style
make check      # lint + typecheck + tests
```

---
</details>

<br>

<details>
<summary><b><code>Contract format</code></b> — <i>Click here to view</i></summary>

<br>

The contract is generated by `init` and should be versioned in Git. It represents the schema the pipeline expects to find.

```json
{
  "contract_version": "1.0",
  "generated_by": "driftbrake",
  "driftbrake_version": "0.1.0",
  "database_type": "postgresql",
  "generated_at": "2026-05-19T10:30:00",
  "schemas": {
    "public": {
      "tables": {
        "customers": {
          "columns": {
            "id": {
              "type": "integer",
              "nullable": false,
              "default": null,
              "primary_key": true,
              "unique": false,
              "foreign_key": false,
              "ordinal_position": 1
            },
            "email": {
              "type": "text",
              "nullable": false,
              "default": null,
              "primary_key": false,
              "unique": true,
              "foreign_key": false,
              "ordinal_position": 2
            }
          }
        }
      }
    }
  }
}
```

---
</details>

<br>

<details>
<summary><b><code>Report formats: JSON, HTML, and Markdown</code></b> — <i>Click here to view</i></summary>

<br>

### JSON (`--json schema_diff.json`)

The JSON report wraps a list of `SchemaChange` objects serialized via `SchemaChange.to_dict()`. The real field names are:

```json
{
  "status": "failed",
  "checked_at": "2026-05-19T10:30:00",
  "database_type": "postgresql",
  "summary": { "breaking": 2, "warning": 1, "safe": 3 },
  "changes": [
    {
      "change_type": "column_removed",
      "severity": "BREAKING",
      "schema_name": "public",
      "table_name": "customers",
      "column_name": "email",
      "field_name": null,
      "old_value": "email",
      "new_value": null,
      "description": "Column 'email' was removed from 'customers'.",
      "suggestion": null
    }
  ]
}
```

**Field reference for a single change object:**

| Field | Type | Description |
|---|---|---|
| `change_type` | string | The `ChangeType` enum value, e.g. `"column_removed"`, `"type_changed"` |
| `severity` | string | `"BREAKING"`, `"WARNING"`, or `"SAFE"` |
| `schema_name` | string | PostgreSQL schema, e.g. `"public"` |
| `table_name` | string | Table where the change was detected |
| `column_name` | string or null | Column name (null for table-level changes) |
| `field_name` | string or null | Sub-field within the column that changed (e.g. `"nullable"`) |
| `old_value` | string or null | Previous value, stringified |
| `new_value` | string or null | New value, stringified |
| `description` | string | Human-readable description of the change |
| `suggestion` | string or null | Optional remediation hint |
| `confidence` | string or null | Only present for `possible_rename`: `"low"`, `"medium"`, or `"high"` |

### HTML (`--html schema_report.html`)

A visual report with a general summary, inspired by ydata-profiling (formerly *Pandas Profiling*). Uses the templates in `templates/`.

### Markdown (`--markdown schema_report.md`)

A Markdown-formatted report, suitable for automatic comments on pull requests.

---
</details>

<br>

---

<div align="center">

## CLI and Library

</div>

DriftBrake gives you two doors into the same engine: a command-line tool and a Python library. Same detection, same classification, same reports. They differ in **how you integrate them**.

### Use the CLI when…

- Your pipeline is a shell script, a Makefile, or a CI job written in YAML (GitHub Actions, GitLab CI, Jenkins).
- You want to run drift checks manually from your terminal during code review.
- You're calling it as a standalone gate before unrelated tools execute: `driftbrake check && dbt run && python publish.py`.
- The database lives in one place and the pipeline runs in another — the CLI's exit code is the contract between them.
- You're getting started and want to learn the tool by typing commands.

### Use the library when…

- Your pipeline is already a Python program (Airflow DAG, Prefect flow, Dagster job, standalone script).
- You want to inspect results before reacting — log to Slack, write to your own observability stack, run custom logic based on which tables changed.
- You need a custom reporter or prompter (JSON-structured logs, a Slack approval flow, a silent reporter for tests).
- You want policy overrides applied programmatically based on the environment (staging vs. production).
- You need async support inside an `async def` pipeline.

### Mental shortcut

If your pipeline is **shell-shaped**, use the CLI. If it's **Python-shaped**, use the library. There's no functional limit either way — pick what makes your pipeline read cleanly.

### Quick comparison

| Aspect | CLI | Library |
|---|---|---|
| Setup cost | `pip install` + `driftbrake init` | `pip install` + 3 lines of Python |
| Output style | Verbose, Rich panels, formatted tables | Concise prefixed log lines (`[INFO]`, `[WARN]`, `[BLOCKED]`) |
| Customization | YAML config | Anything Python can do |
| Async | Not applicable | `aprotect()`, `aprotect_or_exit()` |
| Custom reporter | Not supported | Full `Reporter` protocol |
| Error handling | Exit codes | Typed exceptions OR exit codes (your choice) |
| Best for | CI/CD, shell pipelines, manual review | Python pipelines, custom integrations, libraries |

<br>

---

<div align="center">

## Using DriftBrake in your Python pipeline

</div>

The `DriftBrake` class is a facade that orchestrates the full protection cycle: read the contract, scan the database, compare, classify, apply policies, decide, and report. You instantiate it once at the top of your pipeline, call one method, and that's it.

There are **four entry points** depending on how much control you want.

### Entry point 1: `DriftBrake.run_from_env()` — the one-liner

If you just want "block the pipeline on schema drift" with zero ceremony, this is the entry point:

```python
from driftbrake import DriftBrake

DriftBrake.run_from_env()
# If drift was detected and matches fail_on, the process exits here with the right code.
# If no drift, execution continues.

run_pipeline()
```

That's it. `run_from_env()` reads `DATABASE_URL` from the environment, runs the check, and translates **every** `DriftBrakeError` — including construction errors like missing env vars — into the appropriate `sys.exit(code)`. You don't see exceptions; you see exit codes.

Use this when:

- Your pipeline is a Python script that runs as a separate process (cron job, Airflow `BashOperator`, Docker entrypoint).
- You want exit-code semantics, not exception semantics.
- You don't need to inspect the result before deciding what to do.

<br>

### Entry point 2: `DriftBrake.from_env().protect()` — exception-driven

When you want to catch exceptions and react in code:

```python
from driftbrake import DriftBrake
from driftbrake.exceptions import (
    BreakingChangesDetected,
    SchemaConnectionError,
    UserAborted,
)

try:
    result = DriftBrake.from_env().protect()
except BreakingChangesDetected as e:
    notify_slack(f"Pipeline blocked: {len(e.result.changes)} breaking changes")
    raise
except SchemaConnectionError:
    notify_slack("Pipeline couldn't reach the database")
    raise
except UserAborted:
    notify_slack("User aborted interactively")
    raise

# Continue with the pipeline
run_pipeline(result)
```

`protect()` returns a `DiffResult` on success and raises typed exceptions on failure. You decide what to do with each.

Use this when:

- You're inside a larger Python program that handles its own errors.
- You want to differentiate between failure modes (connection vs. drift vs. user abort).
- You need to log/notify before re-raising.

<br>

### Entry point 3: `DriftBrake.from_env().evaluate()` — inspect before acting

When you want to see what changed *before* deciding what to do:

```python
from driftbrake import DriftBrake

db = DriftBrake.from_env()
decision, result = db.evaluate()
# Returns (Decision, DiffResult)

print(f"Decision: {decision.severity}")
print(f"Breaking: {result.breaking_count}")
print(f"Warning:  {result.warning_count}")
print(f"Safe:     {result.safe_count}")

# Branch on what was found
if result.breaking_count > 0:
    handle_breaking(result)
elif result.warning_count > 5:
    handle_many_warnings(result)
else:
    run_pipeline()
```

`evaluate()` is the pure decision pass — no exceptions, no prompts, no printing. Just the result and the decision. Useful for dashboards, custom workflows, or when you want to render the result your own way.

The return type is `(Decision, DiffResult)`. `Decision` has `.action` (`"release"`, `"ask"`, or `"block"`), `.severity` (`"none"`, `"safe"`, `"warning"`, `"breaking"`), `.reason`, and `.exit_code`.

<br>

### Entry point 4: `DriftBrake(...)` direct construction — full control

When you need to pass policies, custom reporters, or override env values:

```python
from driftbrake import DriftBrake, TerminalReporter
from driftbrake.policy import load_policy

policy = load_policy("policies/strict.yml")

db = DriftBrake(
    database_url="postgresql://user:pass@host:5432/db",
    contract_path="contracts/production.lock.json",
    policy=policy,
    schemas=["public", "analytics"],
    fail_on=["BREAKING", "WARNING"],   # stricter than default
    ask_on=[],                          # never prompt, even interactively
    interactive=False,                  # force non-interactive
    verbose=True,                       # detailed reporter output
    reporter=TerminalReporter(verbose=True),  # explicit reporter
)

db.protect()
run_pipeline()
```

Use this when you need precise control over every parameter, e.g. different configurations per environment.

<br>

### `DriftBrake` constructor — full parameter reference

```python
DriftBrake(
    database_url: str,
    contract_path: str = "schema.lock.json",
    config_path: str | None = None,
    policy_path: str | None = None,
    auto_init: bool = True,
    interactive: bool | Literal["auto"] = "auto",
    ask_on: list[str] | None = None,    # default: ["WARNING"]
    fail_on: list[str] | None = None,   # default: ["BREAKING"]
    output_json: str | None = None,
    output_html: str | None = None,
    output_markdown: str | None = None,
    schemas: list[str] | None = None,   # default: ["public"]
    verbose: bool = False,
    reporter: Reporter | None = None,
    prompter: Prompter | None = None,
)
```

**Parameter notes:**

| Parameter | Default | Notes |
|---|---|---|
| `database_url` | required | Full PostgreSQL connection URL |
| `contract_path` | `"schema.lock.json"` | Path to the contract file |
| `config_path` | `None` | Path to `driftbrake.yml` (v0.0.2-style config, **deprecated** — emits `DeprecationWarning`) |
| `policy_path` | `None` | Path to `driftbrake.policy.yml` (v0.1.0-style policy, preferred) |
| `auto_init` | `True` | If `True`, creates the contract automatically on first run |
| `interactive` | `"auto"` | See [interactive parameter](#the-interactive-parameter) section |
| `ask_on` | `["WARNING"]` | Severities that trigger a confirmation prompt |
| `fail_on` | `["BREAKING"]` | Severities that raise `BreakingChangesDetected` |
| `output_json` | `None` | Path to save JSON report |
| `output_html` | `None` | Path to save HTML report |
| `output_markdown` | `None` | Path to save Markdown report |
| `schemas` | `["public"]` | PostgreSQL schemas to scan |
| `verbose` | `False` | Enables verbose output in the default reporter |
| `reporter` | `FacadeTerminalReporter` | Custom reporter implementing `Reporter` protocol |
| `prompter` | `StdinPrompter` or `NonInteractivePrompter` | Custom prompter implementing `Prompter` protocol |

`from_env(**kwargs)` accepts all the same kwargs except `database_url`, which it resolves from the environment. Any kwarg you pass overrides the environment-resolved value.

<br>

### The `interactive` parameter

`interactive` controls whether DriftBrake will prompt the user for confirmation on `ask_on` severities (defaults to `WARNING`). It accepts three values:

| Value | Behavior | When to use |
|---|---|---|
| `"auto"` (default) | Prompts only if both stdin and stdout are TTYs (`sys.stdin.isatty() and sys.stdout.isatty()`) | Default for code that runs in both terminals and CI — safe everywhere |
| `True` | Always prompts | Local dev when you want to be asked even when piping output |
| `False` | Never prompts; treats every ask as "no" (`NonInteractivePrompter` returns `False`) | CI/CD, cron, Docker, Airflow — anywhere there's no human |

The `"auto"` mode is what you want 99% of the time. It uses `sys.stdin.isatty()` and `sys.stdout.isatty()` to decide. In a CI job (no TTY), it resolves to `False`. In your terminal, it resolves to `True`. You don't think about it.

If you need to override per-environment:

```python
import os

is_ci = os.environ.get("CI") == "true"
db = DriftBrake.from_env(interactive=not is_ci)
```

<br>

### Async pipelines

If your pipeline is `async`, use the async variants:

```python
import asyncio
from driftbrake import DriftBrake

async def main():
    result = await DriftBrake.from_env().aprotect()
    await run_async_pipeline(result)

asyncio.run(main())
```

`aprotect()` and `aprotect_or_exit()` are wrappers over the sync versions, implemented with `asyncio.to_thread`. The scan runs in a worker thread so the event loop stays responsive — useful when your pipeline has other concurrent tasks (heartbeat, status updates, parallel queries).

<br>

### Context manager

For "run this block only if the schema is OK" semantics:

```python
from driftbrake import DriftBrake

with DriftBrake.from_env().guard_block():
    # This block only executes if the drift check passed.
    # If a breaking change is detected, the block is skipped and an exception is raised.
    run_pipeline()
```

The check happens on `__enter__`. Exceptions inside the block propagate normally (no swallowing).

<br>

### Policy files

The `DriftBrake` facade supports a policy file format with three sections:

```yaml
# driftbrake.policy.yml
overrides:
  nullable_column_added: WARNING   # default is SAFE; tighten it
  default_changed: BREAKING        # default is WARNING; make it strict
  possible_rename: BREAKING        # treat all renames as BREAKING
  ordinal_position_changed: SAFE   # relax ordinal position changes

ignore_tables:
  - alembic_version
  - flyway_schema_history

ignore_columns:
  - users.updated_at
  - orders.last_synced
```

Load and apply:

```python
from driftbrake import DriftBrake
from driftbrake.policy import load_policy

# Method 1: pass the path; DriftBrake loads it
db = DriftBrake.from_env(policy_path="driftbrake.policy.yml")

# Method 2: load explicitly, modify in code if needed, pass the object
policy = load_policy("driftbrake.policy.yml")
policy.ignore_tables.append("audit_log")  # dynamic addition
db = DriftBrake.from_env(policy=policy)
```

**How `apply_policy` works**

`apply_policy` runs as post-processing between `guard.check()` and `decide()`. It receives a `DiffResult` and a `Policy` and returns a new `DiffResult` with the adjustments applied. Three operations happen in sequence:

1. **Filter `ignore_tables`**: any change whose `table_name` is in `ignore_tables` is removed entirely from the result.
2. **Filter `ignore_columns`**: any change whose `table_name.column_name` matches an entry in `ignore_columns` is removed.
3. **Apply severity overrides**: for each remaining change, if its `change_type.value` is a key in `overrides`, the severity is replaced with the configured value and `[overridden by policy: SEVERITY]` is appended to the description (audit trail).

The override key is the `change_type.value` string (lowercase, underscore-separated):

```yaml
overrides:
  nullable_column_added: BREAKING    # key = "nullable_column_added"
  default_changed: BREAKING          # key = "default_changed"
  possible_rename: BREAKING          # key = "possible_rename"
  ordinal_position_changed: SAFE     # key = "ordinal_position_changed"
  column_added: WARNING              # key = "column_added"
  column_removed: WARNING            # key = "column_removed"
```

> [!NOTE]
> `apply_policy` is a pure function — it does not mutate the original `DiffResult`. It always returns a new object. This makes it safe to call multiple times or inspect the pre-policy result for comparison.

**Precedence: `config_path` (Settings) vs. `policy_path` (Policy)**

When both `config_path` and `policy_path` are provided, they operate at **different stages of the pipeline** and do not conflict:

| Layer | File | Applied | Effect |
|---|---|---|---|
| Settings (`config_path`) | `driftbrake.yml` | **Before** comparison | Filters tables/columns so they are never compared; controls `fail_on` / `warn_on` thresholds |
| Policy (`policy_path`) | `driftbrake.policy.yml` | **After** comparison | Removes or re-classifies changes that were already detected |

A table listed in both `tables.ignore` (Settings) and `ignore_tables` (Policy) is simply never compared — the Policy filter is a no-op for it. There is no conflict; the Settings layer wins by eliminating the change before the Policy layer sees it.

> [!WARNING]
> `config_path` (`driftbrake.yml`) is **deprecated as of v0.1.1** and will be removed in v0.2.0. Prefer `policy_path` (`driftbrake.policy.yml`) for all new integrations.

For the full classification rules that overrides modify, see [`AUDIT.md`](AUDIT.md).

<br>

### Custom reporters and prompters

The default reporter prints to the terminal with `[INFO]` / `[WARN]` / `[BLOCKED]` prefixes. To send results elsewhere (JSON logs, Slack, custom UI), implement the `Reporter` protocol.

**`Reporter` protocol (from `protocols.py`):**

```python
def on_no_drift(self, result: DiffResult) -> None
def on_safe(self, result: DiffResult) -> None
def on_warning(self, result: DiffResult) -> None
def on_breaking(self, result: DiffResult) -> None
def on_contract_missing(self, contract_path: str) -> None
def on_contract_created(self, contract_path: str) -> None
def on_released(self) -> None
def on_blocked(self, reason: str) -> None
```

**`Prompter` protocol (from `protocols.py`):**

```python
def confirm_create_contract(self, contract_path: str) -> bool
def confirm_continue_with_warnings(self, result: DiffResult) -> bool
def confirm_continue_with_safe(self, result: DiffResult) -> bool
```

**Example: structured JSON reporter**

```python
import json, sys
from driftbrake import DriftBrake

class StructuredJSONReporter:
    """Emits one JSON object per event, on stderr."""
    def _emit(self, payload):
        print(json.dumps(payload), file=sys.stderr, flush=True)

    def on_no_drift(self, r): self._emit({"event": "no_drift"})
    def on_safe(self, r): self._emit({"event": "safe", "count": r.safe_count})
    def on_warning(self, r): self._emit({"event": "warning", "count": r.warning_count})
    def on_breaking(self, r): self._emit({"event": "breaking", "count": r.breaking_count})
    def on_contract_missing(self, path): self._emit({"event": "contract_missing", "path": path})
    def on_contract_created(self, path): self._emit({"event": "contract_created", "path": path})
    def on_released(self): self._emit({"event": "released"})
    def on_blocked(self, reason): self._emit({"event": "blocked", "reason": reason})

DriftBrake.from_env(reporter=StructuredJSONReporter()).protect()
```

The same pattern works for `Prompter` (replace interactive confirmation with Slack approval, deny-by-default for security checks, etc.).

**Reporter design guidelines**

When writing a custom reporter, follow these conventions to keep behavior predictable:

- **Each `on_*` method should behave predictably, regardless of what other events fired.** Don't make `on_safe` go silent when `on_breaking` is also called. That's conditional behavior, hard for callers to reason about.
- **Verbosity belongs inside the method** (via `self.verbose`), not as a function of what other events are present in the same run.
- **Reporters do not make business decisions.** A reporter only outputs. It never decides whether to block, abort, or continue — those decisions live in `decide()` and `protect()`.
- **A silent reporter is valid** (useful for tests), but it must be intentionally silent, not accidentally silent. A reporter that suppresses output when there are breaking changes and looks like a clean run is a bug, not a feature.
- **`on_breaking` should write to stderr** (as the default `FacadeTerminalReporter` does). Breaking changes are an error condition; they belong on the error stream.
- **Event ordering**: `protect()` calls reporter events in this order: `on_safe` → `on_warning` → `on_breaking` → `on_blocked` (or `on_released`). Each event fires independently if the corresponding changes are present — there is no "only call the worst one" logic.

<br>

---

<div align="center">

## Legacy v0.0.2 API — `SchemaGuard`

</div>

The original `SchemaGuard` API is still available and unchanged. New code should prefer `DriftBrake`, but existing pipelines built on `SchemaGuard.assert_compatible()` keep working without modification.

### Simple pipeline integration (v0.0.2 style)

```python
from driftbrake import SchemaGuard

def run_pipeline():
    print("Running ETL...")

def main():
    SchemaGuard.from_env(
        contract_path="schema.lock.json",
        fail_on=["BREAKING"]
    ).assert_compatible()

    run_pipeline()

if __name__ == "__main__":
    main()
```

> [!NOTE]
> If the database contains incompatible changes, `assert_compatible()` prints the report, generates the files, and exits the process with `exit code 2`. The output style is verbose CLI-style with Rich panels — different from the concise pipeline-style output of `DriftBrake.protect()`.

<br>

### Manual construction with `SchemaGuard`

```python
from driftbrake import SchemaGuard

guard = SchemaGuard(
    database_url="postgresql://user:pass@localhost:5432/mydb",
    contract_path="schema.lock.json",
    config_path="driftbrake.yml",        # optional
    output_json="schema_diff.json",      # optional
    output_html="schema_report.html",    # optional
    output_markdown="schema_report.md",  # optional
    fail_on=["BREAKING"],
    schemas=["public", "raw"],           # optional, default: ["public"]
)

guard.assert_compatible()
run_pipeline()
```

### Inspecting the result manually

```python
from driftbrake import SchemaGuard
from driftbrake.models import Severity

guard = SchemaGuard.from_env(contract_path="schema.lock.json")
result = guard.check()  # returns DiffResult

print(f"Total changes: {len(result.changes)}")
print(f"Breaking: {result.breaking_count}")
print(f"Warning:  {result.warning_count}")
print(f"Safe:     {result.safe_count}")

for change in result.changes:
    if change.severity == Severity.BREAKING:
        print(f"  BREAKING | {change.table_name}.{change.column_name}: {change.description}")

if result.has_breaking:
    guard.save_reports(result)
    raise SystemExit(2)
```

### Using `SchemaComparator` directly

```python
from driftbrake.readers.postgres import PostgresSchemaReader
from driftbrake.readers.json_reader import JsonSchemaReader
from driftbrake.comparators.schema_comparator import SchemaComparator

expected = JsonSchemaReader("schema.lock.json").read()
current  = PostgresSchemaReader("postgresql://user:pass@host/db").read()

result = SchemaComparator().compare(expected=expected, current=current)

for change in result.changes:
    print(f"{change.severity.value:8} | {change.schema_name}.{change.table_name} | {change.description}")
```

<br>

---

<div align="center">

## Exception hierarchy

</div>

Every exception raised by DriftBrake inherits from `DriftBrakeError`. Each one carries an `exit_code` attribute that matches the [Exit Codes table](#exit-codes).

### v0.1.0 exceptions

| Exception | Exit code | When it's raised |
|---|---|---|
| `DriftBrakeError` | `1` | Base class — generic failure |
| `BreakingChangesDetected` | `2` | `protect()` detected drift matching `fail_on`. Carries the `DiffResult` on `.result` |
| `SchemaConnectionError` | `3` | Can't connect to the database (also raised through v0.1.0 path via `PostgresSchemaReader`) |
| `ContractMissingError` | `4` | Contract file not found when `auto_init=False` |
| `MissingDatabaseURL` | `5` | `DATABASE_URL` env var not set and no URL passed explicitly |
| `PolicyError` | `5` | Policy file invalid (missing, malformed YAML, unknown severity) |
| `SchemaNotFoundError` | `5` | A schema listed in `schemas=[...]` doesn't exist in the database |
| `ContractWriteError` | `6` | Can't write the contract file (permission, read-only filesystem) |
| `UserAborted` | `7` | Interactive prompt got a "no" answer |

> [!NOTE]
> `SchemaConnectionError` originates in the legacy v0.0.2 layer (`PostgresSchemaReader`) but propagates unmodified through the v0.1.0 path. Any call to `guard.check()` — whether from `SchemaGuard` or `DriftBrake` — can raise it. Catch it explicitly if you need to differentiate connection failures from drift failures.

### Legacy v0.0.2 exceptions (still raised by `SchemaGuard`)

| Exception | Exit code | When it's raised |
|---|---|---|
| `SchemaDetectorError` | `1` | Legacy base — now inherits from `DriftBrakeError` |
| `SchemaConnectionError` | `3` | Can't connect to the database |
| `SchemaContractNotFoundError` | `4` | Contract file missing or invalid JSON |
| `ConfigurationError` | `5` | Invalid configuration |
| `BreakingSchemaChangeError` | `2` | Legacy version of `BreakingChangesDetected` |

All legacy exceptions now inherit from `DriftBrakeError`. Code that catches `DriftBrakeError` catches both new and legacy errors. Code that catches specific legacy exceptions keeps working exactly as before.

### Full exception-to-exit-code mapping

| Code | Exception(s) | Origin |
|---|---|---|
| `1` | `DriftBrakeError`, `SchemaDetectorError` | Base classes |
| `2` | `BreakingChangesDetected`, `BreakingSchemaChangeError` | Breaking drift found matching `fail_on` |
| `3` | `SchemaConnectionError` | DB unreachable, wrong password, network error |
| `4` | `ContractMissingError`, `SchemaContractNotFoundError` | Contract not found or invalid JSON |
| `5` | `MissingDatabaseURL`, `PolicyError`, `ConfigurationError`, `SchemaNotFoundError` | Configuration errors |
| `6` | `ContractWriteError` | Can't write contract (permissions, read-only FS) |
| `7` | `UserAborted` | Interactive prompt answered "no" |

### Example: catching everything

```python
from driftbrake import DriftBrake
from driftbrake.exceptions import DriftBrakeError

try:
    DriftBrake.from_env().protect()
except DriftBrakeError as e:
    # Single catch covers all DriftBrake failure modes
    logger.error(f"{type(e).__name__}: {e}")
    sys.exit(e.exit_code)
```

### Example: differentiated handling

```python
from driftbrake import DriftBrake
from driftbrake.exceptions import (
    BreakingChangesDetected,
    SchemaConnectionError,
    SchemaNotFoundError,
    ContractWriteError,
)

try:
    DriftBrake.from_env().protect()
except BreakingChangesDetected as e:
    # e.result is a DiffResult
    alert_team("schema_breaking", changes=e.result.changes)
    raise
except SchemaConnectionError:
    alert_team("database_unreachable")
    raise
except SchemaNotFoundError:
    alert_team("schema_misconfigured")
    raise
except ContractWriteError:
    alert_team("filesystem_error")
    raise
```

<br>

---

<div align="center">

## How it works

</div>

```
schema.lock.json (contract versioned in Git)
        │
        ▼
DriftBrake connects to PostgreSQL
        │
        ▼
reads the current schema automatically
        │
        ▼
compares expected against current
        │
        ▼
classifies changes by severity (SAFE / WARNING / BREAKING)
        │
        ▼
applies policy overrides (if a policy file was loaded)
        │
        ▼
makes the decision (release / ask / block)
        │
        ├── release ────────────── pipeline runs
        ├── ask ────────────────── prompt user (interactive only)
        └── block ────────────────── pipeline blocked
                                    ├── displays in terminal
                                    ├── generates schema_diff.json
                                    └── generates schema_report.html
```

### Change types detected

The tool detects the following categories of change in every comparison:

| Type | What it means | Default severity |
|---|---|---|
| `table_added` | A new table appeared in the database | SAFE |
| `table_removed` | A table that existed is gone from the database | BREAKING |
| `column_added` | A new NOT NULL column was added to an existing table | WARNING (with default) / BREAKING (without default) |
| `nullable_column_added` | A new nullable column was added to an existing table | SAFE |
| `column_removed` | A column was removed from an existing table | BREAKING |
| `type_changed` | A column's data type changed (e.g. `INTEGER` → `TEXT`) | Varies — see type matrix |
| `nullable_changed` | The column stopped accepting NULL or started accepting it | BREAKING (NOT NULL added) / WARNING (NOT NULL removed) |
| `default_changed` | The column's default value changed or was removed | WARNING |
| `primary_key_changed` | A column gained or lost its primary key | BREAKING |
| `unique_changed` | A `UNIQUE` constraint was added or removed | WARNING |
| `foreign_key_changed` | A foreign key was modified | BREAKING |
| `foreign_key_added` | A foreign key was created where there was none | WARNING |
| `ordinal_position_changed` | The column's position in the table changed | WARNING |
| `possible_rename` | A column was removed and a similar one was added in the same table. The tool only flags this as a suspicion of rename, never as a confirmation. | WARNING (always) |

> [!IMPORTANT]
> For the full classification logic — *why* each change is SAFE, WARNING, or BREAKING — see [`AUDIT.md`](AUDIT.md). It's the independent reference for every classification decision.

> [!NOTE]
> `nullable_column_added` and `column_added` are **two distinct change types** with separate override keys. Adding a nullable column is always SAFE — existing queries keep working, the column defaults to NULL. Adding a NOT NULL column requires a default to be WARNING; without a default, it's BREAKING because existing inserts that don't supply the column will fail. Policy overrides can target each independently:
> ```yaml
> overrides:
>   nullable_column_added: WARNING   # tighten nullable additions
>   column_added: BREAKING           # make all NOT NULL additions strict
> ```

<br>

### `possible_rename` — detection heuristics

**How it works:** for each removed column in a table, the comparator scans all added columns in the same table looking for a best match. Matching requires **compatible types** (SAFE or WARNING in the type compatibility matrix). Incompatible types (BREAKING conversion) disqualify a column from rename detection — they get reported as separate BREAKING + SAFE/BREAKING changes instead.

**Confidence assignment:**

| Level | Criteria |
|---|---|
| `high` | Similar name + same type + `|old_pos - new_pos|` ≤ 2 |
| `medium` | Same type + `|old_pos - new_pos|` ≤ 2 |
| `low` | Only type-compatible (SAFE or WARNING in the type matrix) |

**Name similarity** (from `_names_are_similar`): a prefix match ≥ 3 characters, a suffix match ≥ 3 characters, or one name contains the other.

**Example in the JSON report:**

```json
{
  "change_type": "possible_rename",
  "severity": "WARNING",
  "schema_name": "public",
  "table_name": "customers",
  "column_name": "customer_email",
  "field_name": null,
  "old_value": "customer_email",
  "new_value": "email",
  "description": "Column 'customer_email' removed and 'email' added with compatible type. Possible rename.",
  "suggestion": "If this is a rename, update the schema contract with the new column name 'email'.",
  "confidence": "medium"
}
```

**Intentional but surprising behavior:**

- DROP `customer_email` (text) + ADD `email` (text): types are compatible → **one** `possible_rename` WARNING.
- DROP `customer_email` (text) + ADD `amount` (integer): types are incompatible (BREAKING conversion) → **two** separate changes: one BREAKING (`column_removed`) + one BREAKING or SAFE depending on nullability (`column_added` / `nullable_column_added`).

**Important rules:**

- `possible_rename` is **never** automatically classified as `BREAKING` — always `WARNING`.
- A `confidence: "high"` is still a suspicion, not a certainty.
- Always review migrations before accepting a rename with `driftbrake update-contract`.

**To force strict drop+add detection** (suppress rename heuristic entirely):

```yaml
overrides:
  possible_rename: BREAKING
```

For the full heuristic logic, see [`AUDIT.md`](AUDIT.md#the-possible_rename-heuristic).

<br>

## Typical flow after a migration:

```bash
# 1. Run the migration on the database
psql -U postgres -d mydb -f migration_001.sql

# 2. Check what changed
driftbrake check

# 3. If the changes are expected, accept them and update the contract
driftbrake update-contract --yes

# 4. Commit the new contract alongside the migration
git add schema.lock.json migration_001.sql
git commit -m "migration: add email_verified column to users table"
```

## Usage without `--db-url` (via `.env`)

In every command, `--db-url` is optional. When omitted, the tool looks for credentials in the following order:

1. Environment variable `DATABASE_URL` (highest priority)
2. Combination of `DB_HOST` + `DB_PORT` + `DB_NAME` + `DB_USER` + `DB_PASSWORD`

If you have `.env` loaded in the shell (e.g. with `source .env` or a tool like `dotenv`), you can run any command without passing credentials:

```bash
source .env
driftbrake check
driftbrake init
driftbrake snapshot
```

Or simply run from inside the project directory — many tools (such as `uv run`, `direnv`, `docker-compose`) load `.env` automatically.

<br>

## Default severity reference (summary)

The tables below summarize the default severity for each change type. For the full reasoning behind each classification, see [`AUDIT.md`](AUDIT.md).

### Tables

| Drifts | Default severity |
|---|---|
| Table removed | BREAKING |
| Table added | SAFE |

### Columns

| Drifts | Default severity |
|---|---|
| Column removed | BREAKING |
| Column added — nullable (`nullable_column_added`) | SAFE |
| Column added — NOT NULL without default (`column_added`) | BREAKING |
| Column added — NOT NULL with default (`column_added`) | WARNING |
| NOT NULL added | BREAKING |
| NOT NULL removed | WARNING |
| Default changed | WARNING |
| Primary key changed | BREAKING |
| Unique constraint changed | WARNING |
| Foreign key added | WARNING |
| Foreign key changed | BREAKING |
| Ordinal position changed | WARNING |
| Possible rename detected | WARNING |

> [!NOTE]
> `column_added` covers two sub-cases: NOT NULL **with** default (WARNING) and NOT NULL **without** default (BREAKING). The distinction is made at comparison time based on the column's `default` field in the schema. Both use the same `change_type` value (`"column_added"`) and share a single override key. `nullable_column_added` is always SAFE and has its own separate override key.

### PostgreSQL types (compatibility matrix excerpt)

| Conversion | Severity |
|---|---|
| `varchar(50)` → `varchar(100)` | SAFE |
| `varchar(100)` → `varchar(50)` | BREAKING |
| `text` → `varchar(n)` | BREAKING |
| `varchar(n)` → `text` | SAFE |
| `integer` → `bigint` | WARNING |
| `bigint` → `integer` | BREAKING |
| `smallint` → `integer` | SAFE |
| `numeric(10,2)` → `numeric(12,2)` | SAFE |
| `numeric(12,2)` → `numeric(10,2)` | BREAKING |
| `numeric` → `text` | BREAKING |
| `date` → `timestamp` | WARNING |
| `timestamp` → `date` | BREAKING |

See [`AUDIT.md`](AUDIT.md) for the complete matrix and the reasoning behind each entry.

---
<br>

## Stack

- **SQLAlchemy** — PostgreSQL reflection/inspection
- **Typer** — CLI
- **Rich** — terminal output
- **Jinja2** — HTML templates
- **python-dotenv** — environment variables
- **PyYAML** — configuration and policy files
- **pytest** — tests

## License

**MIT license**

## Author

**Yuri Pontes** — Former Cabo (Corporal equivalent) - Brazilian Army, transitioning to data engineering.

[LinkedIn](https://www.linkedin.com/in/yuri-pontes-4ba24a345/) · [GitHub](https://github.com/yurivski)
