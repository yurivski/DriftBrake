"""ContractWriter: serialização do contrato para schema.lock.json.

Regressão do bug `TypeError: Object of type IndexSchema is not JSON serializable`:
o writer reimplementava a serialização da tabela e gravava os IndexSchema crus
em vez de `idx.to_dict()`. Qualquer banco com índice quebrava `init`/`update-contract`.
Sem teste que escrevesse um contrato COM índices, o bug passou despercebido.
"""

import json
from datetime import datetime

from driftbrake import (
    ColumnSchema,
    DatabaseSchema,
    IndexSchema,
    JsonSchemaReader,
    SchemaComparator,
    TableSchema,
)
from driftbrake.contracts.writer import ContractWriter


def _col(name, type_="integer", **kw):
    return ColumnSchema(
        name=name,
        type=type_,
        nullable=kw.get("nullable", True),
        default=kw.get("default"),
        primary_key=kw.get("primary_key", False),
        unique=kw.get("unique", False),
        foreign_key=kw.get("foreign_key", []),
        ordinal_position=kw.get("ordinal_position", 1),
    )


def _schema_with_indexes() -> DatabaseSchema:
    table = TableSchema(
        name="customers",
        schema="public",
        columns={
            "customer_id": _col("customer_id", "integer", primary_key=True, ordinal_position=1),
            "customer_email": _col("customer_email", "varchar(255)", ordinal_position=2),
        },
        indexes=[
            IndexSchema(name="customers_pkey", columns=["customer_id"], unique=True),
            IndexSchema(
                name="ix_customers_email",
                columns=["customer_email"],
                unique=False,
                index_type="btree",
                predicate="customer_email IS NOT NULL",
            ),
        ],
        check_constraints=["customer_id > 0"],
    )
    return DatabaseSchema(
        database_type="postgresql",
        generated_at=datetime(2026, 1, 1),
        schemas={"public": {"customers": table}},
    )


def test_write_contract_with_indexes_does_not_raise(tmp_path):
    # O bug: isto levantava TypeError ao serializar os IndexSchema.
    path = tmp_path / "schema.lock.json"
    ContractWriter(path).write(_schema_with_indexes())

    data = json.loads(path.read_text(encoding="utf-8"))
    indexes = data["schemas"]["public"]["tables"]["customers"]["indexes"]
    assert isinstance(indexes, list)
    assert all(isinstance(ix, dict) for ix in indexes)  # dicts, não objetos crus
    by_name = {ix["name"]: ix for ix in indexes}
    assert by_name["customers_pkey"]["columns"] == ["customer_id"]
    assert by_name["customers_pkey"]["unique"] is True
    assert by_name["ix_customers_email"]["predicate"] == "customer_email IS NOT NULL"


def test_write_then_reread_contract_is_empty_diff(tmp_path):
    # Idempotência com índices: init -> contrato -> relê -> diff vazio.
    schema = _schema_with_indexes()
    path = tmp_path / "schema.lock.json"
    ContractWriter(path).write(schema)

    reread = JsonSchemaReader(path).read()
    diff = SchemaComparator().compare(reread, schema)
    assert diff.is_compatible
    assert len(diff.changes) == 0
