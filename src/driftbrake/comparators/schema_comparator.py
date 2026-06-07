from __future__ import annotations

from datetime import datetime

from driftbrake.classifiers.impact_classifier import ImpactClassifier
from driftbrake.classifiers.type_compatibility import classify_type_change
from driftbrake.models import (
    ChangeType,
    ColumnSchema,
    DatabaseSchema,
    DiffResult,
    IndexSchema,
    SchemaChange,
    Severity,
    TableSchema,
)


class SchemaComparator:
    """
    Detecta:
    Tabelas adicionadas/removidas
    Colunas adicionadas (nullable/with_default/not_null) / removidas
    Alterações de tipo
    Adição/remoção de restrição NOT NULL
    Alterações de default, PK, UNIQUE, FK, posição ordinal
    Índices adicionados/removidos/modificados (definição completa)
    Possíveis renomeações de colunas (heurística)
    """

    def __init__(self, classifier: ImpactClassifier | None = None) -> None:
        self.classifier = classifier or ImpactClassifier()

    def compare(
        self,
        expected: DatabaseSchema,
        current: DatabaseSchema,
        expected_source: str = "contract",
        current_source: str = "database",
    ) -> DiffResult:
        """
        Compara o schema esperado com o schema atual do banco de dados.

        expected: O schema do arquivo de contrato (lock file).
        current: O schema atual do banco de dados.
        """
        changes: list[SchemaChange] = []

        all_schemas = set(expected.schemas.keys()) | set(current.schemas.keys())

        for schema_name in all_schemas:
            expected_tables = expected.schemas.get(schema_name, {})
            current_tables = current.schemas.get(schema_name, {})

            expected_table_names = set(expected_tables.keys())
            current_table_names = set(current_tables.keys())

            for table_name in expected_table_names - current_table_names:
                changes.append(
                    self.classifier.build_change(
                        change_type=ChangeType.TABLE_REMOVED,
                        severity=self.classifier.classify_table_removed(schema_name, table_name),
                        schema_name=schema_name,
                        table_name=table_name,
                        column_name=None,
                        field_name=None,
                        old_value=table_name,
                        new_value=None,
                        description=f"Table '{schema_name}.{table_name}' was removed.",
                    )
                )

            for table_name in current_table_names - expected_table_names:
                changes.append(
                    self.classifier.build_change(
                        change_type=ChangeType.TABLE_ADDED,
                        severity=self.classifier.classify_table_added(schema_name, table_name),
                        schema_name=schema_name,
                        table_name=table_name,
                        column_name=None,
                        field_name=None,
                        old_value=None,
                        new_value=table_name,
                        description=f"Table '{schema_name}.{table_name}' was added.",
                    )
                )

            for table_name in expected_table_names & current_table_names:
                expected_table = expected_tables[table_name]
                current_table = current_tables[table_name]
                table_changes = self._compare_tables(
                    schema_name, table_name, expected_table, current_table
                )
                changes.extend(table_changes)

        return DiffResult(
            changes=changes,
            compared_at=datetime.now(),
            expected_source=expected_source,
            current_source=current_source,
        )

    def _compare_tables(
        self,
        schema_name: str,
        table_name: str,
        expected: TableSchema,
        current: TableSchema,
    ) -> list[SchemaChange]:
        changes: list[SchemaChange] = []

        expected_cols = set(expected.columns.keys())
        current_cols = set(current.columns.keys())

        removed_cols = expected_cols - current_cols
        added_cols = current_cols - expected_cols

        rename_pairs = self._detect_possible_renames(expected, current, removed_cols, added_cols)
        renamed_removed = {pair[0] for pair in rename_pairs}
        renamed_added = {pair[1] for pair in rename_pairs}

        for old_col, new_col, confidence in rename_pairs:
            old_column = expected.columns[old_col]
            new_column = current.columns[new_col]
            change = self.classifier.build_change(
                change_type=ChangeType.POSSIBLE_RENAME,
                severity=self.classifier.classify_possible_rename(old_col, new_col),
                schema_name=schema_name,
                table_name=table_name,
                column_name=old_col,
                field_name=None,
                old_value=old_col,
                new_value=new_col,
                description=(
                    f"Column '{old_col}' removed and '{new_col}' added with "
                    f"compatible type ({old_column.type} -> {new_column.type}). "
                    "Possible rename."
                ),
                suggestion=(
                    f"If this is a rename, update the schema contract "
                    f"with the new column name '{new_col}'."
                ),
            )
            change.confidence = confidence
            changes.append(change)

        for col_name in removed_cols - renamed_removed:
            changes.append(
                self.classifier.build_change(
                    change_type=ChangeType.COLUMN_REMOVED,
                    severity=self.classifier.classify_column_removed(col_name),
                    schema_name=schema_name,
                    table_name=table_name,
                    column_name=col_name,
                    field_name=None,
                    old_value=col_name,
                    new_value=None,
                    description=f"Column '{col_name}' was removed from '{table_name}'.",
                )
            )

        for col_name in added_cols - renamed_added:
            col = current.columns[col_name]
            change_type, severity = self._classify_column_added(col)
            changes.append(
                self.classifier.build_change(
                    change_type=change_type,
                    severity=severity,
                    schema_name=schema_name,
                    table_name=table_name,
                    column_name=col_name,
                    field_name=None,
                    old_value=None,
                    new_value=col_name,
                    description=self._describe_column_added(col_name, col),
                    suggestion=(
                        "Add the column with a default value or make it nullable "
                        "to avoid breaking existing consumers."
                        if not col.nullable and col.default is None
                        else None
                    ),
                )
            )

        for col_name in expected_cols & current_cols:
            exp_col = expected.columns[col_name]
            cur_col = current.columns[col_name]
            col_changes = self._compare_columns(schema_name, table_name, col_name, exp_col, cur_col)
            changes.extend(col_changes)

        changes.extend(self._compare_indexes(schema_name, table_name, expected, current))

        return changes

    def _classify_column_added(self, col: ColumnSchema) -> tuple[ChangeType, Severity]:
        """Determina change_type e severity sem branching condicional no lado do caller."""
        if col.nullable:
            return (
                ChangeType.COLUMN_ADDED_NULLABLE,
                self.classifier.classify_column_added_nullable(),
            )
        if col.default is not None:
            return (
                ChangeType.COLUMN_ADDED_WITH_DEFAULT,
                self.classifier.classify_column_added_with_default(),
            )
        return ChangeType.COLUMN_ADDED_NOT_NULL, self.classifier.classify_column_added_not_null()

    def _describe_column_added(self, col_name: str, col: ColumnSchema) -> str:
        if col.nullable:
            return f"Column '{col_name}' was added (nullable, safe)."
        if col.default is not None:
            return (
                f"Column '{col_name}' was added (NOT NULL with default='{col.default}', warning)."
            )
        return f"Column '{col_name}' was added (NOT NULL without default, breaking)."

    def _compare_columns(
        self,
        schema_name: str,
        table_name: str,
        col_name: str,
        expected: ColumnSchema,
        current: ColumnSchema,
    ) -> list[SchemaChange]:
        changes: list[SchemaChange] = []

        if expected.type != current.type:
            severity = self.classifier.classify_type_change(expected.type, current.type)
            changes.append(
                self.classifier.build_change(
                    change_type=ChangeType.TYPE_CHANGED,
                    severity=severity,
                    schema_name=schema_name,
                    table_name=table_name,
                    column_name=col_name,
                    field_name="type",
                    old_value=expected.type,
                    new_value=current.type,
                    description=(
                        f"Column '{col_name}' type changed from '{expected.type}' "
                        f"to '{current.type}'."
                    ),
                )
            )

        if expected.nullable != current.nullable:
            if current.nullable:
                # NOT NULL -> nullable: restrição removida
                change_type = ChangeType.NOT_NULL_CONSTRAINT_REMOVED
                severity = self.classifier.classify_not_null_constraint_removed()
                desc = f"Column '{col_name}' is now nullable (NOT NULL constraint removed)."
            else:
                # nullable -> NOT NULL: restrição adicionada
                change_type = ChangeType.NOT_NULL_CONSTRAINT_ADDED
                severity = self.classifier.classify_not_null_constraint_added()
                desc = f"Column '{col_name}' is now NOT NULL (constraint added)."
            changes.append(
                self.classifier.build_change(
                    change_type=change_type,
                    severity=severity,
                    schema_name=schema_name,
                    table_name=table_name,
                    column_name=col_name,
                    field_name="nullable",
                    old_value=expected.nullable,
                    new_value=current.nullable,
                    description=desc,
                )
            )

        if expected.default != current.default:
            severity = self.classifier.classify_default_change(expected.default, current.default)
            changes.append(
                self.classifier.build_change(
                    change_type=ChangeType.DEFAULT_CHANGED,
                    severity=severity,
                    schema_name=schema_name,
                    table_name=table_name,
                    column_name=col_name,
                    field_name="default",
                    old_value=expected.default,
                    new_value=current.default,
                    description=(
                        f"Column '{col_name}' default changed from "
                        f"'{expected.default}' to '{current.default}'."
                    ),
                )
            )

        if expected.primary_key != current.primary_key:
            severity = self.classifier.classify_primary_key_change(
                expected.primary_key, current.primary_key
            )
            changes.append(
                self.classifier.build_change(
                    change_type=ChangeType.PRIMARY_KEY_CHANGED,
                    severity=severity,
                    schema_name=schema_name,
                    table_name=table_name,
                    column_name=col_name,
                    field_name="primary_key",
                    old_value=expected.primary_key,
                    new_value=current.primary_key,
                    description=f"Column '{col_name}' primary key status changed.",
                )
            )

        if expected.unique != current.unique:
            severity = self.classifier.classify_unique_change(expected.unique, current.unique)
            changes.append(
                self.classifier.build_change(
                    change_type=ChangeType.UNIQUE_CHANGED,
                    severity=severity,
                    schema_name=schema_name,
                    table_name=table_name,
                    column_name=col_name,
                    field_name="unique",
                    old_value=expected.unique,
                    new_value=current.unique,
                    description=f"Column '{col_name}' unique constraint changed.",
                )
            )

        old_fk_repr = [str(fk) for fk in expected.foreign_key]
        new_fk_repr = [str(fk) for fk in current.foreign_key]
        if old_fk_repr != new_fk_repr:
            severity = self.classifier.classify_foreign_key_change(
                expected.foreign_key, current.foreign_key
            )
            change_type = (
                ChangeType.FOREIGN_KEY_ADDED
                if not expected.foreign_key and current.foreign_key
                else ChangeType.FOREIGN_KEY_CHANGED
            )
            changes.append(
                self.classifier.build_change(
                    change_type=change_type,
                    severity=severity,
                    schema_name=schema_name,
                    table_name=table_name,
                    column_name=col_name,
                    field_name="foreign_key",
                    old_value=expected.foreign_key or None,
                    new_value=current.foreign_key or None,
                    description=f"Column '{col_name}' foreign key configuration changed.",
                )
            )

        if expected.ordinal_position != current.ordinal_position and (
            expected.ordinal_position != 0 and current.ordinal_position != 0
        ):
            severity = self.classifier.classify_ordinal_position_change(
                expected.ordinal_position, current.ordinal_position
            )
            changes.append(
                self.classifier.build_change(
                    change_type=ChangeType.ORDINAL_POSITION_CHANGED,
                    severity=severity,
                    schema_name=schema_name,
                    table_name=table_name,
                    column_name=col_name,
                    field_name="ordinal_position",
                    old_value=expected.ordinal_position,
                    new_value=current.ordinal_position,
                    description=(
                        f"Column '{col_name}' ordinal position changed from "
                        f"{expected.ordinal_position} to {current.ordinal_position}."
                    ),
                )
            )

        return changes

    # Comparação de índices

    def _compare_indexes(
        self,
        schema_name: str,
        table_name: str,
        expected: TableSchema,
        current: TableSchema,
    ) -> list[SchemaChange]:
        changes: list[SchemaChange] = []

        exp_by_name = {idx.name: idx for idx in expected.indexes}
        cur_by_name = {idx.name: idx for idx in current.indexes}

        for name in set(exp_by_name) - set(cur_by_name):
            idx = exp_by_name[name]
            changes.append(
                self.classifier.build_change(
                    change_type=ChangeType.INDEX_REMOVED,
                    severity=self.classifier.classify_index_removed(),
                    schema_name=schema_name,
                    table_name=table_name,
                    column_name=None,
                    field_name=name,
                    old_value=self._index_label(idx),
                    new_value=None,
                    description=f"Index '{name}' on '{table_name}' was removed.",
                    suggestion=(
                        "Removing an index can silently degrade query performance. "
                        "Verify no critical queries relied on this index."
                    ),
                )
            )

        for name in set(cur_by_name) - set(exp_by_name):
            idx = cur_by_name[name]
            changes.append(
                self.classifier.build_change(
                    change_type=ChangeType.INDEX_ADDED,
                    severity=self.classifier.classify_index_added(),
                    schema_name=schema_name,
                    table_name=table_name,
                    column_name=None,
                    field_name=name,
                    old_value=None,
                    new_value=self._index_label(idx),
                    description=f"Index '{name}' on '{table_name}' was added.",
                )
            )

        for name in set(exp_by_name) & set(cur_by_name):
            exp_idx = exp_by_name[name]
            cur_idx = cur_by_name[name]
            if not self._indexes_equal(exp_idx, cur_idx):
                changes.append(
                    self.classifier.build_change(
                        change_type=ChangeType.INDEX_MODIFIED,
                        severity=self.classifier.classify_index_modified(),
                        schema_name=schema_name,
                        table_name=table_name,
                        column_name=None,
                        field_name=name,
                        old_value=self._index_label(exp_idx),
                        new_value=self._index_label(cur_idx),
                        description=(
                            f"Index '{name}' on '{table_name}' definition changed "
                            f"(columns, type, uniqueness, or predicate)."
                        ),
                        suggestion=(
                            "Index definition changes can silently alter query plans. "
                            "Verify affected queries after this migration."
                        ),
                    )
                )

        return changes

    @staticmethod
    def _indexes_equal(a: IndexSchema, b: IndexSchema) -> bool:
        return (
            sorted(a.columns) == sorted(b.columns)
            and a.unique == b.unique
            and a.index_type == b.index_type
            and a.predicate == b.predicate
        )

    @staticmethod
    def _index_label(idx: IndexSchema) -> str:
        parts = [f"({', '.join(idx.columns) or '?'})", f"type={idx.index_type}"]
        if idx.unique:
            parts.append("UNIQUE")
        if idx.predicate:
            parts.append(f"WHERE {idx.predicate}")
        return " ".join(parts)

    # Heurística de rename

    def _detect_possible_renames(
        self,
        expected: TableSchema,
        current: TableSchema,
        removed_cols: set[str],
        added_cols: set[str],
    ) -> list[tuple[str, str, str]]:
        """
        Detecta heuristicamente possíveis renomeações de colunas.
        high = nome similar + mesmo tipo + posição próxima (≤ 2)
        medium = mesmo tipo + posição próxima (≤ 2)
        low = apenas tipo compatível
        """
        pairs: list[tuple[str, str, str]] = []
        if not removed_cols or not added_cols:
            return pairs

        for removed in list(removed_cols):
            old_col = expected.columns[removed]
            best_match: str | None = None
            best_confidence: str = "low"

            for added in list(added_cols):
                if added in {p[1] for p in pairs}:
                    continue
                new_col = current.columns[added]
                compat = classify_type_change(old_col.type, new_col.type)
                if compat not in (Severity.SAFE, Severity.WARNING):
                    continue

                same_type = old_col.type == new_col.type
                close_position = abs(old_col.ordinal_position - new_col.ordinal_position) <= 2
                similar_name = self._names_are_similar(removed, added)

                if similar_name and same_type and close_position:
                    confidence = "high"
                elif same_type and close_position:
                    confidence = "medium"
                else:
                    confidence = "low"

                if best_match is None or self._confidence_rank(confidence) > self._confidence_rank(
                    best_confidence
                ):
                    best_match = added
                    best_confidence = confidence

            if best_match is not None:
                pairs.append((removed, best_match, best_confidence))

        return pairs

    @staticmethod
    def _confidence_rank(confidence: str) -> int:
        return {"low": 0, "medium": 1, "high": 2}.get(confidence, 0)

    @staticmethod
    def _names_are_similar(a: str, b: str) -> bool:
        a_lower, b_lower = a.lower(), b.lower()
        min_len = 3
        prefix_len = min(len(a_lower), len(b_lower))
        for length in range(prefix_len, min_len - 1, -1):
            if a_lower[:length] == b_lower[:length]:
                return True
        if len(a_lower) >= min_len and a_lower[-min_len:] == b_lower[-min_len:]:
            return True
        if a_lower in b_lower or b_lower in a_lower:
            return True
        return False
