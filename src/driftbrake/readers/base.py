# Classe base abstrata para leitores de schema.

from abc import ABC, abstractmethod

from driftbrake.core.models import DatabaseSchema


class SchemaReader(ABC):
    # Classe base abstrata para leitura de schemas de banco de dados.

    @abstractmethod
    def read(self) -> DatabaseSchema:
        """
        Lê e retorna o schema do banco de dados.

        DatabaseSchema: A representação completa do schema.
        SchemaConnectionError: Se a conexão com a fonte falhar.
        SchemaContractNotFoundError: Se a fonte do schema não for encontrada.
        """
