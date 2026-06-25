# Leitor de schema PostgreSQL usando SQLAlchemy Inspector.

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from driftbrake.core.models import ColumnSchema, DatabaseSchema, IndexSchema, TableSchema
from driftbrake.exceptions import SchemaConnectionError, SchemaNotFoundError
from driftbrake.readers.base import SchemaReader


class PostgresSchemaReader(SchemaReader):
    """
    Lê metadados de schema de um banco de dados PostgreSQL usando SQLAlchemy.

    Suporta tanto uma string DATABASE_URL direta quanto parâmetros de conexão
    individuais (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD).
    """

    def __init__(
        self,
        database_url: str,
        schemas: list[str] | None = None,
        include_tables: list[str] | None = None,
        exclude_tables: list[str] | None = None,
    ) -> None:
        self.database_url = database_url
        self.schemas = schemas or ["public"]
        self.include_tables = include_tables
        self.exclude_tables = exclude_tables or []

    @classmethod
    def from_env(
        cls,
        schemas: list[str] | None = None,
        include_tables: list[str] | None = None,
        exclude_tables: list[str] | None = None,
    ) -> PostgresSchemaReader:
        """
        Cria um PostgresSchemaReader a partir de variáveis de ambiente.

        Usa DATABASE_URL se disponível; caso contrário, constrói a URL a partir
        das variáveis individuais DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD.
        """
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            host = os.getenv("DB_HOST", "localhost")
            port = os.getenv("DB_PORT", "5432")
            name = os.getenv("DB_NAME", "")
            user = os.getenv("DB_USER", "")
            password = os.getenv("DB_PASSWORD", "")
            if not name or not user:
                raise SchemaConnectionError(
                    "Database connection not configured. Set DATABASE_URL or "
                    "DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD environment variables."
                )
            database_url = f"postgresql://{user}:{password}@{host}:{port}/{name}"
        return cls(
            database_url=database_url,
            schemas=schemas,
            include_tables=include_tables,
            exclude_tables=exclude_tables,
        )

    def _should_include_table(self, table_name: str) -> bool:
        if self.exclude_tables and table_name in self.exclude_tables:
            return False
        if self.include_tables is not None:
            return table_name in self.include_tables
        return True

    def _extract_column(
        self,
        col: dict[str, Any],
        pk_columns: list[str],
        unique_constraints: list[dict[str, Any]],
        fk_info: list[dict[str, Any]],
        ordinal_position: int,
    ) -> ColumnSchema:
        col_name = col["name"]
        col_type = str(col["type"])
        nullable = bool(col.get("nullable", True))
        default = col.get("default")
        is_pk = col_name in pk_columns
        is_unique = any(col_name in u.get("column_names", []) for u in unique_constraints)
        fks = [fk for fk in fk_info if col_name in fk.get("constrained_columns", [])]

        return ColumnSchema(
            name=col_name,
            type=col_type,
            nullable=nullable,
            default=default,
            primary_key=is_pk,
            unique=is_unique,
            foreign_key=fks,
            ordinal_position=ordinal_position,
        )

    def _read_table(self, inspector: Any, schema_name: str, table_name: str) -> TableSchema:
        columns = inspector.get_columns(table_name, schema=schema_name)
        pk_info = inspector.get_pk_constraint(table_name, schema=schema_name)
        fk_info = inspector.get_foreign_keys(table_name, schema=schema_name)
        indexes = inspector.get_indexes(table_name, schema=schema_name)
        unique_constraints = inspector.get_unique_constraints(table_name, schema=schema_name)
        check_constraints = inspector.get_check_constraints(table_name, schema=schema_name)

        pk_columns = pk_info.get("constrained_columns", [])
        col_schemas: dict[str, ColumnSchema] = {}

        for ordinal, col in enumerate(columns, start=1):
            col_schema = self._extract_column(col, pk_columns, unique_constraints, fk_info, ordinal)
            col_schemas[col_schema.name] = col_schema

        index_schemas: list[IndexSchema] = []
        for idx in indexes:
            if not idx.get("name"):
                continue
            dialect_opts = idx.get("dialect_options", {})
            index_type = dialect_opts.get("postgresql_using", "btree")
            predicate_raw = dialect_opts.get("postgresql_where")
            predicate = str(predicate_raw) if predicate_raw is not None else None
            index_schemas.append(
                IndexSchema(
                    name=idx["name"],
                    columns=idx.get("column_names", []),
                    unique=bool(idx.get("unique", False)),
                    index_type=index_type,
                    predicate=predicate,
                )
            )

        return TableSchema(
            name=table_name,
            schema=schema_name,
            columns=col_schemas,
            indexes=index_schemas,
            check_constraints=[c["sqltext"] for c in check_constraints],
        )

    def read(self) -> DatabaseSchema:
        """
        Conecta ao PostgreSQL e lê todos os metadados de schema.

        DatabaseSchema: Representação completa do schema.
        SchemaConnectionError: Se a conexão falhar.
        """
        try:
            from sqlalchemy import create_engine
            from sqlalchemy import inspect as sa_inspect
        except ImportError as exc:
            raise SchemaConnectionError(
                "SQLAlchemy is required for PostgresSchemaReader. "
                "Install it with: pip install sqlalchemy psycopg2-binary"
            ) from exc

        try:
            engine = create_engine(self.database_url)
            inspector = sa_inspect(engine)
        except Exception as exc:
            raise SchemaConnectionError(f"Failed to connect to the database: {exc}") from exc

        db_schemas: dict[str, dict[str, TableSchema]] = {}

        try:
            from sqlalchemy import text

            with engine.connect() as conn:
                result = conn.execute(text("SELECT schema_name FROM information_schema.schemata"))
                existing = {row[0] for row in result}
            missing = [s for s in self.schemas if s not in existing]
            if missing:
                raise SchemaNotFoundError(
                    f"Schema(s) not found in database: {missing}. "
                    f"Existing schemas: {sorted(existing)}"
                )

            for schema_name in self.schemas:
                db_schemas[schema_name] = {}
                try:
                    table_names = inspector.get_table_names(schema=schema_name)
                except Exception as exc:
                    raise SchemaConnectionError(
                        f"Failed to list tables in schema '{schema_name}': {exc}"
                    ) from exc

                for table_name in table_names:
                    if not self._should_include_table(table_name):
                        continue
                    try:
                        table_schema = self._read_table(inspector, schema_name, table_name)
                        db_schemas[schema_name][table_name] = table_schema
                    except Exception as exc:
                        raise SchemaConnectionError(
                            f"Failed to read metadata for table '{schema_name}.{table_name}': {exc}"
                        ) from exc
        finally:
            engine.dispose()

        return DatabaseSchema(
            database_type="postgresql",
            generated_at=datetime.now(),
            schemas=db_schemas,
        )
