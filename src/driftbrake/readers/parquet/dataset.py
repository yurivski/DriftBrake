"""
Consolidação de dataset Parquet particionado — a peça sem precedente.

Varre o diretório, lê o footer de cada arquivo via `pyarrow.parquet.read_schema()`
(só metadado, não dados), escolhe um schema dominante e produz o relatório de
divergência inter-arquivo. É o coração da v0.3.0: detectar "esse dataset tem N
arquivos e M divergem do schema dominante".
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from driftbrake.core.type_system import CanonicalType
from driftbrake.exceptions import MissingDependencyError, ParquetReadError
from driftbrake.readers.parquet.type_adapter import ArrowTypeAdapter

# key=value de um caminho particionado estilo Hive (/year=2026/month=06/)
_PARTITION_SEGMENT = re.compile(r"^([^=/]+)=([^=/]+)$")

_VALID_STRATEGIES = ("most_common", "first_file", "latest_mtime")


@dataclass
class FieldDivergence:
    """Uma coluna de um arquivo que diverge do schema dominante."""

    file: str
    column: str
    expected: str | None  # tipo canônico (str) no dominante; None = coluna ausente no dominante
    found: str | None  # tipo canônico (str) no arquivo; None = coluna ausente no arquivo

    def to_dict(self) -> dict[str, str | None]:
        return {
            "arquivo": self.file,
            "coluna": self.column,
            "esperado": self.expected,
            "encontrado": self.found,
        }


@dataclass
class DatasetSchema:
    """Schema consolidado de um diretório Parquet + relatório de divergência."""

    columns: dict[str, CanonicalType]
    divergences: list[FieldDivergence] = field(default_factory=list)
    file_count: int = 0
    dominant_strategy: str = "most_common"
    partition_columns: list[str] = field(default_factory=list)
    nullability: dict[str, bool] = field(default_factory=dict)
    """Nulabilidade (required/optional) do schema dominante, lida do footer Arrow."""

    @property
    def is_consistent(self) -> bool:
        return not self.divergences

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_dominante": {name: str(ct) for name, ct in self.columns.items()},
            "divergencias": [d.to_dict() for d in self.divergences],
            "total_arquivos": self.file_count,
            "estrategia": self.dominant_strategy,
            "colunas_particao": self.partition_columns,
        }


def discover_parquet_files(directory: Path) -> list[Path]:
    """Lista os `.parquet` do diretório recursivamente, ordenados pelo nome."""
    return sorted(p for p in directory.rglob("*.parquet") if p.is_file())


def _partition_columns_from_path(file: Path, root: Path) -> set[str]:
    cols: set[str] = set()
    try:
        rel = file.relative_to(root)
    except ValueError:
        return cols
    for segment in rel.parts[:-1]:  # ignora o nome do arquivo
        m = _PARTITION_SEGMENT.match(segment)
        if m:
            cols.add(m.group(1))
    return cols


def _read_file(
    file: Path, adapter: ArrowTypeAdapter
) -> tuple[dict[str, CanonicalType], dict[str, bool]]:
    """Lê o footer uma vez e devolve (tipos canônicos, nulabilidade) por coluna."""
    import pyarrow.parquet as pq  # lazy

    arrow_schema = pq.read_schema(file)  # só o footer, não os dados
    types = {fld.name: adapter.to_canonical(fld.type) for fld in arrow_schema}
    nullables = {fld.name: bool(fld.nullable) for fld in arrow_schema}
    return types, nullables


def _file_schema(file: Path, adapter: ArrowTypeAdapter) -> dict[str, CanonicalType]:
    return _read_file(file, adapter)[0]


def _select_dominant(
    files: list[Path],
    schemas: dict[Path, dict[str, CanonicalType]],
    strategy: str,
) -> Path:
    """Retorna o arquivo cujo schema é o dominante, conforme a estratégia."""
    if strategy == "first_file":
        return files[0]
    if strategy == "latest_mtime":
        return max(files, key=lambda f: f.stat().st_mtime)

    # most_common: o schema (assinatura) mais frequente entre os arquivos
    def signature(schema: dict[str, CanonicalType]) -> tuple[tuple[str, str], ...]:
        return tuple(sorted((name, str(ct)) for name, ct in schema.items()))

    counts = Counter(signature(schemas[f]) for f in files)
    winner_sig = counts.most_common(1)[0][0]
    for f in files:
        if signature(schemas[f]) == winner_sig:
            return f
    return files[0]  # inalcançável; satisfaz o type checker


# Limiar de afinidade entre conjuntos de colunas (Jaccard). Acima dele, dois
# arquivos são a MESMA tabela (mesmo que um tipo difira, ou uma coluna falte);
# abaixo, são tabelas diferentes que por acaso estão na mesma pasta.
_AFFINITY_THRESHOLD = 0.5


def _require_pyarrow() -> None:
    try:
        import pyarrow.parquet  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercitado via monkeypatch nos testes
        raise MissingDependencyError(
            "PyArrow é necessário para ler datasets Parquet. Instale driftbrake[parquet]."
        ) from exc


def _resolve_dir(directory: str | Path, strategy: str) -> tuple[Path, list[Path]]:
    """Valida o diretório e a estratégia; devolve (root, arquivos não vazios)."""
    _require_pyarrow()
    if strategy not in _VALID_STRATEGIES:
        raise ParquetReadError(
            f"Estratégia de schema dominante inválida: {strategy!r}. "
            f"Use uma de {_VALID_STRATEGIES}."
        )
    root = Path(directory)
    if not root.exists() or not root.is_dir():
        raise ParquetReadError(f"Diretório do dataset não encontrado: {root}")
    files = discover_parquet_files(root)
    if not files:
        raise ParquetReadError(
            f"Nenhum arquivo .parquet encontrado em {root}. "
            "Diretório vazio não vira SchemaModel em silêncio."
        )
    return root, files


def _read_all(
    files: list[Path], root: Path, ignore_partition_columns: bool
) -> tuple[dict[Path, dict[str, CanonicalType]], dict[Path, dict[str, bool]], list[str]]:
    """Lê o footer de cada arquivo uma vez; remove colunas de partição se pedido."""
    adapter = ArrowTypeAdapter()
    partition_cols: set[str] = set()
    for f in files:
        partition_cols |= _partition_columns_from_path(f, root)

    raw_schemas: dict[Path, dict[str, CanonicalType]] = {}
    raw_nullables: dict[Path, dict[str, bool]] = {}
    for f in files:
        types, nullables = _read_file(f, adapter)
        if ignore_partition_columns:
            for col in partition_cols:
                types.pop(col, None)
                nullables.pop(col, None)
        raw_schemas[f] = types
        raw_nullables[f] = nullables
    return raw_schemas, raw_nullables, sorted(partition_cols)


def _consolidate(
    files: list[Path],
    root: Path,
    strategy: str,
    raw_schemas: dict[Path, dict[str, CanonicalType]],
    raw_nullables: dict[Path, dict[str, bool]],
    partition_cols: list[str],
) -> DatasetSchema:
    """Funde uma lista de arquivos num schema dominante + divergências inter-arquivo."""
    dominant_file = _select_dominant(files, raw_schemas, strategy)
    dominant = raw_schemas[dominant_file]
    dominant_nullable = raw_nullables[dominant_file]

    divergences: list[FieldDivergence] = []
    for f in files:
        schema = raw_schemas[f]
        rel = str(f.relative_to(root))
        for col, expected_ct in dominant.items():
            found_ct = schema.get(col)
            if found_ct is None:
                divergences.append(FieldDivergence(rel, col, str(expected_ct), None))
            elif found_ct != expected_ct:
                divergences.append(FieldDivergence(rel, col, str(expected_ct), str(found_ct)))
        for col, found_ct in schema.items():
            if col not in dominant:
                divergences.append(FieldDivergence(rel, col, None, str(found_ct)))

    return DatasetSchema(
        columns=dominant,
        divergences=divergences,
        file_count=len(files),
        dominant_strategy=strategy,
        partition_columns=partition_cols,
        nullability=dominant_nullable,
    )


def read_dataset(
    directory: str | Path,
    *,
    dominant_schema_strategy: str = "most_common",
    ignore_partition_columns: bool = True,
) -> DatasetSchema:
    """Consolida um diretório Parquet inteiro num único schema + divergências.

    Trata TODOS os arquivos como um só dataset (sem agrupar por tabela). Para o
    modelo "pasta = uma ou mais tabelas", use `discover_tables`.
    """
    root, files = _resolve_dir(directory, dominant_schema_strategy)
    raw_schemas, raw_nullables, partition_cols = _read_all(files, root, ignore_partition_columns)
    return _consolidate(
        files, root, dominant_schema_strategy, raw_schemas, raw_nullables, partition_cols
    )


def _cluster_by_affinity(files: list[Path], colsets: dict[Path, set[str]]) -> list[list[Path]]:
    """Agrupa arquivos por afinidade de NOMES de coluna (componentes conexas).

    Dois arquivos ficam na mesma tabela se a similaridade de Jaccard dos seus
    nomes de coluna >= limiar. Diferença de TIPO não separa (é drift dentro da
    tabela); conjuntos de coluna majoritariamente disjuntos separam (são tabelas
    distintas). É a heurística que distingue "dataset com drift" de "pasta de
    tabelas" — a assinatura `found None` que o teste do Argus expôs.
    """
    n = len(files)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):
            a, b = colsets[files[i]], colsets[files[j]]
            if not a and not b:
                union(i, j)
            elif a and b and len(a & b) / len(a | b) >= _AFFINITY_THRESHOLD:
                union(i, j)

    groups: dict[int, list[Path]] = {}
    for i, f in enumerate(files):
        groups.setdefault(find(i), []).append(f)
    # ordena por primeiro arquivo para nome/ordinal determinísticos
    return sorted(groups.values(), key=lambda g: str(g[0]))


def _table_name(cluster: list[Path], root: Path) -> str:
    """Nomeia a tabela de um grupo de arquivos.

    Subdiretório comum (ignorando partições Hive) -> nome do subdir; arquivo solto
    único -> stem do arquivo; vários arquivos soltos (um dataset) -> nome da pasta.
    """
    subdirs: set[str] = set()
    has_loose = False
    for f in cluster:
        seg = None
        for s in f.relative_to(root).parts[:-1]:
            if not _PARTITION_SEGMENT.match(s):
                seg = s
                break
        if seg is None:
            has_loose = True
        else:
            subdirs.add(seg)
    if not has_loose and len(subdirs) == 1:
        return next(iter(subdirs))
    if len(cluster) == 1 and has_loose:
        return cluster[0].stem
    return root.name


def discover_tables(
    directory: str | Path,
    *,
    dominant_schema_strategy: str = "most_common",
    ignore_partition_columns: bool = True,
) -> dict[str, DatasetSchema]:
    """Lê um diretório como UMA OU MAIS tabelas.

    Agrupa os arquivos `.parquet` por afinidade de colunas: arquivos que
    compartilham a maioria dos nomes de coluna são a mesma tabela (um dataset,
    com detecção de divergência inter-arquivo); conjuntos disjuntos são tabelas
    diferentes. Assim uma pasta `silver/` com cinco entidades vira cinco tabelas,
    e um dataset particionado vira uma só — sem descartar nada em silêncio.
    """
    root, files = _resolve_dir(directory, dominant_schema_strategy)
    raw_schemas, raw_nullables, partition_cols = _read_all(files, root, ignore_partition_columns)
    colsets = {f: set(raw_schemas[f]) for f in files}

    tables: dict[str, DatasetSchema] = {}
    for cluster in _cluster_by_affinity(files, colsets):
        name = _table_name(cluster, root)
        # desambigua colisões de nome (ex.: dois stems iguais em subpastas)
        unique = name
        suffix = 2
        while unique in tables:
            unique = f"{name}_{suffix}"
            suffix += 1
        tables[unique] = _consolidate(
            cluster, root, dominant_schema_strategy, raw_schemas, raw_nullables, partition_cols
        )
    return tables
