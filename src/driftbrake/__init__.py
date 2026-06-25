# Copyright (C) 2026 Yuri Pontes
#
# This package is a free and open-source project: you may redistribute it and/or modify it
# under the terms of the MIT License.
#
# This package is distributed in the hope that it will be useful,
# but without any warranty; without even the implied warranty of
# merchantability or fitness for a particular purpose.
#
# Library for detecting schema drift in databases and files
# (datasets - data lake folders).
# -----------------------------------------------------------------------------------------
# DriftBrake
# =========
#
# A schema contract guard for data pipelines. Detects, classifies, and reports schema
# changes in PostgreSQL databases.


from driftbrake.core.classifier import ImpactClassifier
from driftbrake.core.comparator import SchemaComparator
from driftbrake.core.decision import Decision, decide
from driftbrake.core.models import (
    ChangeType,
    ColumnSchema,
    DatabaseSchema,
    DiffResult,
    IndexSchema,
    SchemaChange,
    Severity,
    TableSchema,
)
from driftbrake.core.policy import Policy, load_policy
from driftbrake.driftbrake import DriftBrake
from driftbrake.exceptions import (
    # v0.1.0 hierarchy
    BreakingChangesDetected,
    # legacy (v0.0.2) — kept for backward compatibility
    BreakingSchemaChangeError,
    ConfigurationError,
    ContractMissingError,
    ContractWriteError,
    DriftBrakeError,
    MissingDatabaseURL,
    PolicyError,
    SchemaConnectionError,
    SchemaContractNotFoundError,
    SchemaDetectorError,
    SchemaNotFoundError,
    UserAborted,
)
from driftbrake.guard import SchemaGuard
from driftbrake.prompters import NonInteractivePrompter, StdinPrompter
from driftbrake.protocols import Prompter, Reporter
from driftbrake.readers.json.reader import JsonSchemaReader
from driftbrake.readers.parquet.reader import ParquetSchemaReader
from driftbrake.readers.postgres import PostgresSchemaReader
from driftbrake.reporters.facade_terminal import FacadeTerminalReporter as TerminalReporter

__version__ = "0.3.0"

__all__ = [
    # v0.1.0 facade
    "DriftBrake",
    # Decision
    "Decision",
    "decide",
    # Policy
    "Policy",
    "load_policy",
    # Protocols
    "Reporter",
    "Prompter",
    # Built-in implementations
    "TerminalReporter",
    "StdinPrompter",
    "NonInteractivePrompter",
    # v0.1.0 exceptions
    "DriftBrakeError",
    "BreakingChangesDetected",
    "ContractMissingError",
    "ContractWriteError",
    "MissingDatabaseURL",
    "PolicyError",
    "SchemaNotFoundError",
    "UserAborted",
    # Legacy API (v0.0.2)
    "SchemaGuard",
    "SchemaComparator",
    "ImpactClassifier",
    "PostgresSchemaReader",
    "JsonSchemaReader",
    "ParquetSchemaReader",
    "DatabaseSchema",
    "TableSchema",
    "ColumnSchema",
    "IndexSchema",
    "SchemaChange",
    "DiffResult",
    "Severity",
    "ChangeType",
    # legacy exceptions
    "SchemaDetectorError",
    "SchemaContractNotFoundError",
    "SchemaConnectionError",
    "BreakingSchemaChangeError",
    "ConfigurationError",
]
