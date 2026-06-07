<div align="center">

# DriftBrake — Classification Audit

</div>

This document is the **independent reference for every classification decision** DriftBrake makes. If you're trying to understand why the tool marked a change as BREAKING when you expected WARNING, or you need to defend a classification in code review, this is where you look.

> **Audience:** developers integrating DriftBrake into critical pipelines, reviewers auditing migrations, and anyone building custom severity policies.  
> **Companion:** for usage docs (CLI, library, configuration), see [`DOCUMENTATION.md`](DOCUMENTATION.md).

<br>

## Contents

- [Classification](#classification)
- [Complete change-type reference table](#complete-change-type-reference-table)
- [Table-level changes](#table-level-changes)
- [Column-level changes](#column-level-changes)
- [Index-level changes](#index-level-changes)
- [Type compatibility matrix](#type-compatibility-matrix)
- [The `possible_rename` heuristic](#the-possible_rename-heuristic)
- [How overrides interact with classification](#how-overrides-interact-with-classification)
- [Decision logic: block, ask, release](#decision-logic-block-ask-release)
- [Reporter output format](#reporter-output-format)
- [Mixed scenarios](#mixed-scenarios)
- [Edge cases](#edge-cases)
- [Programmatic usage for auditors](#programmatic-usage-for-auditors)

<br>

## Classification

DriftBrake classifies every detected change into one of three severities. The decision rules follow three principles consistently.

**1. The contract is the source of truth.** When the live database differs from the contract, DriftBrake reports the database as drifted from the agreement — not the contract as outdated. The comparator's vocabulary reflects this: a column "removed" means the database lost a column the contract expected; a column "added" means the database has a column the contract didn't agree to.

**2. Severity is about consumer impact, not effort to fix.** A change is BREAKING when downstream consumers reading the database according to the contract would receive wrong data or crash. It is WARNING when consumers keep working but the behavior changed in a way that deserves human review. It is SAFE when existing consumers are unaffected.

**3. Default classifications are conservative.** When in doubt between two severities, DriftBrake picks the stricter one. Practical examples: a `NOT NULL` constraint removed is WARNING (not SAFE) because new code may have started depending on NULL not appearing; a foreign key added is WARNING (not SAFE) because referential constraints can reject inserts that worked before.

<br>

## Complete change-type reference table

The table below lists every `ChangeType` value that DriftBrake can emit, its default severity, the exact key used for policy overrides (snake_case, matching `change_type.value`), and a brief reason.

| `change_type` | Default severity | Override key (YAML) | Reason |
|---|---|---|---|
| `table_added` | **SAFE** | `table_added` | New tables are invisible to existing consumers. |
| `table_removed` | **BREAKING** | `table_removed` | All consumers that query this table crash immediately. |
| `column_added_nullable` | **SAFE** | `column_added_nullable` | Nullable additions are invisible to existing consumers; existing INSERTs and SELECTs continue to work. |
| `column_added_with_default` | **WARNING** | `column_added_with_default` | NOT NULL column with default: inserts still work, but new constraint may surprise application code. |
| `column_added_not_null` | **BREAKING** | `column_added_not_null` | NOT NULL column without default: existing INSERTs that omit this column fail with `NotNullViolation`. |
| `column_removed` | **BREAKING** | `column_removed` | Every SELECT, WHERE, and code path referencing this column breaks. |
| `type_changed` | **see matrix** | `type_changed` | Severity depends on widening, narrowing, or semantic shift; consult the type compatibility matrix. |
| `not_null_constraint_added` | **BREAKING** | `not_null_constraint_added` | Existing rows with NULL fail validation. Existing inserts that omit this column now fail. |
| `not_null_constraint_removed` | **WARNING** | `not_null_constraint_removed` | Column now accepts NULL; code that assumed non-null may propagate NULLs silently. |
| `default_changed` | **WARNING** | `default_changed` | Silent behavioral change: inserts that omit this column now receive a different value. |
| `primary_key_changed` | **BREAKING** | `primary_key_changed` | Identity semantics shift; FK references may break; joins on PK columns may produce wrong results. |
| `unique_changed` | **WARNING** | `unique_changed` | New inserts may fail (constraint added); existing reliance on uniqueness is silently lost (constraint removed). |
| `foreign_key_added` | **WARNING** | `foreign_key_added` | New referential constraints may reject inserts that previously succeeded. |
| `foreign_key_changed` | **BREAKING** | `foreign_key_changed` | Referenced target shifted; existing joins may break; existing rows may violate referential integrity. |
| `ordinal_position_changed` | **WARNING** | `ordinal_position_changed` | `SELECT *` order changed; position-based consumers break silently. |
| `possible_rename` | **WARNING** | `possible_rename` | Heuristic suspicion only; human confirmation required before approving. |
| `index_added` | **SAFE** | `index_added` | New indexes are transparent to existing consumers; queries continue to work. |
| `index_removed` | **WARNING** | `index_removed` | Dropping an index can silently degrade query performance; queries keep returning correct results but may be slower. |
| `index_modified` | **BREAKING** | `index_modified` | Index definition changes (columns, type, uniqueness, predicate) can silently alter query plans. |

<br>

## Table-level changes

### `table_added` — SAFE

**When it happens:** The live database contains a table not present in the contract.

**Why SAFE:** Existing consumers ignore tables they don't know about. New tables are additive by definition, no contract held by current consumers is violated. Queries, inserts, and application code that was working before the migration continues to work unchanged.

**How to adjust:**

```yaml
overrides:
  table_added: WARNING  # Require human sign-off on any schema expansion
```

**Edge cases:** If a table is added without migrating the contract (`init`), subsequent runs will keep reporting it as SAFE drift. Update the contract when the addition is intentional.

---

### `table_removed` — BREAKING

**When it happens:** The contract references a table that no longer exists in the live database.

**Why BREAKING:** Every consumer that queries this table crashes immediately with `UndefinedTable`. No recovery is possible without restoring the table or rewriting all dependent code and updating the contract.

**How to adjust:** There is no safe downgrade for `table_removed`. If the table was intentionally dropped, update the contract via `driftbrake init`. If it was dropped by accident, restore it.

<br>

## Column-level changes

### `column_added_nullable` — SAFE

**When it happens:** A new nullable column appears in the live database that was not in the contract.

**Why SAFE:** Existing `INSERT` statements that list columns explicitly skip this column and the database inserts NULL. Existing `SELECT *` queries receive one extra NULL column which they typically ignore. No consumer breaks.

**How to adjust:**

```yaml
overrides:
  column_added_nullable: BREAKING  # Strict audit: every schema expansion requires sign-off
```

This is one of the most common overrides in high-compliance environments. This key targets ONLY nullable additions and does not affect `column_added_with_default` or `column_added_not_null`.

---

### `column_added_with_default` — WARNING

**When it happens:** A new NOT NULL column with a default value appears in the live database.

**Why WARNING:** Existing `INSERT` statements that don't include this column still succeed because the database fills the default. The severity is WARNING (not SAFE) because the default behavior may surprise application code that assumed inserts failing when this field was missing, and the new constraint is a behavioral change worth reviewing.

**How to adjust:**

```yaml
overrides:
  column_added_with_default: BREAKING  # Treat any NOT NULL addition as blocking
  column_added_with_default: SAFE      # Only if the default covers all cases and consumers are already aware
```

---

### `column_added_not_null` — BREAKING

**When it happens:** A new NOT NULL column without a default value appears in the live database.

**Why BREAKING:** Existing `INSERT` statements that don't include this column fail with `NotNullViolation`. Every writer to this table must be updated before the migration can be applied safely. There is no automatic recovery.

**How to adjust:**

```yaml
overrides:
  column_added_not_null: WARNING  # Only if all writers have already been updated to provide this field
```

---

### `column_removed` — BREAKING

**When it happens:** The contract references a column that no longer exists in the live database.

**Why BREAKING:** Every `SELECT column_name`, every `WHERE column_name = ...`, every application code path that reads or writes this field breaks. There is no automatic recovery.

**How to adjust:** No safe downgrade. If the removal was intentional, update the contract. If it was a `possible_rename`, see that section.

---

### `type_changed` — see matrix

**When it happens:** A column's data type in the live database differs from the type in the contract.

**Why it varies:** Type changes range from safe widening (more values fit) to lossy narrowing (existing values may be lost or misinterpreted). See the [type compatibility matrix](#type-compatibility-matrix) for specific pairs.

**How to adjust:**

```yaml
overrides:
  type_changed: WARNING  # Downgrade all type changes — only if you've verified every conversion is safe
```

This is a coarse override because `type_changed` covers every type pair. Prefer reviewing specific cases rather than blanket-downgrading.

---

### `not_null_constraint_added` — BREAKING

**When it happens:** A column that was nullable in the contract is now NOT NULL in the live database.

**Why BREAKING:** Existing rows with NULL fail validation at the database level. Inserts that previously succeeded without providing this field now fail. Even if the migration backfills existing NULLs, all writers must be updated.

**How to adjust:**

```yaml
overrides:
  not_null_constraint_added: WARNING  # Only if existing data has been backfilled and all writers updated
```

---

### `not_null_constraint_removed` — WARNING

**When it happens:** A column that was NOT NULL in the contract is now nullable in the live database.

**Why WARNING:** Existing code continues reading the column without error. But the code now implicitly assumes the field is always non-null — if new code paths start inserting NULLs, previously safe logic fails silently (NULL propagating into arithmetic, comparisons, formatted strings).

**How to adjust:**

```yaml
overrides:
  not_null_constraint_removed: SAFE  # Only if consumers have been audited for null-handling
```

---

### `default_changed` — WARNING

**When it happens:** A column's default value was added, removed, or changed in the live database relative to the contract. All three sub-cases emit `default_changed` with WARNING severity.

**Why WARNING:** The schema doesn't break structurally, queries and inserts continue to compile and run. But behavior changes: inserts that omit this column now receive a different value (or NULL, or fail if NOT NULL without default). This is a silent behavioral change that can produce wrong data in business logic without any error surfacing.

**How to adjust:**

```yaml
overrides:
  default_changed: BREAKING  # Treat silent behavioral changes as blocking
```

---

### `primary_key_changed` — BREAKING

**When it happens:** The primary key column(s) of a table changed relative to the contract.

**Why BREAKING:** Primary keys are identity contracts. Foreign keys in other tables that reference this PK may break. Code that assumes a specific PK column (for caching, pagination cursors, deduplication) may produce wrong joins or incorrect results. The change is always BREAKING because there is no safe PK swap for a live system with dependencies.

---

### `unique_changed` — WARNING

**When it happens:** A unique constraint was added or removed from a column relative to the contract.

**Why WARNING (constraint added):** Existing data passed validation (the constraint was created successfully). But new inserts and updates that previously succeeded may now fail with duplicate-key errors.

**Why WARNING (constraint removed):** Code may have relied on uniqueness for caching strategies, deduplication logic, or guaranteed join correctness. The removal is silent at the schema level but loud in application behavior.

---

### `foreign_key_added` — WARNING

**When it happens:** A new foreign key constraint was added in the live database that was not in the contract.

**Why WARNING:** New inserts and updates must now satisfy referential integrity. Application code that previously wrote orphan references (rows with no matching parent) now fails at the database level. The change doesn't break existing reads, but it breaks existing writes that relied on the absence of constraint.


---

### `foreign_key_changed` — BREAKING

**When it happens:** An existing foreign key constraint's referenced table or column changed relative to the contract.

**Why BREAKING:** The FK now points to a different target. Existing joins may produce wrong results. Existing rows may now violate referential integrity if the new referenced column doesn't contain matching values.

---

### `foreign_key_changed` also covers FK removed — BREAKING (not WARNING)

**Why BREAKING (FK removed):** Removing a foreign key removes a referential integrity guarantee that consumers may have depended on. Cascade delete behavior, ON UPDATE behavior, and join semantics all change silently. The code treats this as BREAKING because the assumption embedded in the contract is violated.

---

### `ordinal_position_changed` — WARNING

**When it happens:** A column's position (ordinal) within the table changed relative to the contract.

**Why WARNING:** `SELECT *` callers receive columns in a different order. Modern code that maps columns by name is unaffected. Legacy code that reads result sets by position (index 0, index 1, etc.) breaks silently. WARNING rather than BREAKING because the failure mode is position-based access, which is rare in contemporary codebases but common enough to flag.

<br>

## Index-level changes

### `index_added` — SAFE

**When it happens:** A new index appears in the live database on a table already tracked by the contract.

**Why SAFE:** Indexes are a performance detail, invisible to consumers at the query result level. Adding an index does not change what data is stored or returned. Existing queries continue working correctly.

**How to adjust:**

```yaml
overrides:
  index_added: WARNING  # Require sign-off for every index addition in high-compliance environments
```

---

### `index_removed` — WARNING

**When it happens:** An index that existed in the contract no longer exists in the live database.

**Why WARNING:** Dropping an index does not affect query correctness — results remain the same — but performance can degrade silently. Queries that relied on the index for fast lookups may now perform full table scans. DriftBrake includes a suggestion in the change description: "Verify no critical queries relied on this index."

**How to adjust:**

```yaml
overrides:
  index_removed: BREAKING  # Treat every index drop as requiring explicit approval
```

---

### `index_modified` — BREAKING

**When it happens:** An index with the same name exists in both the contract and the live database, but its definition changed — different columns, different uniqueness, different index type, or different partial predicate.

**Why BREAKING:** Index definition changes can silently alter query plans. A query that used a covering index may now require a different access path. A unique index made non-unique removes a consistency guarantee that code may depend on. A partial index (WHERE clause) change means different rows are indexed than before.

Note: DriftBrake compares columns in sorted order, so column order within an index does not trigger `index_modified`. Only the set of columns, uniqueness flag, index type, and predicate are compared.

**How to adjust:**

```yaml
overrides:
  index_modified: WARNING  # Downgrade if query plan changes are acceptable in your environment
```

<br>

## Type compatibility matrix

When a column type changes, DriftBrake consults the type compatibility module before deciding severity. The matrix below covers the most common conversions. Conversions not listed default to **BREAKING**.

> **Type canonicalization (v0.1.1):** Before any comparison, DriftBrake normalizes PostgreSQL catalog aliases to their canonical names. This prevents phantom `type_changed` events caused by representation differences between SQLAlchemy versions or driver configurations:
>
> | Alias (as PostgreSQL may report) | Canonical (used internally) |
> |---|---|
> | `character varying(N)` | `varchar(N)` |
> | `decimal` / `decimal(p,s)` | `numeric` / `numeric(p,s)` |
> | `int4` | `integer` |
> | `int8` | `bigint` |
> | `int2` | `smallint` |
> | `float8` | `double precision` |
> | `float4` | `real` |
> | `bool` | `boolean` |
> | `timestamp without time zone` | `timestamp` |
> | `timestamp with time zone` | `timestamptz` |
>
> Two type strings that are different aliases for the same physical type will always produce `SAFE`.

### Strings

| Conversion | Severity | Reasoning |
|---|---|---|
| `varchar(50)` → `varchar(100)` | **SAFE** | Widening — every value that fit before still fits. |
| `varchar(100)` → `varchar(50)` | **BREAKING** | Narrowing — values longer than 50 characters are truncated or rejected. |
| `varchar(n)` → `text` | **SAFE** | `text` has no length limit; every `varchar` value fits unchanged. |
| `text` → `varchar(n)` | **BREAKING** | Any value longer than `n` is now invalid. |


### Integers

| Conversion | Severity | Reasoning |
|---|---|---|
| `smallint` → `integer` | **SAFE** | Widening. |
| `integer` → `bigint` | **WARNING** | Widening for the database, but client code reading into a fixed-width 32-bit integer may overflow on large values. |
| `bigint` → `integer` | **BREAKING** | Narrowing — values above 2^31-1 overflow. |
| `integer` → `smallint` | **BREAKING** | Narrowing — values above 2^15-1 overflow. |

**The code says WARNING for these specific pairs:**

| Conversion | Severity | Reasoning |
|---|---|---|
| `integer` → `text` | **WARNING** | Code returns WARNING: numeric value is losslessly representable as text, but arithmetic semantics are lost. |
| `bigint` → `text` | **WARNING** | Code returns WARNING. |


### Decimals

| Conversion | Severity | Reasoning |
|---|---|---|
| `numeric(10,2)` → `numeric(12,2)` | **SAFE** | Widening precision, scale unchanged. |
| `numeric(12,2)` → `numeric(10,2)` | **BREAKING** | Narrowing precision — values above 10 significant digits overflow. |
| `numeric(10,4)` → `numeric(10,2)` | **BREAKING** | Scale narrowed — values with more than 2 decimal places lose precision. |

The logic in the code is as follows: `if new_prec < old_prec or new_scale != old_scale: return BREAKING`. This means that **any modification to the scale**, whether increasing or decreasing it, is treated as a breaking change. Downstream consumers that rely on parsing the column scale from metadata may behave unexpectedly or incorrectly if the scale changes in any direction.

| Conversion | Severity | Reasoning |
|---|---|---|
| `real` → `double precision` | **SAFE** | Widening. |
| `double precision` → `real` | **BREAKING** | Code returns BREAKING: narrowing precision with potential value loss, not just accuracy loss. |

### Dates and times

| Conversion | Severity | Reasoning |
|---|---|---|
| `date` → `timestamp` | **WARNING** | Date semantics preserved (midnight), but consumers may now process an unexpected time component. |
| `timestamp` → `date` | **BREAKING** | Loss of time component; rows with non-midnight times silently lose information. |
| `timestamp` → `timestamptz` | **WARNING** | Time zone interpretation shifts; consumers must agree on UTC vs. local. |
| `timestamptz` → `timestamp` | **WARNING** | **Code returns WARNING.** Time zone information is technically dropped at the database level, but for many consumers in a single time zone environment this conversion is tolerable, human review is required rather than automatic blocking. |

### Generic

| Conversion | Severity | Reasoning |
|---|---|---|
| `numeric` → `text` | **BREAKING** | Numeric semantics lost. Arithmetic, comparisons, range queries all break. |
| `text` → `numeric` | **BREAKING** | Parsing required; rows with non-numeric content fail. |
| `json` → `jsonb` | **SAFE** | `jsonb` is a strict superset of `json` use cases. |
| `jsonb` → `json` | **WARNING** | Loses indexability; queries relying on jsonb operators break. |

### What the matrix does NOT cover

If DriftBrake encounters a type pair not in `_COMPAT_RULES` (custom domains, extension types such as PostGIS, enums, composite types), it defaults to **BREAKING** to be conservative. Use a policy override if your context requires otherwise:

```yaml
overrides:
  type_changed: WARNING  # Use only after manually verifying each unknown type pair is safe
```

<br>

## The `possible_rename` heuristic

When a column is removed from a table and another column is added to the same table with a compatible type, DriftBrake treats this as a **suspicion of rename** rather than two independent changes.

### How the suspicion is detected

The heuristic fires when all three conditions hold:

1. A column was removed from a table.
2. A column was added to the same table.
3. The types are compatible per the type matrix (the conversion would be SAFE or WARNING — **never BREAKING**).

When this fires, DriftBrake emits a single `possible_rename` change instead of one `column_removed` (BREAKING) + one column-added change (`column_added_nullable`, `column_added_with_default`, or `column_added_not_null`).

**Only one rename pair per removed column.** When multiple added columns match a removed column, DriftBrake selects the best match and emits a single `possible_rename` for that pair. The other candidates remain as independent additions.

### When incompatible types prevent rename detection

If the type of the removed column and the type of the added column are BREAKING-incompatible per the type matrix, the heuristic does **not** fire. Instead, DriftBrake emits:

- A `column_removed` change (BREAKING) for the removed column.
- A column-added change for the added column (`column_added_nullable` SAFE, `column_added_with_default` WARNING, or `column_added_not_null` BREAKING), based on its properties.

This is the correct behavior because an incompatible type change is not a rename, it's a semantic replacement.

### Why `possible_rename` is always WARNING

A `possible_rename` is never auto-classified as BREAKING for two reasons:

- If it really was a rename, the change is essentially backward-compatible — the data moved, but it didn't disappear. Blocking it would prevent legitimate migrations from proceeding.
- If it really was a coincidental drop + add with similar types, the BREAKING-ness is in the drop. Flagging the pair as BREAKING would double-count the severity.

WARNING captures the right semantic: "this looks like a rename, but a human must confirm before approving."

### Confidence levels

Each `possible_rename` carries a `confidence` field that reflects how strong the rename signal is.

| Level | Criteria | Practical meaning |
|---|---|---|
| `high` | Similar column names **and** same type **and** \|ordinal_diff\| ≤ 2 | Strong rename signal. The three independent signals align. Still requires manual confirmation, but is the most likely true rename. |
| `medium` | Same type **and** \|ordinal_diff\| ≤ 2 | Names differ but position and type alignment suggest rename. Could be a refactor where the column was renamed significantly. Review required. |
| `low` | Only type-compatible | Could be a rename, could be coincidence. Most caution required. Treat as a suspected drop+add until proven otherwise. |

### How to escalate rename detection to BREAKING

If your audit pipeline requires every removal to be explicitly approved regardless of rename suspicion:

```yaml
overrides:
  possible_rename: BREAKING
```

The change is still detected as `possible_rename` (not split into separate drop/add), but it will block the pipeline instead of warning.

<br>

## How overrides interact with classification

Policy overrides apply **after** DriftBrake's default classification. The pipeline is:

1. Schema comparator detects each change and assigns its default severity (per the tables above).
2. If a policy file is loaded, `apply_policy()` runs as post-processing.
3. For each change, the policy checks `ignore_tables`, then `ignore_columns`, then `overrides`.
4. Overrides **replace the severity** and append `[overridden by policy: SEVERITY]` to the original description for audit trail.

### Exact mechanics of `apply_policy`

```python
def apply_policy(result, policy: Policy):
    for change in result.changes:
        # Ignore_tables: skip entirely — change is not reported at all
        if change.table_name in policy.ignore_tables:
            continue
        # Ignore_columns: skip ("table.column" format)
        col_key = f"{change.table_name}.{change.column_name}" if change.column_name else None
        if col_key and col_key in policy.ignore_columns:
            continue
        # Overrides: replace severity + append to description
        change_type_name = change.change_type.value  # e.g. "nullable_column_added"
        if change_type_name in policy.overrides:
            new_severity = Severity(policy.overrides[change_type_name])
            change = replace(change, severity=new_severity,
                description=f"{change.description} [overridden by policy: {new_severity.value}]")
```

The override key in YAML **must match `change_type.value` exactly** (snake_case). The complete set of valid keys is: `table_added`, `table_removed`, `column_added_nullable`, `column_added_with_default`, `column_added_not_null`, `column_removed`, `type_changed`, `not_null_constraint_added`, `not_null_constraint_removed`, `default_changed`, `primary_key_changed`, `unique_changed`, `foreign_key_changed`, `foreign_key_added`, `ordinal_position_changed`, `possible_rename`, `index_added`, `index_removed`, `index_modified`.

### Override examples

```yaml
overrides:
  column_added_nullable: BREAKING   # Require sign-off for every nullable addition
  column_added_with_default: BREAKING  # Treat NOT NULL+default additions as blocking
  ordinal_position_changed: SAFE    # Suppress positional change warnings in your environment
  default_changed: BREAKING         # Treat silent behavioral changes as blocking
  possible_rename: BREAKING         # Force explicit approval of every rename suspicion
  index_removed: BREAKING           # Treat index drops as blocking
```

### Ignore lists are absolute

`ignore_tables` and `ignore_columns` filter changes out entirely — DriftBrake does not report them at all, regardless of severity. They take priority over overrides.

```yaml
ignore_tables:
  - alembic_version        # Migration tooling artifact
  - flyway_schema_history  # Migration tooling artifact

ignore_columns:
  - users.updated_at       # Automatic timestamp, not part of the API contract
  - orders.last_synced     # Operational field, not contract-relevant
```

Use ignore lists for fields that change frequently for operational reasons and are not part of the contract you want to enforce.

<br>

## Decision logic: block, ask, release

After all changes are classified (including policy post-processing), DriftBrake determines the highest severity present and decides whether to block, ask, or release the pipeline.

```python
# Pseudocode from decision.py
if sev_upper in fail_on:
    → block (exit code 2)
if sev_upper in ask_on and interactive_effective:
    → ask (prompt user for confirmation)
else:
    → release (exit code 0)
```

Default configuration:
- `fail_on = ["BREAKING"]` — any BREAKING change blocks automatically.
- `ask_on = ["WARNING"]` — any WARNING change prompts for confirmation in interactive mode; in non-interactive mode (CI), it releases without asking.

The decision is based on the single highest severity across all changes. A run with 10 SAFE changes and 1 BREAKING change blocks just as firmly as a run with 1 BREAKING change.

<br>

## Reporter output format

The `FacadeTerminalReporter` formats output as follows:

```
[OK]      DriftBrake: no schema drift detected.
[INFO]    DriftBrake: N safe schema change(s) detected.
[WARN]    DriftBrake: N warning change(s) detected.
[BLOCKED] DriftBrake: N breaking change(s) detected.
[BLOCKED] {reason}
          Pipeline blocked.
[OK]      Pipeline released.
```

Key behaviors:

- `[OK]` on no drift: emitted when there are zero changes of any kind.
- `[INFO]` for SAFE: emits a count only unless `verbose=True`. When `verbose=True`, each SAFE change is listed individually.
- `[WARN]` for WARNING: **always lists each change individually**, regardless of verbose setting.
- `[BLOCKED]` for BREAKING: **always lists each change individually**; written to stderr.
- `[BLOCKED]` + `Pipeline blocked.`: emitted after the change list when the pipeline is blocked; written to stderr.
- `[OK]` + `Pipeline released.`: emitted when the pipeline is allowed to proceed.

### Example: multiple severities present

```
[INFO]    DriftBrake: 1 safe schema change(s) detected.
[WARN]    DriftBrake: 1 warning change(s) detected.
  - public.orders.created_at: Column 'created_at' default changed from 'now()' to 'CURRENT_TIMESTAMP'.
[BLOCKED] DriftBrake: 1 breaking change(s) detected.
  - public.users.email: Column 'email' was removed from 'users'.
[BLOCKED] BREAKING in fail_on.
          Pipeline blocked.
```

SAFE changes appear as a count only in non-verbose mode. WARNING and BREAKING changes are always listed with table, column, and description.

<br>

## Mixed scenarios

When a single migration touches multiple tables or columns, DriftBrake reports every change independently. The pipeline-level decision is based on the **highest severity present**:

| Highest severity | Pipeline outcome |
|---|---|
| No changes | Release |
| SAFE only | Release |
| WARNING (non-interactive or not in `ask_on`) | Release |
| WARNING (interactive + `ask_on` includes WARNING) | Ask user |
| BREAKING (in `fail_on`) | Block |

All three severity levels may appear in the same run. The reporter shows each one present, in order (SAFE → WARNING → BREAKING), each with its own prefix.

<br>

## Edge cases

### Schemas configured but not present in the database

If `schemas=["public", "staging"]` is configured but `staging` doesn't exist, DriftBrake raises `SchemaNotFoundError` (exit code 5) listing the available schemas. This fails loud instead of silently reporting "no drift."

### Contract file present but corrupted

If `schema.lock.json` exists but isn't valid JSON, DriftBrake raises `SchemaContractNotFoundError` (exit code 4) with the parse error location. Same exit code as "contract missing" because in both cases the contract is unusable.

### Contract file present but structurally invalid

If `schema.lock.json` is valid JSON but missing required fields (e.g. `{}`), DriftBrake raises `SchemaContractNotFoundError` listing the missing fields.

### Filesystem read-only during `init`

If DriftBrake tries to write `schema.lock.json` to a read-only filesystem (CI sandbox, hardened container), it raises `ContractWriteError` (exit code 6) with the path and the underlying OS error.

### Database unreachable

If the database can't be connected to, DriftBrake raises `SchemaConnectionError` (exit code 3) with the underlying driver error. Exit code 3 covers both "server not running" and "authentication failed" — the message distinguishes the two.

### `possible_rename` + incompatible types = separate drop and add

If a removed column and an added column have BREAKING-incompatible types, the rename heuristic does not fire. The result is a `column_removed` (BREAKING) + a column-added change (`column_added_nullable` SAFE, `column_added_with_default` WARNING, or `column_added_not_null` BREAKING), depending on the added column's properties. This reflects a true semantic replacement, not a rename.

### Removed `driftbrake.yml` format (v0.2.0)

Loading `driftbrake.yml` files that use the nested keys `tables.ignore` / `columns.ignore` (v0.0.2 format) now raises `ConfigurationError` immediately. This format was deprecated with a `DeprecationWarning` in v0.1.1 and removed in v0.2.0. Migrate to `driftbrake.policy.yml` with the flat keys `ignore_tables` / `ignore_columns`.

### `index_modified` vs separate `index_removed` + `index_added`

When an index exists in both before and after but its definition changed (different columns, uniqueness, type, or predicate), DriftBrake emits a single `index_modified` (BREAKING) instead of `index_removed` + `index_added`. The name is the matching key. If the same name doesn't exist in both sides, it's detected as independent removal + addition.

Note: DriftBrake compares index columns in sorted order — index column order is not tracked as a change. Only the set of columns matters.

<br>

## Programmatic usage for auditors

### Why classifications matter in pipelines

When DriftBrake is embedded in a CI/CD pipeline, the classification determines whether a deployment is automatically blocked, requires human approval, or proceeds. Getting the classifications right means:

- BREAKING changes halt deployment automatically, preventing outages caused by schema drift.
- WARNING changes surface for review without stopping the pipeline in non-interactive CI environments.
- SAFE changes are logged but never block.

Misconfigured policies (e.g. `nullable_column_added: SAFE` when it already defaults to SAFE, or `foreign_key_changed: WARNING` when it should be BREAKING) can silently pass changes that break downstream consumers.

### Overriding severity via YAML

```yaml
# driftbrake.policy.yml
overrides:
  column_added_nullable: BREAKING   # Stricter: require sign-off for all additions
  column_added_not_null: WARNING    # Looser: allow NOT NULL without default after writer update
  ordinal_position_changed: SAFE    # Suppress positional change warnings in your environment
  possible_rename: BREAKING         # Escalate: treat every rename suspicion as blocking
  index_removed: BREAKING           # Escalate: treat index drops as blocking
ignore_tables:
  - alembic_version
ignore_columns:
  - users.internal_notes
```

The override key must be the exact snake_case `change_type.value`. Case sensitivity matters — `COLUMN_ADDED_NULLABLE` will not match.

### Overriding severity via Python API

```python
from driftbrake.models import Policy
from driftbrake.policy import apply_policy

policy = Policy(
    overrides={"column_added_nullable": "BREAKING"},
    ignore_tables=["alembic_version"],
    ignore_columns=["users.updated_at"],
)
result = apply_policy(drift_result, policy)
```

### CLI and library

For CLI usage, configuration flags, and integration recipes, see [`DOCUMENTATION.md`](DOCUMENTATION.md). This document (AUDIT.md) covers only classification logic and policy mechanics.

<br>

---

## Maintenance note

This document is the audit trail of classification decisions. **When a default severity changes between versions, this document is updated alongside the CHANGELOG.**

For the source code that implements these rules, see:

- `src/driftbrake/classifiers/impact_classifier.py` — applies severity defaults.
- `src/driftbrake/classifiers/type_compatibility.py` — type matrix logic.
- `src/driftbrake/comparators/schema_comparator.py` — change detection and `possible_rename` heuristic.
- `src/driftbrake/policy.py` — `apply_policy()` post-processing.
- `src/driftbrake/decision.py` — block / ask / release decision logic.
- `src/driftbrake/reporters/facade_terminal.py` — terminal reporter output format.
