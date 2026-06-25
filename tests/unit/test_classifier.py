"""
Testes unitários para ImpactClassifier.
Pra evitar que o arquivo fique muito grande, apenas as chamadas com argumentos
acima de 100 caracteres terão quebras de linhas.
"""

from driftbrake.core.classifier import ImpactClassifier
from driftbrake.models import ColumnSchema, Severity

classifier = ImpactClassifier()


def _col(
    name: str = "col",
    type_: str = "TEXT",
    nullable: bool = True,
    default=None,
    primary_key: bool = False,
    unique: bool = False,
    foreign_key: list | None = None,
    ordinal_position: int = 1,
) -> ColumnSchema:
    return ColumnSchema(
        name=name,
        type=type_,
        nullable=nullable,
        default=default,
        primary_key=primary_key,
        unique=unique,
        foreign_key=foreign_key or [],
        ordinal_position=ordinal_position,
    )


class TestTableClassification:
    def test_table_added_is_safe(self):
        assert classifier.classify_table_added("public", "new_table") == Severity.SAFE

    def test_table_removed_is_breaking(self):
        assert classifier.classify_table_removed("public", "old_table") == Severity.BREAKING


class TestColumnAddedClassification:
    def test_nullable_column_is_safe(self):
        assert classifier.classify_column_added_nullable() == Severity.SAFE

    def test_not_null_with_default_is_warning(self):
        assert classifier.classify_column_added_with_default() == Severity.WARNING

    def test_not_null_no_default_is_breaking(self):
        assert classifier.classify_column_added_not_null() == Severity.BREAKING


class TestColumnRemovedClassification:
    def test_column_removed_is_breaking(self):
        assert classifier.classify_column_removed("any_col") == Severity.BREAKING


class TestNotNullConstraintClassification:
    def test_not_null_constraint_added_is_breaking(self):
        assert classifier.classify_not_null_constraint_added() == Severity.BREAKING

    def test_not_null_constraint_removed_is_warning(self):
        assert classifier.classify_not_null_constraint_removed() == Severity.WARNING


class TestDefaultClassification:
    def test_default_changed_is_warning(self):
        assert classifier.classify_default_change("old", "new") == Severity.WARNING
        assert classifier.classify_default_change(None, "'default'") == Severity.WARNING


class TestPrimaryKeyClassification:
    def test_pk_changed_is_breaking(self):
        assert classifier.classify_primary_key_change(True, False) == Severity.BREAKING
        assert classifier.classify_primary_key_change(False, True) == Severity.BREAKING


class TestUniqueClassification:
    def test_unique_changed_is_warning(self):
        assert classifier.classify_unique_change(True, False) == Severity.WARNING
        assert classifier.classify_unique_change(False, True) == Severity.WARNING


class TestForeignKeyClassification:
    def test_fk_added_is_warning(self):
        fk = [{"referred_table": "other", "referred_columns": ["id"]}]
        assert classifier.classify_foreign_key_change([], fk) == Severity.WARNING

    def test_fk_changed_is_breaking(self):
        fk_old = [{"referred_table": "a", "referred_columns": ["id"]}]
        fk_new = [{"referred_table": "b", "referred_columns": ["id"]}]
        assert classifier.classify_foreign_key_change(fk_old, fk_new) == Severity.BREAKING

    def test_fk_removed_is_breaking(self):
        fk = [{"referred_table": "other", "referred_columns": ["id"]}]
        assert classifier.classify_foreign_key_change(fk, []) == Severity.BREAKING


class TestOrdinalPositionClassification:
    def test_ordinal_changed_is_warning(self):
        assert classifier.classify_ordinal_position_change(1, 5) == Severity.WARNING
        assert classifier.classify_ordinal_position_change(3, 1) == Severity.WARNING


class TestPossibleRenameClassification:
    def test_possible_rename_is_warning(self):
        assert classifier.classify_possible_rename("old_col", "new_col") == Severity.WARNING


class TestIndexClassification:
    def test_index_added_is_safe(self):
        assert classifier.classify_index_added() == Severity.SAFE

    def test_index_removed_is_warning(self):
        assert classifier.classify_index_removed() == Severity.WARNING

    def test_index_modified_is_breaking(self):
        assert classifier.classify_index_modified() == Severity.BREAKING
