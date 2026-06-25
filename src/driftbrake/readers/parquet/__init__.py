# Engine Parquet: reader, dataset particionado e adapter de tipos Arrow.
#
# Import lazy: o PyArrow só é carregado quando reader/dataset/adapter são usados.
# `import driftbrake` nunca puxa o PyArrow por este pacote.

__all__ = ["ArrowTypeAdapter", "ParquetSchemaReader"]


def __getattr__(name: str):
    if name == "ArrowTypeAdapter":
        from driftbrake.readers.parquet.type_adapter import ArrowTypeAdapter

        return ArrowTypeAdapter
    if name == "ParquetSchemaReader":
        from driftbrake.readers.parquet.reader import ParquetSchemaReader

        return ParquetSchemaReader
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
