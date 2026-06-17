<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" 
            srcset="https://raw.githubusercontent.com/yurivski/DriftBrake/main/docs/img/db_banner_dark.svg">
    <img alt="DriftBrake-Banner" 
         src="https://raw.githubusercontent.com/yurivski/DriftBrake/main/docs/img/db_banner_white.svg" 
         width="560">
  </picture>
</div>

<div align="center">

### Detecte, classifique e bloqueie drifts de schemas no PostgreSQL antes que seus pipelines sejam corrompidos.

</div>

[![Tests](https://github.com/yurivski/DriftBrake/actions/workflows/ci.yml/badge.svg)](https://github.com/yurivski/DriftBrake/actions/workflows/ci.yml)
[![PyPI Latest Release](https://img.shields.io/pypi/v/driftbrake.svg)](https://pypi.org/project/driftbrake/)
[![PyPI Downloads](https://img.shields.io/pypi/dm/driftbrake.svg?label=PyPI%20downloads)](https://pypi.org/project/driftbrake/)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/MIT-License-blue.svg)

A ferramenta identifica bugs capazes de corromper ou quebrar pipelines em silêncio, antes do deploy em produção, com um conceito simples: você cria um "contrato" que descreve exatamente como seu banco deve ser. Antes de executar qualquer pipeline, a ferramenta compara o banco real com esse contrato e avisa (ou bloqueia) se algo mudou.

Consulte a documentação: [driftbrake.pages](https://driftbrake.pages.dev/#en/overview)

<br>

## DriftBrake

O DriftBrake atua antes da execução de pipelines, verificando se o banco real ainda respeita o contrato esperado pelos consumidores de dados. Ele detecta desvios, classifica o impacto e bloqueia execuções quando necessário, mas nunca altera o banco. DriftBrake não é uma ferramenta de migration. Ele não aplica mudanças no banco, não gera scripts SQL e não gerencia versões de schema.

## Pacote Python

Este arquivo README contém apenas informações básicas relacionadas à instalação do DriftBrake via pip. Esse pacote é experimental e pode sofrer alterações em versões futuras. O uso do DriftBrake pode ser feito por CLI ou (para personalização de políticas de detecção) implementado diretamente no código, consulte as instruções de compilação em ["Python API"](https://driftbrake.pages.dev/#en/python-api). 

O pacote Python para DriftBrake lê automaticamente o schema atual do banco de dados PostgreSQL, compara contra um contrato versionado, classifica os drifts por impacto e pode bloquear pipelines antes que eles quebrem em produção.

**NOTA:** Se estiver usando isso com um banco de dados que não seja PostgreSQL (MySQL, SQLite, SQL Server, etc.) você poderá encontrar erros inesperados. Na versão atual o DriftBrake é construído inteiramente em torno da semântica do PostgreSQL: o leitor de schema consulta `information_schema.schemata` e lê opções de índice exclusivas do Postgres (`postgresql_using`, `postgresql_where`), e a matriz de compatibilidade de tipos segue as regras de cast do PostgreSQL (`varchar`, `text`, `bigint`, `timestamptz`, etc.). Outros bancos ainda não são suportados.


## Instalação

```bash
# Instala o drive psycopg2-binary, necessário pra conexão postgre
pip install "driftbrake[postgres]"
```

> O extra `[dev]` inclui `pre-commit`, `ruff`, `mypy`, `pytest` e as demais ferramentas de desenvolvimento.


## Funcionamento

O fluxo da versão atual:

```
schema.lock.json (contrato versionado no Git)
        │
        ▼
DriftBrake conecta no PostgreSQL
        │
        ▼
lê schema atual automaticamente
        │
        ▼
compara esperado e atual
        │
        ├── OK ──────────────────── pipeline executa
        │
        └── BREAKING ────────────── pipeline bloqueado
                                    ├── exibe no terminal
                                    ├── gera schema_diff.json
                                    └── gera schema_report.html
```

### Tipos de mudança detectados

A ferramenta detecta as seguintes categorias de alteração em cada comparação:

| Tipo | O que significa |
|---|---|
| `table_added` | Uma tabela nova apareceu no banco |
| `table_removed` | Uma tabela que existia sumiu do banco |
| `column_added` | Uma coluna NOT NULL foi adicionada a uma tabela existente |
| `nullable_column_added` | Uma coluna nullable foi adicionada a uma tabela existente |
| `column_removed` | Uma coluna foi removida de uma tabela existente |
| `type_changed` | O tipo de dado de uma coluna mudou (ex: `INTEGER` → `TEXT`) |
| `nullable_changed` | A coluna deixou de aceitar NULL ou passou a aceitar |
| `default_changed` | O valor padrão da coluna mudou ou foi removido |
| `primary_key_changed` | Uma coluna ganhou ou perdeu a chave primária |
| `unique_changed` | Uma constraint `UNIQUE` foi adicionada ou removida |
| `foreign_key_changed` | Uma chave estrangeira foi alterada |
| `foreign_key_added` | Uma chave estrangeira foi criada onde não havia |
| `ordinal_position_changed` | A posição da coluna na tabela mudou |
| `possible_rename` | Uma coluna foi removida e outra coluna semelhante foi adicionada na mesma tabela. A ferramenta trata isso apenas como uma suspeita de rename, nunca como confirmação. Sempre classificado como `WARNING`. |

> `possible_rename` é uma heurística, nunca uma confirmação. O DriftBrake sinaliza a suspeita quando uma coluna removida e uma coluna adicionada parecem compatíveis por tipo. A validação final deve ser feita por quem revisa a migration.


### Confiança do `possible_rename`

Cada ocorrência de `possible_rename` traz um campo `confidence` que indica o grau de certeza da heurística:

| Nível | Critério |
|---|---|
| `high` | Nome similar + mesmo tipo + posição ordinal próxima (diferença ≤ 2) |
| `medium` | Mesmo tipo + posição ordinal próxima (diferença ≤ 2) |
| `low` | Apenas tipo compatível (SAFE ou WARNING na matriz de tipos) |


**Regras importantes:**

- `possible_rename` **nunca** é classificado como `BREAKING` automaticamente, é sempre `WARNING`.
- Um `confidence: "high"` ainda é uma suspeita, não uma certeza.
- Sempre revise as migrations antes de aceitar um rename com `driftbrake update-contract`.

<br>

## Licença

**MIT license**
