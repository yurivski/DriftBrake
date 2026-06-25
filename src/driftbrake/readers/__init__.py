# Pacote de schema readers.

from driftbrake.readers.base import SchemaReader
from driftbrake.readers.json.reader import JsonSchemaReader
from driftbrake.readers.postgres import PostgresSchemaReader

__all__ = ["SchemaReader", "PostgresSchemaReader", "JsonSchemaReader"]
