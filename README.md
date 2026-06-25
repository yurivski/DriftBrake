<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" 
            srcset="https://raw.githubusercontent.com/yurivski/DriftBrake/main/docs/img/db_banner_dark.svg">
    <img alt="DriftBrake-Banner" 
         src="https://raw.githubusercontent.com/yurivski/DriftBrake/main/docs/img/db_banner_white.svg" 
         width="560">
  </picture>
</div>

<div align="center">

### Detect, classify, and block schema drift in PostgreSQL before your pipelines get corrupted.

</div>

[![Tests](https://github.com/yurivski/DriftBrake/actions/workflows/ci.yml/badge.svg)](https://github.com/yurivski/DriftBrake/actions/workflows/ci.yml)
[![PyPI Latest Release](https://img.shields.io/pypi/v/driftbrake.svg)](https://pypi.org/project/driftbrake/)
[![PyPI Downloads](https://img.shields.io/pypi/dm/driftbrake.svg?label=PyPI%20downloads)](https://pypi.org/project/driftbrake/)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/MIT-License-blue.svg)

The tool identifies bugs capable of silently corrupting or breaking pipelines before deploying to production, with a simple concept: you create a "contract" describing exactly how your database should look. Before running any pipeline, the tool compares the actual database against this contract and warns you (or blocks you) if anything has changed.

Consult the documentation: [driftbrake.pages](https://driftbrake.pages.dev/#en/overview)

<br>

## DriftBrake

DriftBrake runs before pipelines execute, verifying that the actual database still respects the contract expected by its data consumers. It detects deviations, classifies impact, and blocks execution when necessary — but never alters the database. DriftBrake is not a migration tool. It doesn't apply changes to the database, doesn't generate SQL scripts, and doesn't manage schema versions.

## Python package

This package was designed to run before your pipelines; future updates will expand compatibility to other databases and file formats.

This README contains only basic information related to installing DriftBrake via pip. This package is experimental and may change in future versions. DriftBrake can be used through the CLI or (to customize detection policies) implemented directly in code — see the build instructions in ["Python API"](https://driftbrake.pages.dev/#en/python-api).

The Python package for DriftBrake automatically reads the current schema of a PostgreSQL database, compares it against a versioned contract, classifies drifts by impact, and can block pipelines before they break in production.

**NOTE:** If you are using this with a database other than PostgreSQL (MySQL, SQLite, SQL Server, etc.) you may encounter unexpected errors. In the current version DriftBrake is built entirely around PostgreSQL semantics: the schema reader queries `information_schema.schemata` and reads index options exclusive to Postgres (`postgresql_using`, `postgresql_where`), and the type compatibility matrix follows PostgreSQL cast rules (`varchar`, `text`, `bigint`, `timestamptz`, etc.). Other databases are not supported yet.

<br>

## Installation

```bash
# Installs the psycopg2-binary driver, required for the postgres connection
pip install "driftbrake[postgres]"
# Install pyarrow
pip install "driftbrake[parquet]"
```

For Parquet files, see the [parquet tutorial](https://driftbrake.pages.dev/#en/parquet-guide)

> The `[dev]` extra includes `pre-commit`, `ruff`, `mypy`, `pytest`, and the other development tools.

<br>

## How it works

The current flow:

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
        ├── OK ──────────────────── pipeline runs
        │
        └── BREAKING ────────────── pipeline blocked
                                    ├── displays in terminal
                                    ├── generates schema_diff.json
                                    └── generates schema_report.html
```

### Change types detected

The tool detects the following categories of change in every comparison:

| Type | What it means |
|---|---|
| `table_added` | A new table appeared in the database |
| `table_removed` | A table that existed is gone from the database |
| `column_added` | A NOT NULL column was added to an existing table |
| `nullable_column_added` | A nullable column was added to an existing table |
| `column_removed` | A column was removed from an existing table |
| `type_changed` | A column's data type changed (e.g. `INTEGER` → `TEXT`) |
| `nullable_changed` | The column stopped accepting NULL or started accepting it |
| `default_changed` | The column's default value changed or was removed |
| `primary_key_changed` | A column gained or lost its primary key |
| `unique_changed` | A `UNIQUE` constraint was added or removed |
| `foreign_key_changed` | A foreign key was modified |
| `foreign_key_added` | A foreign key was created where there was none |
| `ordinal_position_changed` | The column's position in the table changed |
| `possible_rename` | A column was removed and a similar one was added in the same table. The tool only flags this as a suspicion of rename, never as a confirmation. Always classified as `WARNING`. |

> `possible_rename` is a heuristic, never a confirmation. DriftBrake flags the suspicion when a removed column and an added column appear type-compatible. Final validation must be done by whoever reviews the migration.

<br>

### `possible_rename` confidence

Each `possible_rename` occurrence carries a `confidence` field indicating how certain the heuristic is:

| Level | Criteria |
|---|---|
| `high` | Similar name + same type + close ordinal position (difference ≤ 2) |
| `medium` | Same type + close ordinal position (difference ≤ 2) |
| `low` | Only type-compatible (SAFE or WARNING in the type matrix) |


**Important rules:**

- `possible_rename` is **never** automatically classified as `BREAKING` — always `WARNING`.
- A `confidence: "high"` is still a suspicion, not a certainty.
- Always review migrations before accepting a rename with `driftbrake update-contract`.

<br>

## License

**MIT license**
