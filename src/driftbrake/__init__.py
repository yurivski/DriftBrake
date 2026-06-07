"""
DriftBrake
=========

A schema contract guard for data pipelines.
Detects, classifies, and reports schema changes in PostgreSQL databases.
"""

from driftbrake.classifiers.impact_classifier import ImpactClassifier
from driftbrake.comparators.schema_comparator import SchemaComparator
from driftbrake.decision import Decision, decide
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
from driftbrake.policy import Policy, load_policy
from driftbrake.prompters import NonInteractivePrompter, StdinPrompter
from driftbrake.protocols import Prompter, Reporter
from driftbrake.readers.json_reader import JsonSchemaReader
from driftbrake.readers.postgres import PostgresSchemaReader
from driftbrake.reporters.facade_terminal import FacadeTerminalReporter as TerminalReporter

__version__ = "0.2.0"

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
