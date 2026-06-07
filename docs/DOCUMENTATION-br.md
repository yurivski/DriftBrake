<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" 
            srcset="https://raw.githubusercontent.com/yurivski/DriftBrake/main/docs/img/db_banner_dark.svg">
    <img alt="DriftBrake-Banner" 
         src="https://raw.githubusercontent.com/yurivski/DriftBrake/main/docs/img/db_banner_white.svg" 
         width="560">
  </picture>
</div>

-----------------
<br>

<div align="center">

**DriftBrake lê o esquema atual do PostgreSQL automaticamente, compara com um contrato versionado, classifica os drifts por impacto (BREAKING, WARNING, SAFE) e bloqueia pipelines quando alterações incompatíveis são detectadas, antes que causem falhas em produção.**

</div>

> [!NOTE]
> - Lê o schema do PostgreSQL
> - Compara contra um contrato
> - Classifica mudanças por impacto
> - Bloqueia pipelines com breaking changes
> - Gera relatórios JSON, HTML e Markdown

<br>

> **Procurando as regras de classificação?** Veja [`AUDIT-br.md`](AUDIT-br.md) — referência independente para cada decisão SAFE / WARNING / BREAKING, incluindo a matriz de compatibilidade de tipos e a heurística `possible_rename`.

<br>

<div align="center">

### Atalho por categoria: clique no título sublinhado para expandir.

</div>

<details>
<summary><b><code>VERSÕES DA API — v0.0.2 e v0.1.0</code></b> — <i>Clique aqui para visualizar</i></summary>

<br>

Duas APIs coexistem no DriftBrake. Ambas são suportadas, completamente funcionais, e usam o mesmo motor de detecção. A diferença está na interface, no estilo de saída e na extensibilidade.

### API v0.0.2 — `SchemaGuard`

A API original. Ainda disponível e sem alterações. Pipelines existentes continuam funcionando sem modificação.

| | |
|---|---|
| **Ponto de entrada principal** | `SchemaGuard.from_env(contract_path=...).assert_compatible()` |
| **Estilo de saída** | Painéis Rich verbosos, tabelas formatadas (usa a biblioteca `rich`) |
| **Objeto de resultado** | `DiffResult` — via `guard.check()` |
| **Configuração** | `driftbrake.yml` (YAML, `fail_on`, `tables.ignore`, `columns.ignore`) |
| **Construtor** | `SchemaGuard(database_url=..., contract_path=..., config_path=..., output_json=..., fail_on=[...])` |
| **Entrada de baixo nível** | `guard.check()` → `DiffResult` |
| **Entrada de alto nível** | `guard.assert_compatible()` → `sys.exit` em caso de falha |

### API v0.1.0 — `DriftBrake`

A nova classe. Criada pra embutir em pipelines Python com saída concisa, overrides de política, reporters customizados e suporte a async.

| | |
|---|---|
| **Pontos de entrada principais** | `DriftBrake.run_from_env()` ou `DriftBrake.from_env().protect()` |
| **Estilo de saída** | Linhas de log concisas com prefixo: `[INFO]`, `[WARN]`, `[BLOCKED]` |
| **Objeto de resultado** | `DiffResult` — via `evaluate()` ou `protect()` |
| **Configuração** | `driftbrake.policy.yml` (`overrides`, `ignore_tables`, `ignore_columns`) |
| **Construtor** | `DriftBrake(database_url=..., policy=..., reporter=..., interactive=...)` |
| **Pontos de entrada** | `evaluate()`, `protect()`, `protect_or_exit()`, `run_from_env()` |

> [!NOTE]
> `DriftBrake` usa `SchemaGuard` internamente. Não são implementações concorrentes — `DriftBrake` é um wrapper de nível mais alto em torno do mesmo motor de comparação.

---
</details>

<br>

<details>
<summary><b><code>INSTALAÇÃO</code></b> — <i>Clique aqui para visualizar</i></summary>

#### Cenários

O DriftBrake suporta três caminhos de instalação dependendo do que você quer fazer.

**1. Instalação básica (CLI carrega, comandos de banco falham com erro claro):**

```bash
pip install driftbrake
```

A CLI fica disponível imediatamente. Qualquer comando que acesse o banco (ex: `driftbrake init`, `driftbrake check`) falhará com uma mensagem de erro clara apontando para o driver `psycopg2` ausente. Use isso apenas se quiser inspecionar as opções da CLI antes de se comprometer com a instalação completa.

**2. Instalação completa — CLI e biblioteca, uso real (mais comum):**

```bash
pip install "driftbrake[postgres]"
```

O extra `[postgres]` instala o `psycopg2-binary`, o driver necessário para ler um banco PostgreSQL. Isso é o que você quer para todo caso de uso real — CLI ou biblioteca.

**3. Desenvolvimento (contribuição ou testes locais):**

```bash
git clone https://github.com/yurivski/DriftBrake
cd DriftBrake
pip install -e ".[postgres,dev]"
pre-commit install
```

O extra `[dev]` adiciona `pytest`, `ruff`, `mypy`, `build`, `twine` e `pre-commit`.

<br>

Verifique a instalação:

```bash
driftbrake --help
driftbrake --version
```

```
DriftBrake 0.1.0
```

> [!NOTE]
> Se você instalar `driftbrake` sem `[postgres]`, a CLI carrega mas o primeiro comando que acessa o banco falha com um erro claro apontando para o driver ausente. O erro é intencional e descritivo, não é um bug.

---
</details>

<br>

<details>
<summary><b><code>Resumo por situação</code></b> — <i>Clique aqui para visualizar</i></summary>

<br>

| Situação | Comando |
|---|---|
| Primeira vez usando a ferramenta | `driftbrake init` |
| Verificar se o banco mudou antes de rodar o pipeline | `driftbrake check` |
| Comparar dois estados sem mexer no contrato | `driftbrake diff --old arquivo1.json --new arquivo2.json` |
| Guardar o estado atual do banco como referência futura | `driftbrake snapshot --output snapshots/nome.json` |
| Uma migration foi aplicada e as mudanças são intencionais | `driftbrake update-contract --yes` |
| Ver o relatório de mudanças em HTML | `driftbrake check --html relatorio.html` |
| Embutir proteção dentro de um pipeline Python | `from driftbrake import DriftBrake; DriftBrake.run_from_env()` |


### Resumo dos comandos CLI

| Comando | Descrição |
|---|---|
| `driftbrake init` | Gera `schema.lock.json` a partir do banco atual |
| `driftbrake check` | Compara o banco contra o contrato e retorna exit code |
| `driftbrake diff` | Compara dois JSONs ou um JSON contra o banco |
| `driftbrake snapshot` | Captura o schema atual sem comparar |
| `driftbrake update-contract` | Atualiza o contrato para refletir o estado atual |

---
</details>

<br>

<details>
<summary><b><code>Config. do seu arquivo .env</code></b> — <i>Clique aqui para visualizar</i></summary>

<br>

As credenciais abaixo são exemplo de como devem estar no seu `.env`, são usadas automaticamente quando você não passa `--db-url`:

| Variável | Valor |
|---|---|
| `DATABASE_URL` | `postgresql://user:pass@localhost:5432/mydb` |
| `DB_HOST` | `localhost` |
| `DB_PORT` | `5432` |
| `DB_NAME` | `mydb` |
| `DB_USER` | `postgres` |
| `DB_PASSWORD` | `secrets` |

**Acesso ao banco de dados:** a ferramenta usa o SQLAlchemy por baixo dos panos. Quando você roda qualquer comando, ela monta a URL de conexão no formato `postgresql://usuario:senha@host:porta/banco` e usa o driver `psycopg2` para se conectar. O SQLAlchemy então usa o `Inspector`, uma API interna que consulta o catálogo do PostgreSQL (`information_schema` e `pg_catalog`) para ler metadados de tabelas, colunas, tipos, constraints e índices. Nenhuma linha dos seus dados é lida, apenas a estrutura.

**Prioridade da conexão:** se `DATABASE_URL` estiver definida no ambiente, ela tem prioridade total. Só se ela não existir, a ferramenta monta a URL juntando `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` e `DB_PASSWORD`.

---
</details>

<br>

