# Hierarquia de exceções do DriftBrake.


class DriftBrakeError(Exception):
    """Exceção base. Toda exceção da lib herda desta."""

    exit_code: int = 1


class ContractMissingError(DriftBrakeError):
    """Contrato não encontrado e auto_init desabilitado."""

    exit_code = 4


class BreakingChangesDetected(DriftBrakeError):
    """Schema possui mudanças classificadas como bloqueantes."""

    exit_code = 2

    def __init__(self, result, message: str | None = None):
        self.result = result
        super().__init__(message or f"{result.breaking_count} breaking change(s) detected")


class UserAborted(DriftBrakeError):
    """Usuário recusou interativamente."""

    exit_code = 7


class MissingDatabaseURL(DriftBrakeError):
    """from_env() não encontrou DATABASE_URL no ambiente."""

    exit_code = 5


class PolicyError(DriftBrakeError):
    """Erro ao carregar ou parsear o arquivo de política."""

    exit_code = 5


class SchemaNotFoundError(DriftBrakeError):
    """Schema configurado não existe no banco."""

    exit_code = 5


class ContractWriteError(DriftBrakeError):
    """Falha ao escrever contrato no disco (permissão, espaço, FS)."""

    exit_code = 6


class MissingDependencyError(DriftBrakeError):
    """Extra opcional não instalado (ex.: driftbrake[parquet])."""

    exit_code = 5


class ParquetReadError(DriftBrakeError):
    """Falha ao ler um dataset Parquet (diretório vazio, footer inválido)."""

    exit_code = 3


# Exceções legadas (v0.0.2) mantidas para compatibilidade


class SchemaDetectorError(DriftBrakeError):
    """Exceção base legada."""

    exit_code: int = 1


class SchemaContractNotFoundError(SchemaDetectorError):
    """Contrato não encontrado (legado)."""

    exit_code = 4


class SchemaConnectionError(SchemaDetectorError):
    """Erro de conexão com o banco (legado)."""

    exit_code = 3


class BreakingSchemaChangeError(SchemaDetectorError):
    """Alterações críticas detectadas (legado)."""

    exit_code = 2


class ConfigurationError(SchemaDetectorError):
    """Erro de configuração (legado)."""

    exit_code = 5
