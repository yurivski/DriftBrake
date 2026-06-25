# Classificador de impacto para alterações de schema.

from __future__ import annotations

from driftbrake.core.models import ChangeType, SchemaChange, Severity
from driftbrake.core.type_compatibility import classify_type_change


class ImpactClassifier:
    """
    Invariante: severity = f(change_type, policy), a severidade é determinada
    unicamente pelo change_type, sem inspecionar propriedades adicionais do objeto.

    - Objetos removidos são sempre BREAKING.
    - Adições de coluna nullable: SAFE; com default: WARNING; NOT NULL sem default: BREAKING.
    - Adição de restrição NOT NULL: BREAKING; remoção: WARNING.
    - Índice removido: WARNING; modificado: BREAKING; adicionado: SAFE.
    - Alterações de tipo são avaliadas pela matriz de compatibilidade de tipos.
    """

    def __init__(self, custom_rules: dict | None = None) -> None:
        self.custom_rules = custom_rules or {}

    # Tabelas
    def classify_table_added(self, schema: str, table: str) -> Severity:
        return Severity.SAFE

    def classify_table_removed(self, schema: str, table: str) -> Severity:
        return Severity.BREAKING

    # Colunas adicionadas (granular)
    def classify_column_added_nullable(self) -> Severity:
        return Severity.SAFE

    def classify_column_added_with_default(self) -> Severity:
        return Severity.WARNING

    def classify_column_added_not_null(self) -> Severity:
        return Severity.BREAKING

    def classify_column_removed(self, column_name: str) -> Severity:
        return Severity.BREAKING

    # Tipo
    def classify_type_change(self, old_type: str, new_type: str) -> Severity:
        return classify_type_change(old_type, new_type)

    # Restrições NOT NULL (granular)
    def classify_not_null_constraint_added(self) -> Severity:
        return Severity.BREAKING

    def classify_not_null_constraint_removed(self) -> Severity:
        return Severity.WARNING

    # Default, PK, UNIQUE, FK, ordinal
    def classify_default_change(self, old_default: object, new_default: object) -> Severity:
        return Severity.WARNING

    def classify_primary_key_change(self, old_pk: bool, new_pk: bool) -> Severity:
        return Severity.BREAKING

    def classify_unique_change(self, old_unique: bool, new_unique: bool) -> Severity:
        return Severity.WARNING

    def classify_foreign_key_change(self, old_fk: list, new_fk: list) -> Severity:
        old_has = bool(old_fk)
        new_has = bool(new_fk)
        if not old_has and new_has:
            return Severity.WARNING
        return Severity.BREAKING

    def classify_ordinal_position_change(self, old_pos: int, new_pos: int) -> Severity:
        return Severity.WARNING

    def classify_possible_rename(self, removed_col: str, added_col: str) -> Severity:
        return Severity.WARNING

    # Índices
    def classify_index_added(self) -> Severity:
        return Severity.SAFE

    def classify_index_removed(self) -> Severity:
        return Severity.WARNING

    def classify_index_modified(self) -> Severity:
        return Severity.BREAKING

    # Builder
    def build_change(
        self,
        change_type: ChangeType,
        severity: Severity,
        schema_name: str,
        table_name: str,
        column_name: str | None,
        field_name: str | None,
        old_value: object,
        new_value: object,
        description: str,
        suggestion: str | None = None,
    ) -> SchemaChange:
        return SchemaChange(
            change_type=change_type,
            severity=severity,
            schema_name=schema_name,
            table_name=table_name,
            column_name=column_name,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            description=description,
            suggestion=suggestion,
        )