<details>
<summary><b><code>Config. do arquivo YML</code></b> — <i>Clique aqui para visualizar</i></summary>

<br>

Crie um `driftbrake.yml` baseado no `driftbrake.example.yml`:

```yaml
fail_on:
  - BREAKING

tables:
  ignore:
    - alembic_version
    - flyway_schema_history

columns:
  ignore:
    orders:
      - updated_at
      [...]
```

Passe o arquivo para a CLI com `--config driftbrake.yml` ou para o `SchemaGuard` com `config_path="driftbrake.yml"`.

> [!WARNING]
> **`driftbrake.yml` (formato v0.0.2): as chaves aninhadas `tables.ignore` / `columns.ignore` foram removidas na v0.2.0.** Carregar um arquivo com essas chaves agora lança `ConfigurationError` imediatamente. Migre para `driftbrake.policy.yml` com as chaves planas `ignore_tables` / `ignore_columns`. Veja a seção [Arquivos de política](#arquivos-de-política) abaixo.

> Para o novo formato de arquivo de política usado pela classe `DriftBrake` (`driftbrake.policy.yml` com `overrides`, `ignore_tables`, `ignore_columns`), veja a seção [Arquivos de política](#arquivos-de-política) abaixo.

---
</details>


<br>

<details>
<summary><b><code>Conexão com o banco de dados</code></b> — <i>Clique aqui para visualizar</i></summary>

<br>

A ferramenta aceita a URL do banco de três formas, em ordem de prioridade:

**1. Argumento direto na CLI:**

```bash
driftbrake check --db-url "postgresql://user:pass@localhost:5432/mydb"
```

**2. Variável de ambiente `DATABASE_URL`:**

```bash
export DATABASE_URL="postgresql://user:pass@localhost:5432/mydb"
driftbrake check
```

**3. Variáveis individuais no `.env` ou no ambiente:**

```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mydb
DB_USER=postgres
DB_PASSWORD=secret
```

---
</details>

<br>

<details>
<summary><b><code>Comandos e exemplos de saídas</code></b> — <i>Clique aqui para visualizar</i></summary>

<br>

### 0. `--version` e `--info` — Verificar versão e ambiente

#### `driftbrake --version`

Exibe a versão instalada do DriftBrake e encerra.

```bash
driftbrake --version
```

```
DriftBrake 0.1.0
```

<br>

#### `driftbrake --info`

Exibe informações completas sobre o ambiente de execução e encerra. Útil para reportar problemas.

```bash
driftbrake --info
```

```
DriftBrake 0.1.0
Python 3.13.5
Platform Linux-6.5.0-parrot7-amd64
SQLAlchemy 2.0.49
```

<br>

---

### 1. `init` — Criar o contrato pela primeira vez

Conecta ao seu PostgreSQL, lê a estrutura completa do banco (tabelas, colunas, tipos, constraints, índices) e salva tudo em um arquivo JSON. Esse arquivo se torna o contrato, a "foto" do estado atual do banco.

**Primeira execução:** sem o contrato, não há nada para comparar. O `init` é sempre o ponto de partida. Você roda uma vez, commita o arquivo no git, e a partir daí qualquer mudança no banco pode ser detectada. O `init` vem antes de tudo porque ele *cria* o ponto de referência. Não faz sentido rodar `check` antes de ter um contrato.

#### `driftbrake init`

Conecta no banco, lê o schema atual e cria o contrato `schema.lock.json`. Esse arquivo deve ser versionado no Git.

```bash
driftbrake init \
  --db-url "$DATABASE_URL" \
  --schemas public \
  --output schema.lock.json
```

<br>

**Opções:**

| Opção | Padrão | O que faz |
|---|---|---|
| `--db-url` | lê do `.env` | URL completa de conexão com o PostgreSQL |
| `--schemas` | `public` | Quais schemas do PostgreSQL capturar. Separe por vírgula para mais de um |
| `--output` | `schema.lock.json` | Nome e caminho do arquivo de contrato gerado |

**Exit codes:** `0` sucesso, `3` erro de conexão, `6` erro de escrita no sistema de arquivos.

<br>

```bash
# Forma mais simples, usa as variáveis do .env automaticamente
driftbrake init

# Especificando o banco explicitamente
driftbrake init --db-url "postgresql://user:pass@localhost:5432/mydb"

# Capturando schemas específicos (além do public)
driftbrake init --schemas "public,analytics,staging"

# Salvando o contrato em outro caminho
driftbrake init --output "contratos/schema_producao.lock.json"

# Tudo junto
driftbrake init \
  --db-url "postgresql://user:pass@localhost:5432/mydb" \
  --schemas "public" \
  --output "schema.lock.json"
```

<br>

**Exemplo de arquivo gerado:**
```json
{
  "contract_version": "1.0",
  "generated_by": "driftbrake",
  "driftbrake_version": "0.1.0",
  "database_type": "postgresql",
  "generated_at": "2026-05-19T10:30:00",
  "schemas": {
    "public": {
      "tables": {
        "users": {
          "columns": {
            "id": { "type": "INTEGER", "nullable": false, "primary_key": true },
            "name": { "type": "VARCHAR", "nullable": true }
          },
          "indexes": ["users_pkey"],
          "check_constraints": []
        }
      }
    }
  }
}
```

<br>

**Saídas possíveis:**
```
Conectando ao banco de dados e lendo o schema (public)...
[OK] Contrato de schema salvo em: schema.lock.json
     12 tabela(s) capturada(s) em 1 schema(s).
```

<br>

### 2. `check` — Verificar se o banco mudou

Lê o banco de dados atual e compara com o contrato existente (`schema.lock.json`). Lista todas as diferenças encontradas, classifica cada uma por severidade e retorna um código de saída que pode ser usado em pipelines de CI/CD.

**Comando de rotina:** o `check` é o coração da ferramenta. Você roda antes de qualquer pipeline, migration ou deploy. Se ele retornar código 0, está tudo bem. Se retornar código 2, algo crítico mudou e o pipeline deve ser bloqueado.

**Comparar contrato → banco (e não banco → banco):** o contrato representa o estado *acordado* do banco. Ao comparar contra ele, você detecta desvios do que foi planejado, independente de quando ou como a mudança aconteceu.

#### `driftbrake check`

Compara o banco atual contra o contrato. É o comando central para uso em CI/CD.

```bash
driftbrake check \
  --db-url "$DATABASE_URL" \
  --contract schema.lock.json \
  --fail-on BREAKING \
  --json schema_diff.json \
  --html schema_report.html \
  --markdown schema_report.md
```

<br>

**Opções:**

| Opção | Padrão | O que faz |
|---|---|---|
| `--db-url` | lê do `.env` | URL de conexão com o PostgreSQL |
| `--contract` | `schema.lock.json` | Caminho do arquivo de contrato para comparar |
| `--fail-on` | `BREAKING` | Níveis que causam saída com código 2. Use `BREAKING,WARNING` para ser mais restritivo |
| `--json` | — | Caminho para salvar um relatório em JSON |
| `--html` | — | Caminho para salvar um relatório em HTML (visual, com tabelas coloridas) |
| `--markdown` | — | Caminho para salvar um relatório em Markdown |
| `--config` | — | Arquivo `.yml` com configurações adicionais (exclusões de tabelas, etc.) |

**Exit codes:** veja a [seção Exit Codes abaixo](#exit-codes) para o mapeamento completo.

<br>

```bash
# Forma mais simples, usa schema.lock.json no diretório atual e variáveis do .env
driftbrake check

# Especificando tudo
driftbrake check \
  --db-url "postgresql://user:pass@localhost:5432/mydb" \
  --contract "schema.lock.json"

# Falhar também em warnings (mais restritivo)
driftbrake check --fail-on "BREAKING,WARNING"

# Gerar relatórios além da saída no terminal
driftbrake check \
  --json "relatorios/diff.json" \
  --html "relatorios/diff.html" \
  --markdown "relatorios/diff.md"

# Usando um arquivo de configuração (yml)
driftbrake check --config "driftbrake.yml"

# Comando completo para uso em CI
driftbrake check \
  --db-url "postgresql://user:pass@localhost:5432/mydb" \
  --contract "schema.lock.json" \
  --fail-on "BREAKING" \
  --html "relatorios/diff.html"
```

<br>

**Exemplo prático (schema compatível):**

```bash
driftbrake check --db-url "$DATABASE_URL" --contract schema.lock.json
```

```
Conectando ao banco... OK
Comparando contra schema.lock.json...

DRIFTBRAKE CHECK PASSED

Resumo:
  BREAKING: 0
  WARNING:  0
  SAFE:     0

Nenhuma mudança detectada. Pipeline liberado.
```

<br>

**Exemplo prático (breaking change detectado):**

```bash
driftbrake check \
  --db-url "$DATABASE_URL" \
  --contract schema.lock.json \
  --fail-on BREAKING \
  --json schema_diff.json \
  --html schema_report.html
```

```
Conectando ao banco... OK
Comparando contra schema.lock.json...

DRIFTBRAKE CHECK FAILED

Resumo:
  BREAKING: 2
  WARNING:  1
  SAFE:     1

BREAKING
  public.customers    email              coluna removida
  public.orders       total_amount       tipo mudou: numeric → text

WARNING
  public.orders       customer_id        foreign key adicionada

SAFE
  public.customers    created_at         coluna nullable adicionada

JSON:  schema_diff.json
HTML:  schema_report.html

Pipeline bloqueado. (exit code 2)
```

<br>

### 3. `diff` — Comparar duas versões de schema sem usar o contrato

Compara duas fontes de schema livremente, dois arquivos JSON, ou um arquivo JSON contra um banco ao vivo. Não usa nem modifica o `schema.lock.json`. É uma comparação pontual, exploratória.

**Separado do `check`:** o `check` tem uma função específica, validar o banco contra o contrato oficial. O `diff` é mais flexível: você pode comparar um snapshot de ontem com o banco de hoje, ou dois arquivos de ambientes diferentes (produção e homologação), sem comprometer o contrato.

#### `driftbrake diff`

**Arquivo vs arquivo:**

```bash
driftbrake diff \
  --old schema_before.json \
  --new schema_after.json \
  --json schema_diff.json
```

<br>

**Arquivo vs banco ao vivo:**

```bash
driftbrake diff \
  --old schema.lock.json \
  --new-db "$DATABASE_URL" \
  --html schema_diff.html
```

<br>

**Opções:**

| Opção | Padrão | O que faz |
|---|---|---|
| `--old` | obrigatório | Caminho para o arquivo JSON que representa o estado "esperado" / "antes" |
| `--new` | — | Caminho para o arquivo JSON que representa o estado "atual" / "depois" |
| `--new-db` | — | URL do banco de dados a ser usado como estado "atual" (alternativa ao `--new`) |
| `--json` | — | Caminho para salvar o relatório em JSON |
| `--html` | — | Caminho para salvar o relatório em HTML |

> [!CAUTION]
> Você deve informar `--new` **ou** `--new-db`, nunca os dois ao mesmo tempo. Se nenhum for informado, a ferramenta retorna erro.

<br>

### 4. `snapshot` — Tirar uma foto do banco sem criar contrato

Conecta ao banco, lê o schema e salva em um arquivo JSON, igual ao `init`, mas com um nome de arquivo diferente por padrão (`schema.snapshot.json`) e sem a intenção de ser o contrato oficial.

**Função:** o `init` cria o contrato oficial do projeto. O `snapshot` serve para guardar estados intermediários, "como estava o banco na sexta-feira antes da migration", "estado do banco em homologação", "versão antes do deploy". Esses arquivos podem ser usados depois como `--old` no `diff` para investigar o que mudou.

#### `driftbrake snapshot`

```bash
driftbrake snapshot \
  --db-url "$DATABASE_URL" \
  --output historico/schema_2026-05-19.json \
  --schemas public
```

<br>

**Opções:**

| Opção | Padrão | O que faz |
|---|---|---|
| `--db-url` | lê do `.env` | URL de conexão com o PostgreSQL |
| `--output` | `schema.snapshot.json` | Caminho do arquivo de snapshot gerado |
| `--schemas` | `public` | Schemas do PostgreSQL a capturar |

> [!NOTE]
> **Dica de uso:** criar um snapshot antes de cada migration é uma boa prática. Se algo der errado, você consegue fazer um `diff` para entender exatamente o que mudou.

<br>

### 5. `update-contract` — Aceitar as mudanças e atualizar o contrato

Reconecta ao banco, lê o schema atual e sobrescreve o `schema.lock.json` com esse novo estado. Em outras palavras: "estou ciente das mudanças, elas são intencionais, e quero que passem a ser o novo contrato". Quando uma mudança é planejada e aprovada, uma migration legítima, uma refatoração de schema deliberada, o contrato precisa ser atualizado para refletir o novo estado. Sem esse comando, o `check` continuaria reportando as mudanças para sempre como se fossem problemas.

**Confirmação interativa:** sobrescrever o contrato é uma ação irreversível sem o git. A confirmação existe como proteção contra execuções acidentais.

**Comando `--yes`:** em ambientes de CI/CD não há terminal interativo. O `--yes` (ou `-y`) pula a confirmação para que o comando possa rodar em scripts automatizados após aprovação humana no processo de review.

#### `driftbrake update-contract`

```bash
driftbrake update-contract \
  --db-url "$DATABASE_URL" \
  --contract schema.lock.json \
  --yes
```

<br>

**Opções:**

| Opção | Padrão | O que faz |
|---|---|---|
| `--db-url` | lê do `.env` | URL de conexão com o PostgreSQL |
| `--contract` | `schema.lock.json` | Caminho do contrato a ser sobrescrito |
| `--yes` / `-y` | `false` | Pula a pergunta de confirmação |
| `--schemas` | `public` | Schemas a capturar para o novo contrato |

> [!WARNING]
> **Atenção:** sem `--yes`, o comando pede confirmação explícita antes de sobrescrever o contrato.

---
</details>

<br>

<details>
<summary><b><code>Exit Codes</code></b> — <i>Clique aqui para visualizar</i></summary>

<br>

O DriftBrake usa exit codes determinísticos para que o CI/CD possa decidir sucesso ou falha exclusivamente pelo código de saída.

| Código | Significado | Quando ocorre |
|---|---|---|
| `0` | Sucesso — schema compatível ou operação concluída | `check` não encontrou mudanças, ou todas abaixo do limite `--fail-on` |
| `1` | Erro genérico do DriftBrake | Base catch-all; subclasses específicas abaixo |
| `2` | Mudança crítica detectada — pipeline deve ser bloqueado | `check` encontrou mudanças que correspondem ao `--fail-on` |
| `3` | Erro de conexão com o banco | Host/porta/senha errados, servidor inacessível, problema de rede |
| `4` | Contrato ausente ou inválido | Arquivo não encontrado, JSON malformado, campos obrigatórios ausentes |
| `5` | Erro de configuração | YAML inválido, erro de sintaxe na política, `DATABASE_URL` ausente, schema configurado mas não existe no banco |
| `6` | Erro de escrita no sistema de arquivos | Não foi possível escrever o arquivo de contrato (sistema de arquivos somente leitura, permissão negada) |
| `7` | Usuário abortou | Prompt interativo respondido com "não" |

> [!NOTE]
> Cada exceção Python levantada pela biblioteca mapeia para um desses códigos. Veja a seção [Hierarquia de exceções](#hierarquia-de-exceções) para o mapeamento completo.

---
</details>

<br>

<details>
<summary><b><code>Atalho de Desenvolvimento</code></b> — <i>Clique aqui para visualizar</i></summary>

<br>

O repositório possui o arquivo `Makefile` com comandos de atalho:

```bash
pip install -e ".[dev]"
make test       # roda todos os testes
make lint       # verifica estilo
make check      # lint + typecheck + testes
```

---
</details>

<br>

<details>
<summary><b><code>Formato do contrato</code></b> — <i>Clique aqui para visualizar</i></summary>

<br>

O contrato é gerado pelo comando `init` e deve ser versionado no Git. Representa o schema que o pipeline espera encontrar.

```json
{
  "contract_version": "1.0",
  "generated_by": "driftbrake",
  "driftbrake_version": "0.1.0",
  "database_type": "postgresql",
  "generated_at": "2026-05-19T10:30:00",
  "schemas": {
    "public": {
      "tables": {
        "customers": {
          "columns": {
            "id": {
              "type": "integer",
              "nullable": false,
              "default": null,
              "primary_key": true,
              "unique": false,
              "foreign_key": false,
              "ordinal_position": 1
            },
            "email": {
              "type": "text",
              "nullable": false,
              "default": null,
              "primary_key": false,
              "unique": true,
              "foreign_key": false,
              "ordinal_position": 2
            }
          }
        }
      }
    }
  }
}
```

---
</details>

<br>

<details>
<summary><b><code>Formato dos relatórios gerados: JSON, HTML e Markdown</code></b> — <i>Clique aqui para visualizar</i></summary>

<br>

### JSON (`--json schema_diff.json`)

O relatório JSON encapsula uma lista de objetos `SchemaChange` serializados via `SchemaChange.to_dict()`. Os nomes reais dos campos são:

```json
{
  "status": "failed",
  "checked_at": "2026-05-19T10:30:00",
  "database_type": "postgresql",
  "summary": { "breaking": 2, "warning": 1, "safe": 3 },
  "changes": [
    {
      "change_type": "column_removed",
      "severity": "BREAKING",
      "schema_name": "public",
      "table_name": "customers",
      "column_name": "email",
      "field_name": null,
      "old_value": "email",
      "new_value": null,
      "description": "Column 'email' was removed from 'customers'.",
      "suggestion": null
    }
  ]
}
```

**Referência de campos para um único objeto de mudança:**

| Campo | Tipo | Descrição |
|---|---|---|
| `change_type` | string | O valor do enum `ChangeType`, ex: `"column_removed"`, `"type_changed"` |
| `severity` | string | `"BREAKING"`, `"WARNING"` ou `"SAFE"` |
| `schema_name` | string | Schema do PostgreSQL, ex: `"public"` |
| `table_name` | string | Tabela onde a mudança foi detectada |
| `column_name` | string ou null | Nome da coluna (null para mudanças no nível da tabela) |
| `field_name` | string ou null | Sub-campo dentro da coluna que mudou (ex: `"nullable"`) |
| `old_value` | string ou null | Valor anterior, convertido para string |
| `new_value` | string ou null | Novo valor, convertido para string |
| `description` | string | Descrição legível da mudança |
| `suggestion` | string ou null | Dica opcional de remediação |
| `confidence` | string ou null | Presente apenas em `possible_rename`: `"low"`, `"medium"` ou `"high"` |

### HTML (`--html schema_report.html`)

Relatório visual com resumo geral, inspirado no modelo do ydata-profiling (antigo *Pandas Profiling*). Usa os templates em `templates/`.

### Markdown (`--markdown schema_report.md`)

Relatório em formato Markdown, para comentários automáticos em pull requests.

---
</details>

<br>

---

<div align="center">

## CLI e Biblioteca

</div>

O DriftBrake oferece duas portas de entrada para o mesmo motor: uma ferramenta de linha de comando e uma biblioteca Python. Mesma detecção, mesma classificação, mesmos relatórios. Eles diferem em **como você os integra**.

### Use a CLI quando…

- Seu pipeline é um script shell, um Makefile, ou um job de CI escrito em YAML (GitHub Actions, GitLab CI).
- Você quer rodar verificações de drift manualmente no terminal durante a revisão de código.
- Você está chamando como uma barreira independente antes de outras ferramentas executarem: `driftbrake check && dbt run && python publish.py`.
- O banco vive em um lugar e o pipeline roda em outro, o exit code da CLI é o contrato entre eles.
- Você está começando e quer aprender a ferramenta digitando comandos.

### Use a biblioteca quando…

- Seu pipeline já é um programa Python (Suporte a duckdb, spark, delta lake, etc., em breve).
- Você quer inspecionar os resultados antes de reagir, logar no Slack, escrever na sua própria stack de observabilidade, rodar lógica customizada baseada em quais tabelas mudaram.
- Você precisa de um reporter ou prompter customizado (logs JSON estruturados, um fluxo de aprovação no Slack, um reporter silencioso para testes).
- Você quer overrides de política aplicados programaticamente com base no ambiente (staging vs. produção).
- Você precisa de suporte a async dentro de um pipeline `async def`.

### Atalho mental

Se seu pipeline tem **formato de shell**, use a CLI. Se tem **formato Python**, use a biblioteca. Não há limitação funcional em nenhum dos dois — escolha o que faz seu pipeline ficar mais legível.

### Comparação rápida

| Aspecto | CLI | Biblioteca |
|---|---|---|
| Custo de setup | `pip install` + `driftbrake init` | `pip install` + 3 linhas de Python |
| Estilo de saída | Verboso, painéis Rich, tabelas formatadas | Linhas de log concisas com prefixo (`[INFO]`, `[WARN]`, `[BLOCKED]`) |
| Customização | Configuração YAML | Tudo que Python consegue fazer |
| Async | Não se aplica | `aprotect()`, `aprotect_or_exit()` |
| Reporter customizado | Não suportado | Protocolo `Reporter` completo |
| Tratamento de erros | Exit codes | Exceções tipadas OU exit codes (sua escolha) |
| Melhor para | CI/CD, pipelines shell, revisão manual | Pipelines Python, integrações customizadas, bibliotecas |

<br>

---

<div align="center">

## Usando DriftBrake no seu pipeline Python

</div>

A classe `DriftBrake` orquestra o ciclo completo de proteção: lê o contrato, escaneia o banco, compara, classifica, aplica políticas, decide e reporta. Você instancia uma vez no topo do pipeline, chama um método, e é isso.

Há **quatro pontos de entrada** dependendo de quanto controle você quer.

### Ponto de entrada 1: `DriftBrake.run_from_env()` — o one-liner

Se você só quer "bloquear o pipeline em caso de drift de schema" sem cerimônia, este é o ponto de entrada:

```python
from driftbrake import DriftBrake

DriftBrake.run_from_env()
# Se drift foi detectado e corresponde a fail_on, o processo encerra aqui com o código certo.
# Se não há drift, a execução continua.

run_pipeline()
```

É só isso. `run_from_env()` lê `DATABASE_URL` do ambiente, roda a verificação, e traduz **todos** os `DriftBrakeError` — incluindo erros de construção como variáveis de ambiente ausentes, para o `sys.exit(code)` apropriado. Você não vê exceções; você vê exit codes.

Use quando:

- Seu pipeline é um script Python que roda como processo separado (cron job, `BashOperator` do Airflow, entrypoint Docker).
- Você quer semântica de exit code, não semântica de exceção.
- Você não precisa inspecionar o resultado antes de decidir o que fazer.

<br>

### Ponto de entrada 2: `DriftBrake.from_env().protect()` — orientado a exceções

Quando você quer capturar exceções e reagir no código:

```python
from driftbrake import DriftBrake
from driftbrake.exceptions import (
    BreakingChangesDetected,
    SchemaConnectionError,
    UserAborted,
)

try:
    result = DriftBrake.from_env().protect()
except BreakingChangesDetected as e:
    notify_slack(f"Pipeline bloqueado: {len(e.result.changes)} breaking changes")
    raise
except SchemaConnectionError:
    notify_slack("Pipeline não conseguiu alcançar o banco")
    raise
except UserAborted:
    notify_slack("Usuário abortou interativamente")
    raise

# Continua com o pipeline
run_pipeline(result)
```

`protect()` retorna um `DiffResult` em caso de sucesso e lança exceções tipadas em caso de falha. Você decide o que fazer com cada uma.

Use quando:

- Você está dentro de um programa Python maior que gerencia seus próprios erros.
- Você quer diferenciar entre modos de falha (conexão vs. drift vs. abort do usuário).
- Você precisa logar/notificar antes de re-lançar.

<br>

### Ponto de entrada 3: `DriftBrake.from_env().evaluate()` — inspecionar antes de agir

Quando você quer ver o que mudou *antes* de decidir o que fazer:

```python
from driftbrake import DriftBrake

db = DriftBrake.from_env()
decision, result = db.evaluate()
# Retorna (Decision, DiffResult)

print(f"Decisão: {decision.severity}")
print(f"Breaking: {result.breaking_count}")
print(f"Warning:  {result.warning_count}")
print(f"Safe:     {result.safe_count}")

# Ramifica com base no que foi encontrado
if result.breaking_count > 0:
    handle_breaking(result)
elif result.warning_count > 5:
    handle_many_warnings(result)
else:
    run_pipeline()
```

`evaluate()` é a passagem de decisão pura, sem exceções, sem prompts, sem impressão. Apenas o resultado e a decisão. Útil para dashboards, fluxos customizados, ou quando você quer renderizar o resultado do seu próprio jeito.

O tipo de retorno é `(Decision, DiffResult)`. `Decision` tem `.action` (`"release"`, `"ask"` ou `"block"`), `.severity` (`"none"`, `"safe"`, `"warning"`, `"breaking"`), `.reason` e `.exit_code`.

<br>

### Ponto de entrada 4: `DriftBrake(...)` construção direta — controle total

Quando você precisa passar políticas, reporters customizados, ou sobrescrever valores de ambiente:

```python
from driftbrake import DriftBrake, TerminalReporter
from driftbrake.policy import load_policy

policy = load_policy("policies/strict.yml")

db = DriftBrake(
    database_url="postgresql://user:pass@host:5432/db",
    contract_path="contracts/production.lock.json",
    policy=policy,
    schemas=["public", "analytics"],
    fail_on=["BREAKING", "WARNING"],   # mais restritivo que o padrão
    ask_on=[],                          # nunca prompt, mesmo interativamente
    interactive=False,                  # força modo não interativo
    verbose=True,                       # saída detalhada do reporter
    reporter=TerminalReporter(verbose=True),  # reporter explícito
)

db.protect()
run_pipeline()
```

Use quando você precisa de controle preciso sobre cada parâmetro, ex: configurações diferentes por ambiente.

<br>

### Construtor `DriftBrake` — referência completa de parâmetros

```python
DriftBrake(
    database_url: str,
    contract_path: str = "schema.lock.json",
    config_path: str | None = None,
    policy_path: str | None = None,
    auto_init: bool = True,
    interactive: bool | Literal["auto"] = "auto",
    ask_on: list[str] | None = None,    # padrão: ["WARNING"]
    fail_on: list[str] | None = None,   # padrão: ["BREAKING"]
    output_json: str | None = None,
    output_html: str | None = None,
    output_markdown: str | None = None,
    schemas: list[str] | None = None,   # padrão: ["public"]
    verbose: bool = False,
    reporter: Reporter | None = None,
    prompter: Prompter | None = None,
)
```

**Notas dos parâmetros:**

| Parâmetro | Padrão | Observações |
|---|---|---|
| `database_url` | obrigatório | URL completa de conexão com o PostgreSQL |
| `contract_path` | `"schema.lock.json"` | Caminho para o arquivo de contrato |
| `config_path` | `None` | Caminho para `driftbrake.yml` (configuração estilo v0.0.2, **removido na v0.2.0** — lança `ConfigurationError` se as chaves `tables.ignore` / `columns.ignore` estiverem presentes) |
| `policy_path` | `None` | Caminho para `driftbrake.policy.yml` (política estilo v0.1.0, preferencial) |
| `auto_init` | `True` | Se `True`, cria o contrato automaticamente na primeira execução |
| `interactive` | `"auto"` | Veja a seção [parâmetro interactive](#o-parâmetro-interactive) |
| `ask_on` | `["WARNING"]` | Severidades que disparam um prompt de confirmação |
| `fail_on` | `["BREAKING"]` | Severidades que lançam `BreakingChangesDetected` |
| `output_json` | `None` | Caminho para salvar relatório JSON |
| `output_html` | `None` | Caminho para salvar relatório HTML |
| `output_markdown` | `None` | Caminho para salvar relatório Markdown |
| `schemas` | `["public"]` | Schemas do PostgreSQL a escanear |
| `verbose` | `False` | Ativa saída detalhada no reporter padrão |
| `reporter` | `FacadeTerminalReporter` | Reporter customizado implementando o protocolo `Reporter` |
| `prompter` | `StdinPrompter` ou `NonInteractivePrompter` | Prompter customizado implementando o protocolo `Prompter` |

`from_env(**kwargs)` aceita todos os mesmos kwargs exceto `database_url`, que é resolvido do ambiente. Qualquer kwarg passado sobrescreve o valor resolvido do ambiente.

<br>

### O parâmetro `interactive`

`interactive` controla se o DriftBrake vai solicitar confirmação do usuário para severidades em `ask_on` (padrão `WARNING`). Aceita três valores:

| Valor | Comportamento | Quando usar |
|---|---|---|
| `"auto"` (padrão) | Solicita apenas se stdin e stdout são TTYs (`sys.stdin.isatty() and sys.stdout.isatty()`) | Padrão para código que roda tanto em terminais quanto em CI — seguro em qualquer lugar |
| `True` | Sempre solicita | Desenvolvimento local quando você quer ser perguntado mesmo ao redirecionar saída |
| `False` | Nunca solicita; trata cada ask como "não" (`NonInteractivePrompter` retorna `False`) | CI/CD, cron, Docker, Airflow — qualquer lugar sem humano |

O modo `"auto"` é o que você quer 99% do tempo. Ele usa `sys.stdin.isatty()` e `sys.stdout.isatty()` para decidir. Em um job de CI (sem TTY), resolve para `False`. No seu terminal, resolve para `True`. Você não precisa pensar nisso.

Se precisar sobrescrever por ambiente:

```python
import os

is_ci = os.environ.get("CI") == "true"
db = DriftBrake.from_env(interactive=not is_ci)
```

<br>

### Pipelines async

Se seu pipeline é `async`, use as variantes assíncronas:

```python
import asyncio
from driftbrake import DriftBrake

async def main():
    result = await DriftBrake.from_env().aprotect()
    await run_async_pipeline(result)

asyncio.run(main())
```

`aprotect()` e `aprotect_or_exit()` são wrappers sobre as versões síncronas, implementados com `asyncio.to_thread`. O scan roda em um worker thread para que o event loop permaneça responsivo — útil quando seu pipeline tem outras tarefas concorrentes (heartbeat, atualizações de status, queries paralelas).

<br>

### Context manager

Para a semântica "execute este bloco apenas se o schema estiver OK":

```python
from driftbrake import DriftBrake

with DriftBrake.from_env().guard_block():
    # Este bloco só executa se a verificação de drift passou.
    # Se uma breaking change for detectada, o bloco é ignorado e uma exceção é lançada.
    run_pipeline()
```

A verificação acontece no `__enter__`. Exceções dentro do bloco propagam normalmente (sem supressão).

<br>

### Arquivos de política

A classe `DriftBrake` suporta um formato de arquivo de política com três seções:

```yaml
# driftbrake.policy.yml
overrides:
  column_added_nullable: WARNING      # padrão é SAFE; tornando mais restritivo
  column_added_with_default: BREAKING # padrão é WARNING; tornando estrito
  default_changed: BREAKING           # padrão é WARNING; tornando estrito
  possible_rename: BREAKING           # tratar todos os renames como BREAKING
  ordinal_position_changed: SAFE      # relaxar mudanças de posição ordinal
  index_removed: BREAKING             # tratar remoção de índice como bloqueante

ignore_tables:
  - alembic_version
  - flyway_schema_history

ignore_columns:
  - users.updated_at
  - orders.last_synced
```

Carregar e aplicar:

```python
from driftbrake import DriftBrake
from driftbrake.policy import load_policy

# Método 1: passar o caminho; DriftBrake carrega
db = DriftBrake.from_env(policy_path="driftbrake.policy.yml")

# Método 2: carregar explicitamente, modificar no código se necessário, passar o objeto
policy = load_policy("driftbrake.policy.yml")
policy.ignore_tables.append("audit_log")  # adição dinâmica
db = DriftBrake.from_env(policy=policy)
```

**Como `apply_policy` funciona**

`apply_policy` executa como pós-processamento entre `guard.check()` e `decide()`. Ele recebe um `DiffResult` e uma `Policy` e retorna um novo `DiffResult` com os ajustes aplicados. Três operações acontecem em sequência:

1. **Filtrar `ignore_tables`**: qualquer mudança cujo `table_name` esteja em `ignore_tables` é removida inteiramente do resultado.
2. **Filtrar `ignore_columns`**: qualquer mudança cujo `table_name.column_name` corresponda a uma entrada em `ignore_columns` é removida.
3. **Aplicar overrides de severidade**: para cada mudança restante, se o `change_type.value` for uma chave em `overrides`, a severidade é substituída pelo valor configurado e `[overridden by policy: SEVERITY]` é anexado à descrição (trilha de auditoria).

A chave do override é o valor string de `change_type.value` (minúsculas, separado por underscore):

```yaml
overrides:
  column_added_nullable: WARNING      # chave = "column_added_nullable"
  column_added_with_default: BREAKING # chave = "column_added_with_default"
  column_added_not_null: WARNING      # chave = "column_added_not_null"
  not_null_constraint_added: WARNING  # chave = "not_null_constraint_added"
  default_changed: BREAKING           # chave = "default_changed"
  possible_rename: BREAKING           # chave = "possible_rename"
  ordinal_position_changed: SAFE      # chave = "ordinal_position_changed"
  column_removed: WARNING             # chave = "column_removed"
  index_removed: BREAKING             # chave = "index_removed"
  index_modified: WARNING             # chave = "index_modified"
```

> [!NOTE]
> `apply_policy` é uma função pura, não muta o `DiffResult` original. Sempre retorna um novo objeto. Isso torna seguro chamá-la múltiplas vezes ou inspecionar o resultado pré-política para comparação.

**Precedência: `config_path` (Settings) e `policy_path` (Policy)**

Quando ambos `config_path` e `policy_path` são fornecidos, eles operam em **etapas diferentes do pipeline** e não entram em conflito:

| Camada | Arquivo | Aplicado | Efeito |
|---|---|---|---|
| Settings (`config_path`) | `driftbrake.yml` | **Antes** da comparação | Filtra tabelas/colunas para que nunca sejam comparadas; controla os limiares `fail_on` / `warn_on` |
| Policy (`policy_path`) | `driftbrake.policy.yml` | **Depois** da comparação | Remove ou reclassifica mudanças que já foram detectadas |

Uma tabela listada tanto em `tables.ignore` (Settings) quanto em `ignore_tables` (Policy) simplesmente nunca é comparada — o filtro da Policy é no-op para ela. Não há conflito; a camada de Settings vence ao eliminar a mudança antes que a camada de Policy a veja.

> [!WARNING]
> `config_path` (`driftbrake.yml`) com `tables.ignore` / `columns.ignore` foi **removido na v0.2.0**. O uso dessas chaves agora lança `ConfigurationError`. Prefira `policy_path` (`driftbrake.policy.yml`) para todas as novas integrações.

Para as regras de classificação completas que os overrides modificam, veja [`AUDIT-br.md`](AUDIT-br.md).

<br>

### Reporters e prompters customizados

O reporter padrão imprime no terminal com prefixos `[INFO]` / `[WARN]` / `[BLOCKED]`. Para enviar resultados para outros destinos (logs JSON, Slack, UI customizada), implemente o protocolo `Reporter`.

**Protocolo `Reporter` (de `protocols.py`):**

```python
def on_no_drift(self, result: DiffResult) -> None
def on_safe(self, result: DiffResult) -> None
def on_warning(self, result: DiffResult) -> None
def on_breaking(self, result: DiffResult) -> None
def on_contract_missing(self, contract_path: str) -> None
def on_contract_created(self, contract_path: str) -> None
def on_released(self) -> None
def on_blocked(self, reason: str) -> None
```

**Protocolo `Prompter` (de `protocols.py`):**

```python
def confirm_create_contract(self, contract_path: str) -> bool
def confirm_continue_with_warnings(self, result: DiffResult) -> bool
def confirm_continue_with_safe(self, result: DiffResult) -> bool
```

**Exemplo: reporter JSON estruturado**

```python
import json, sys
from driftbrake import DriftBrake

class StructuredJSONReporter:
    """Emite um objeto JSON por evento, no stderr."""
    def _emit(self, payload):
        print(json.dumps(payload), file=sys.stderr, flush=True)

    def on_no_drift(self, r): self._emit({"event": "no_drift"})
    def on_safe(self, r): self._emit({"event": "safe", "count": r.safe_count})
    def on_warning(self, r): self._emit({"event": "warning", "count": r.warning_count})
    def on_breaking(self, r): self._emit({"event": "breaking", "count": r.breaking_count})
    def on_contract_missing(self, path): self._emit({"event": "contract_missing", "path": path})
    def on_contract_created(self, path): self._emit({"event": "contract_created", "path": path})
    def on_released(self): self._emit({"event": "released"})
    def on_blocked(self, reason): self._emit({"event": "blocked", "reason": reason})

DriftBrake.from_env(reporter=StructuredJSONReporter()).protect()
```

O mesmo padrão funciona para `Prompter` (substituir confirmação interativa por aprovação no Slack, negar por padrão para verificações de segurança, etc.).

**Diretrizes de design para Reporter**

Ao escrever um reporter customizado, siga estas convenções para manter o comportamento previsível:

- **Cada método `on_*` deve se comportar de forma previsível, independente de quais outros eventos foram disparados.** Não faça `on_safe` ficar silencioso quando `on_breaking` também foi chamado. Isso é comportamento condicional, difícil de raciocinar para quem chama.
- **Verbosidade pertence dentro do método** (via `self.verbose`), não como função de quais outros eventos estão presentes na mesma execução.
- **Reporters não tomam decisões de negócio.** Um reporter apenas produz saída. Ele nunca decide se deve bloquear, abortar ou continuar — essas decisões vivem em `decide()` e `protect()`.
- **Um reporter silencioso é válido** (útil para testes), mas deve ser intencionalmente silencioso, não acidentalmente silencioso. Um reporter que suprime saída quando há breaking changes e parece uma execução limpa é um bug, não uma feature.
- **`on_breaking` deve escrever no stderr** (como o `FacadeTerminalReporter` padrão faz). Breaking changes são uma condição de erro; elas pertencem ao stream de erro.
- **Ordem dos eventos**: `protect()` chama eventos do reporter nesta ordem: `on_safe` → `on_warning` → `on_breaking` → `on_blocked` (ou `on_released`). Cada evento dispara independentemente se as mudanças correspondentes estão presentes — não há lógica de "chamar apenas o pior".

<br>

---

<div align="center">

## API legada v0.0.2 — `SchemaGuard`

</div>

A API original `SchemaGuard` ainda está disponível e sem alterações. Novo código deve preferir `DriftBrake`, mas pipelines existentes construídos sobre `SchemaGuard.assert_compatible()` continuam funcionando sem modificação.

### Integração simples em um pipeline (estilo v0.0.2)

```python
from driftbrake import SchemaGuard

def run_pipeline():
    print("Executando ETL...")

def main():
    SchemaGuard.from_env(
        contract_path="schema.lock.json",
        fail_on=["BREAKING"]
    ).assert_compatible()

    run_pipeline()

if __name__ == "__main__":
    main()
```

> [!NOTE]
> Se o banco tiver mudanças incompatíveis, `assert_compatible()` imprime o relatório, gera os arquivos e encerra o processo com `exit code 2`. O estilo de saída é verboso estilo CLI com painéis Rich, diferente da saída concisa estilo pipeline do `DriftBrake.protect()`.

<br>

### Construção manual com `SchemaGuard`

```python
from driftbrake import SchemaGuard

guard = SchemaGuard(
    database_url="postgresql://user:pass@localhost:5432/mydb",
    contract_path="schema.lock.json",
    config_path="driftbrake.yml",        # opcional
    output_json="schema_diff.json",      # opcional
    output_html="schema_report.html",    # opcional
    output_markdown="schema_report.md",  # opcional
    fail_on=["BREAKING"],
    schemas=["public", "raw"],           # opcional, padrão: ["public"]
)

guard.assert_compatible()
run_pipeline()
```

### Inspecionando o resultado manualmente

```python
from driftbrake import SchemaGuard
from driftbrake.models import Severity

guard = SchemaGuard.from_env(contract_path="schema.lock.json")
result = guard.check()  # retorna DiffResult

print(f"Total de mudanças: {len(result.changes)}")
print(f"Breaking: {result.breaking_count}")
print(f"Warning:  {result.warning_count}")
print(f"Safe:     {result.safe_count}")

for change in result.changes:
    if change.severity == Severity.BREAKING:
        print(f"  BREAKING | {change.table_name}.{change.column_name}: {change.description}")

if result.has_breaking:
    guard.save_reports(result)
    raise SystemExit(2)
```

### Usando `SchemaComparator` diretamente

```python
from driftbrake.readers.postgres import PostgresSchemaReader
from driftbrake.readers.json_reader import JsonSchemaReader
from driftbrake.comparators.schema_comparator import SchemaComparator

expected = JsonSchemaReader("schema.lock.json").read()
current  = PostgresSchemaReader("postgresql://user:pass@host/db").read()

result = SchemaComparator().compare(expected=expected, current=current)

for change in result.changes:
    print(f"{change.severity.value:8} | {change.schema_name}.{change.table_name} | {change.description}")
```

<br>

---

<div align="center">

## Hierarquia de exceções

</div>

Toda exceção lançada pelo DriftBrake herda de `DriftBrakeError`. Cada uma carrega um atributo `exit_code` que corresponde à [tabela de Exit Codes](#exit-codes).

### Exceções v0.1.0

| Exceção | Exit code | Quando é lançada |
|---|---|---|
| `DriftBrakeError` | `1` | Classe base — falha genérica |
| `BreakingChangesDetected` | `2` | `protect()` detectou drift correspondendo ao `fail_on`. Carrega o `DiffResult` em `.result` |
| `SchemaConnectionError` | `3` | Não consegue conectar ao banco (também levantada pelo caminho v0.1.0 via `PostgresSchemaReader`) |
| `ContractMissingError` | `4` | Arquivo de contrato não encontrado quando `auto_init=False` |
| `MissingDatabaseURL` | `5` | Variável de ambiente `DATABASE_URL` não definida e nenhuma URL passada explicitamente |
| `PolicyError` | `5` | Arquivo de política inválido (ausente, YAML malformado, severidade desconhecida) |
| `SchemaNotFoundError` | `5` | Um schema listado em `schemas=[...]` não existe no banco |
| `ContractWriteError` | `6` | Não consegue escrever o arquivo de contrato (permissão, sistema de arquivos somente leitura) |
| `UserAborted` | `7` | Prompt interativo respondido com "não" |

> [!NOTE]
> `SchemaConnectionError` se origina na camada legada v0.0.2 (`PostgresSchemaReader`) mas se propaga sem modificação pelo caminho v0.1.0. Qualquer chamada a `guard.check()`, seja do `SchemaGuard` ou do `DriftBrake`, pode lançá-la. Capture-a explicitamente se precisar diferenciar falhas de conexão de falhas de drift.

### Exceções legadas v0.0.2 (ainda lançadas pelo `SchemaGuard`)

| Exceção | Exit code | Quando é lançada |
|---|---|---|
| `SchemaDetectorError` | `1` | Base legada — agora herda de `DriftBrakeError` |
| `SchemaConnectionError` | `3` | Não consegue conectar ao banco |
| `SchemaContractNotFoundError` | `4` | Arquivo de contrato ausente ou JSON inválido |
| `ConfigurationError` | `5` | Configuração inválida |
| `BreakingSchemaChangeError` | `2` | Versão legada de `BreakingChangesDetected` |

Todas as exceções legadas agora herdam de `DriftBrakeError`. Código que captura `DriftBrakeError` captura tanto erros novos quanto legados. Código que captura exceções legadas específicas continua funcionando exatamente como antes.

### Mapeamento completo exceção - exit code

| Código | Exceção(ões) | Origem |
|---|---|---|
| `1` | `DriftBrakeError`, `SchemaDetectorError` | Classes base |
| `2` | `BreakingChangesDetected`, `BreakingSchemaChangeError` | Drift BREAKING encontrado correspondendo ao `fail_on` |
| `3` | `SchemaConnectionError` | Banco inacessível, senha errada, erro de rede |
| `4` | `ContractMissingError`, `SchemaContractNotFoundError` | Contrato não encontrado ou JSON inválido |
| `5` | `MissingDatabaseURL`, `PolicyError`, `ConfigurationError`, `SchemaNotFoundError` | Erros de configuração |
| `6` | `ContractWriteError` | Não consegue escrever contrato (permissões, FS somente leitura) |
| `7` | `UserAborted` | Prompt interativo respondido com "não" |

### Exemplo: capturando tudo

```python
from driftbrake import DriftBrake
from driftbrake.exceptions import DriftBrakeError

try:
    DriftBrake.from_env().protect()
except DriftBrakeError as e:
    # Uma única captura cobre todos os modos de falha do DriftBrake
    logger.error(f"{type(e).__name__}: {e}")
    sys.exit(e.exit_code)
```

### Exemplo: tratamento diferenciado

```python
from driftbrake import DriftBrake
from driftbrake.exceptions import (
    BreakingChangesDetected,
    SchemaConnectionError,
    SchemaNotFoundError,
    ContractWriteError,
)

try:
    DriftBrake.from_env().protect()
except BreakingChangesDetected as e:
    # e.result é um DiffResult
    alert_team("schema_breaking", changes=e.result.changes)
    raise
except SchemaConnectionError:
    alert_team("database_unreachable")
    raise
except SchemaNotFoundError:
    alert_team("schema_misconfigured")
    raise
except ContractWriteError:
    alert_team("filesystem_error")
    raise
```

<br>

---

<div align="center">

## Funcionamento

</div>

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
compara esperado contra atual
        │
        ▼
classifica mudanças por severidade (SAFE / WARNING / BREAKING)
        │
        ▼
aplica overrides de política (se um arquivo de política foi carregado)
        │
        ▼
toma a decisão (release / ask / block)
        │
        ├── release ─────────────── pipeline executa
        ├── ask ─────────────────── prompt ao usuário (somente interativo)
        └── block ────────────────── pipeline bloqueado
                                    ├── exibe no terminal
                                    ├── gera schema_diff.json
                                    └── gera schema_report.html
```

### Tipos de mudança detectados

A ferramenta detecta as seguintes categorias de alteração em cada comparação:

| Tipo | O que significa | Severidade padrão |
|---|---|---|
| `table_added` | Uma tabela nova apareceu no banco | SAFE |
| `table_removed` | Uma tabela que existia sumiu do banco | BREAKING |
| `column_added_nullable` | Uma nova coluna nullable foi adicionada a uma tabela existente | SAFE |
| `column_added_with_default` | Uma nova coluna NOT NULL com valor padrão foi adicionada | WARNING |
| `column_added_not_null` | Uma nova coluna NOT NULL sem valor padrão foi adicionada | BREAKING |
| `column_removed` | Uma coluna foi removida de uma tabela existente | BREAKING |
| `type_changed` | O tipo de dado de uma coluna mudou (ex: `INTEGER` → `TEXT`) | Varia — veja matriz de tipos |
| `not_null_constraint_added` | A coluna parou de aceitar NULL (restrição NOT NULL adicionada) | BREAKING |
| `not_null_constraint_removed` | A coluna passou a aceitar NULL (restrição NOT NULL removida) | WARNING |
| `default_changed` | O valor padrão da coluna mudou ou foi removido | WARNING |
| `primary_key_changed` | Uma coluna ganhou ou perdeu a chave primária | BREAKING |
| `unique_changed` | Uma constraint `UNIQUE` foi adicionada ou removida | WARNING |
| `foreign_key_changed` | Uma chave estrangeira foi alterada | BREAKING |
| `foreign_key_added` | Uma chave estrangeira foi criada onde não havia | WARNING |
| `ordinal_position_changed` | A posição da coluna na tabela mudou | WARNING |
| `possible_rename` | Uma coluna foi removida e outra coluna semelhante foi adicionada na mesma tabela. A ferramenta trata isso apenas como uma suspeita de rename, nunca como confirmação. | WARNING (sempre) |
| `index_added` | Um novo índice foi criado na tabela | SAFE |
| `index_removed` | Um índice existente foi removido | WARNING |
| `index_modified` | Um índice mudou colunas, tipo, unicidade ou predicado | BREAKING |

> [!IMPORTANT]
> Para a lógica de classificação completa — *por que* cada mudança é SAFE, WARNING ou BREAKING — veja [`AUDIT-br.md`](AUDIT-br.md). É a referência independente para cada decisão de classificação.

> [!NOTE]
> Adições de coluna usam **três tipos de mudança distintos** com chaves de override separadas. Adicionar uma coluna nullable é sempre SAFE. Adicionar uma coluna NOT NULL com default é WARNING (linhas existentes recebem o default). Adicionar uma coluna NOT NULL sem default é BREAKING (inserts existentes que não fornecem a coluna irão falhar). Overrides de política podem ser aplicados a cada um independentemente:
> ```yaml
> overrides:
>   column_added_nullable: WARNING        # tornar adições nullable mais restritas
>   column_added_with_default: BREAKING   # tornar NOT NULL+default estrito
>   column_added_not_null: WARNING        # relaxar NOT NULL sem default
> ```

<br>

### `possible_rename` — heurística de detecção

**Como funciona:** para cada coluna removida em uma tabela, o comparador escaneia todas as colunas adicionadas na mesma tabela procurando a melhor correspondência. A correspondência exige **tipos compatíveis** (SAFE ou WARNING na matriz de compatibilidade de tipos). Tipos incompatíveis (conversão BREAKING) desqualificam uma coluna da detecção de rename — elas são reportadas como mudanças BREAKING + SAFE/BREAKING separadas.

**Atribuição de confiança:**

| Nível | Critério |
|---|---|
| `high` | Nome similar + mesmo tipo + `|pos_antiga - pos_nova|` ≤ 2 |
| `medium` | Mesmo tipo + `|pos_antiga - pos_nova|` ≤ 2 |
| `low` | Apenas tipo compatível (SAFE ou WARNING na matriz de tipos) |

**Similaridade de nome** (de `_names_are_similar`): uma correspondência de prefixo ≥ 3 caracteres, uma correspondência de sufixo ≥ 3 caracteres, ou um nome contém o outro.

**Exemplo no relatório JSON:**

```json
{
  "change_type": "possible_rename",
  "severity": "WARNING",
  "schema_name": "public",
  "table_name": "customers",
  "column_name": "customer_email",
  "field_name": null,
  "old_value": "customer_email",
  "new_value": "email",
  "description": "Column 'customer_email' removed and 'email' added with compatible type. Possible rename.",
  "suggestion": "If this is a rename, update the schema contract with the new column name 'email'.",
  "confidence": "medium"
}
```

**Comportamento intencional mas surpreendente:**

- DROP `customer_email` (text) + ADD `email` (text): tipos são compatíveis → **um** WARNING `possible_rename`.
- DROP `customer_email` (text) + ADD `amount` (integer): tipos são incompatíveis (conversão BREAKING) → **duas** mudanças separadas: um BREAKING (`column_removed`) + o resultado da classificação de coluna adicionada (`column_added_nullable`, `column_added_with_default`, ou `column_added_not_null`).

**Regras importantes:**

- `possible_rename` **nunca** é classificado como `BREAKING` automaticamente — sempre `WARNING`.
- Um `confidence: "high"` ainda é uma suspeita, não uma certeza.
- Sempre revise as migrations antes de aceitar um rename com `driftbrake update-contract`.

**Para forçar detecção estrita de drop+add** (suprimindo completamente a heurística de rename):

```yaml
overrides:
  possible_rename: BREAKING
```

Para a lógica completa da heurística, veja [`AUDIT-br.md`](AUDIT-br.md#a-heuristica-possible_rename).

<br>

## Fluxo típico após uma migration:

```bash
# 1. Rodar a migration no banco
psql -U postgres -d mydb -f migration_001.sql

# 2. Verificar o que mudou
driftbrake check

# 3. Se as mudanças são as esperadas, aceitar e atualizar o contrato
driftbrake update-contract --yes

# 4. Commitar o novo contrato junto com a migration
git add schema.lock.json migration_001.sql
git commit -m "migration: adiciona coluna email_verificado na tabela users"
```

## Uso sem `--db-url` (via `.env`)

Em todos os comandos, a opção `--db-url` é opcional. Quando omitida, a ferramenta busca as credenciais na seguinte ordem:

1. Variável de ambiente `DATABASE_URL` (tem prioridade máxima)
2. Combinação de `DB_HOST` + `DB_PORT` + `DB_NAME` + `DB_USER` + `DB_PASSWORD`

Se você tiver o `.env` carregado no shell (por exemplo com `source .env` ou usando uma ferramenta como `dotenv`), pode rodar qualquer comando sem passar credenciais:

```bash
source .env
driftbrake check
driftbrake init
driftbrake snapshot
```

Ou simplesmente rodar de dentro do diretório do projeto, muitas ferramentas (como `uv run`, `direnv`, `docker-compose`) carregam o `.env` automaticamente.

<br>

## Referência de severidade padrão (resumo)

As tabelas abaixo resumem a severidade padrão para cada tipo de mudança. Para o raciocínio completo por trás de cada classificação, veja [`AUDIT-br.md`](AUDIT-br.md).

### Tabelas

| Drifts | Severidade padrão |
|---|---|
| Tabela removida | BREAKING |
| Tabela adicionada | SAFE |

### Colunas

| Drifts | Tipo de mudança | Severidade padrão |
|---|---|---|
| Coluna removida | `column_removed` | BREAKING |
| Coluna adicionada — nullable | `column_added_nullable` | SAFE |
| Coluna adicionada — NOT NULL com default | `column_added_with_default` | WARNING |
| Coluna adicionada — NOT NULL sem default | `column_added_not_null` | BREAKING |
| Restrição NOT NULL adicionada | `not_null_constraint_added` | BREAKING |
| Restrição NOT NULL removida | `not_null_constraint_removed` | WARNING |
| Default alterado | `default_changed` | WARNING |
| Primary key alterada | `primary_key_changed` | BREAKING |
| Unique constraint alterada | `unique_changed` | WARNING |
| Foreign key adicionada | `foreign_key_added` | WARNING |
| Foreign key alterada | `foreign_key_changed` | BREAKING |
| Posição ordinal alterada | `ordinal_position_changed` | WARNING |
| Possível rename detectado | `possible_rename` | WARNING |

### Índices

| Drifts | Tipo de mudança | Severidade padrão |
|---|---|---|
| Índice adicionado | `index_added` | SAFE |
| Índice removido | `index_removed` | WARNING |
| Índice modificado (colunas, tipo, unicidade, predicado) | `index_modified` | BREAKING |

### Tipos PostgreSQL (trecho da matriz de compatibilidade)

| Conversão | Severidade |
|---|---|
| `varchar(50)` → `varchar(100)` | SAFE |
| `varchar(100)` → `varchar(50)` | BREAKING |
| `text` → `varchar(n)` | BREAKING |
| `varchar(n)` → `text` | SAFE |
| `integer` → `bigint` | WARNING |
| `bigint` → `integer` | BREAKING |
| `smallint` → `integer` | SAFE |
| `numeric(10,2)` → `numeric(12,2)` | SAFE |
| `numeric(12,2)` → `numeric(10,2)` | BREAKING |
| `numeric` → `text` | BREAKING |
| `date` → `timestamp` | WARNING |
| `timestamp` → `date` | BREAKING |

Veja [`AUDIT-br.md`](AUDIT-br.md) para a matriz completa e o raciocínio por trás de cada entrada.

---
<br>

## Stack

- **SQLAlchemy** — reflection/inspection do PostgreSQL
- **Typer** — CLI
- **Rich** — output no terminal
- **Jinja2** — templates HTML
- **python-dotenv** — variáveis de ambiente
- **PyYAML** — configuração e arquivos de política
- **pytest** — testes

## Licença

**MIT license**

## Autor

**Yuri Pontes** — Ex-Cabo do Exército Brasileiro em transição para engenharia de dados.

[LinkedIn](https://www.linkedin.com/in/yuri-pontes-4ba24a345/) · [GitHub](https://github.com/yurivski)
