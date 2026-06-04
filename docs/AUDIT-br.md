<div align="center">

# DriftBrake — Auditoria das Classificações

</div>

Esse documento é a **referência independente pra toda decisão de classificação** que o DriftBrake toma. Se você tá tentando entender por que a ferramenta marcou uma mudança como BREAKING quando você esperava WARNING, ou precisa defender uma classificação numa revisão de código, é aqui que olha.

> **Público:** devs integrando o DriftBrake em pipelines críticos, revisores auditando migrations, e quem tá construindo policies customizadas de severidade.  
> **Companheiro:** pra docs de uso (CLI, biblioteca, configuração), veja [`DOCUMENTATION-BR.md`](DOCUMENTATION-BR.md).

<br>

## Sumário

- [Classificação](#classificação)
- [Tabela de referência completa de change_type](#tabela-de-referência-completa-de-change_type)
- [Mudanças no nível de tabela](#mudanças-no-nível-de-tabela)
- [Mudanças no nível de coluna](#mudanças-no-nível-de-coluna)
- [Matriz de compatibilidade de tipos](#matriz-de-compatibilidade-de-tipos)
- [O heurístico `possible_rename`](#o-heurístico-possible_rename)
- [Como overrides interagem com a classificação](#como-overrides-interagem-com-a-classificação)
- [Lógica de decisão: bloquear, perguntar, liberar](#lógica-de-decisão-bloquear-perguntar-liberar)
- [Formato de saída do reporter](#formato-de-saída-do-reporter)
- [Cenários mistos](#cenários-mistos)
- [Casos extremos](#casos-extremos)
- [Uso programático para auditores](#uso-programático-para-auditores)

<br>

## Classificação

O DriftBrake classifica cada mudança detectada em uma de três severidades. As regras seguem três princípios de forma consistente.

**1. O contrato é a fonte da verdade.** Quando o banco em produção difere do contrato, o DriftBrake reporta o banco como "desviou do acordo", não o contrato como "desatualizado". O vocabulário do comparator reflete isso: uma coluna "removida" significa que o banco perdeu uma coluna que o contrato esperava; uma coluna "adicionada" significa que o banco tem uma coluna que o contrato não acordou.

**2. Severidade é sobre impacto no consumidor, não esforço pra arrumar.** Uma mudança é BREAKING quando consumidores downstream que leem o banco segundo o contrato vão receber dado errado ou crashar. É WARNING quando consumidores continuam funcionando mas o comportamento mudou de um jeito que merece revisão humana. É SAFE quando consumidores existentes não são afetados.

**3. Classificações default são conservadoras.** Quando tá em dúvida entre duas severidades, o DriftBrake escolhe a mais estrita. Exemplos práticos: uma constraint `NOT NULL` removida é WARNING (não SAFE) porque código novo pode ter começado a depender de NULL não aparecer; uma foreign key adicionada é WARNING (não SAFE) porque restrições referenciais podem rejeitar inserts que funcionavam antes.

<br>

## Tabela de referência completa de change_type

A tabela abaixo lista todo valor de `ChangeType` que o DriftBrake pode emitir, sua severidade default, a chave exata usada para overrides de policy (snake_case, correspondendo a `change_type.value`), e um breve raciocínio.

| `change_type` | Severidade default | Chave de override (YAML) | Raciocínio |
|---|---|---|---|
| `table_added` | **SAFE** | `table_added` | Tabelas novas são invisíveis para consumidores existentes. |
| `table_removed` | **BREAKING** | `table_removed` | Todo consumidor que faz query nessa tabela quebra imediatamente. |
| `column_added` | **BREAKING** | `column_added` | Uma coluna NOT NULL sem default quebra INSERTs existentes. Uma coluna NOT NULL com default é WARNING — mas ambos compartilham o mesmo `change_type` (veja nota abaixo). |
| `nullable_column_added` | **SAFE** | `nullable_column_added` | Adições nullable são invisíveis para consumidores existentes; INSERTs e SELECTs existentes continuam funcionando. |
| `column_removed` | **BREAKING** | `column_removed` | Todo SELECT, WHERE e caminho de código que referencia essa coluna quebra. |
| `type_changed` | **veja matriz** | `type_changed` | Severidade depende de ampliação, redução ou mudança semântica; consulte a matriz de compatibilidade de tipos. |
| `nullable_changed` | **BREAKING ou WARNING** | `nullable_changed` | Adicionar NOT NULL = BREAKING; remover NOT NULL = WARNING. Ambas as direções compartilham um `change_type` (veja nota abaixo). |
| `default_changed` | **WARNING** | `default_changed` | Mudança comportamental silenciosa: inserts que omitem essa coluna agora recebem um valor diferente. |
| `primary_key_changed` | **BREAKING** | `primary_key_changed` | Semântica de identidade desloca; referências FK podem quebrar; joins nas colunas PK podem produzir resultados errados. |
| `unique_changed` | **WARNING** | `unique_changed` | Inserts novos podem falhar (constraint adicionada); dependência existente em unicidade é silenciosamente perdida (constraint removida). |
| `foreign_key_added` | **WARNING** | `foreign_key_added` | Restrições referenciais novas podem rejeitar inserts que antes passavam. |
| `foreign_key_changed` | **BREAKING** | `foreign_key_changed` | Alvo referenciado deslocou; joins existentes podem quebrar; linhas existentes podem violar integridade referencial. |
| `ordinal_position_changed` | **WARNING** | `ordinal_position_changed` | Ordem de `SELECT *` mudou; consumidores baseados em posição quebram silenciosamente. |
| `possible_rename` | **WARNING** | `possible_rename` | Apenas suspeita heurística; confirmação humana necessária antes de aprovar. |

> **Nota sobre `column_added`:** O change type `column_added` representa uma coluna NOT NULL (com ou sem default). Quando um default está presente, o DriftBrake emite `column_added` com severidade WARNING; quando não há default, emite `column_added` com severidade BREAKING. Ambos compartilham o mesmo valor de `change_type` e não podem ser alvejados independentemente via override de policy — um override de `column_added: SAFE` se aplicaria aos dois. Use com cuidado.

> **Nota sobre `nullable_column_added`:** Este é um `change_type` **distinto** de `column_added`. `nullable_column_added` significa que a nova coluna permite NULL. `column_added` significa que a nova coluna é NOT NULL.

> **Nota sobre `nullable_changed`:** A direção importa para a severidade mas o valor de `change_type` é o mesmo para ambas as direções. Um override de `nullable_changed: SAFE` incorretamente rebaixaria "NOT NULL adicionado" junto com "NOT NULL removido". Prefira usar `ignore_columns` ou revisar esse change type manualmente.

<br>

## Mudanças no nível de tabela

### `table_added` — SAFE

**Quando acontece:** O banco em produção contém uma tabela que não está presente no contrato.

**Por que SAFE:** Consumidores existentes ignoram tabelas que não conhecem. Tabelas novas são aditivas por definição, nenhum contrato segurado pelos consumidores atuais é violado. Queries, inserts e código de aplicação que funcionavam antes da migration continuam funcionando sem alteração.

**Como ajustar:**

```yaml
overrides:
  table_added: WARNING  # Exige aprovação humana para toda expansão de schema
```

**Casos extremos:** Se uma tabela é adicionada sem atualizar o contrato (`init`), execuções subsequentes vão continuar reportando-a como drift SAFE. Atualize o contrato quando a adição for intencional.

---

### `table_removed` — BREAKING

**Quando acontece:** O contrato referencia uma tabela que não existe mais no banco em produção.

**Por que BREAKING:** Todo consumidor que faz query nessa tabela quebra imediatamente com `UndefinedTable`. Nenhuma recuperação é possível sem restaurar a tabela ou reescrever todo o código dependente e atualizar o contrato.

**Como ajustar:** Não há rebaixamento seguro para `table_removed`. Se a tabela foi removida intencionalmente, atualize o contrato via `driftbrake init`. Se foi removida por acidente, restaure-a.

<br>

## Mudanças no nível de coluna

### Adições

#### `nullable_column_added` — SAFE

**Quando acontece:** Uma nova coluna nullable aparece no banco em produção que não estava no contrato.

**Por que SAFE:** Statements `INSERT` existentes que listam colunas explicitamente pulam essa coluna e o banco insere NULL. Queries `SELECT *` existentes recebem uma coluna NULL extra que tipicamente ignoram. Nenhum consumidor quebra.

**Como ajustar:**

```yaml
overrides:
  nullable_column_added: BREAKING  # Auditoria estrita: toda expansão de schema exige aprovação
```

---

#### `column_added` — BREAKING (sem default) ou WARNING (com default)

**Quando acontece:** Uma nova coluna NOT NULL aparece no banco em produção.

- **Sem default:** Statements `INSERT` existentes que não incluem essa coluna falham com `NotNullViolation`. Todo escritor dessa tabela precisa ser atualizado antes que a migration possa ser aplicada com segurança.
- **Com default:** Inserts continuam funcionando porque o banco preenche o default. A severidade é WARNING porque o comportamento do default pode surpreender código de aplicação que assumia que inserts falhariam quando esse campo estivesse faltando.

**Por que BREAKING / WARNING:** Ambos são mais estritos que SAFE porque a constraint NOT NULL impõe uma nova obrigação sobre os escritores. A diferença é se o banco pode satisfazer essa obrigação automaticamente (default presente) ou não.

**Como ajustar:** Um override de `column_added` aplica-se a ambos os sub-casos porque compartilham o mesmo valor de `change_type`.

```yaml
overrides:
  column_added: WARNING  # Rebaixa o caso "sem default" — apenas se todos os escritores já foram atualizados
```

---

### Remoções

#### `column_removed` — BREAKING

**Quando acontece:** O contrato referencia uma coluna que não existe mais no banco em produção.

**Por que BREAKING:** Todo `SELECT column_name`, todo `WHERE column_name = ...`, todo caminho de código de aplicação que lê ou escreve esse campo quebra. Não há recuperação automática.

**Como ajustar:** Sem rebaixamento seguro. Se a remoção foi intencional, atualize o contrato. Se foi um `possible_rename`, veja essa seção.

---

### Mudanças de tipo

#### `type_changed` — veja matriz

**Quando acontece:** O tipo de dado de uma coluna no banco em produção difere do tipo no contrato.

**Por que varia:** Mudanças de tipo vão de ampliação segura (mais valores cabem) a redução com perda (valores existentes podem ser perdidos ou mal interpretados). Veja a [matriz de compatibilidade de tipos](#matriz-de-compatibilidade-de-tipos) para pares específicos.

**Como ajustar:**

```yaml
overrides:
  type_changed: WARNING  # Rebaixa todas as mudanças de tipo, apenas se você verificou que toda conversão é segura
```

Este é um override grosseiro porque `type_changed` cobre todo par de tipos. Prefira revisar casos específicos em vez de rebaixar de forma abrangente.

---

### Nulabilidade

#### `nullable_changed` — BREAKING (NOT NULL adicionado) ou WARNING (NOT NULL removido)

**Quando acontece:**

- **NOT NULL adicionado:** Uma coluna que era nullable no contrato agora é NOT NULL no banco em produção.
- **NOT NULL removido:** Uma coluna que era NOT NULL no contrato agora é nullable no banco em produção.

**Por que BREAKING (adicionando NOT NULL):** Linhas existentes com NULL falham validação no nível do banco. Inserts que antes passavam sem fornecer esse campo agora falham. Mesmo que a migration preencha NULLs existentes com um default, todos os escritores precisam ser atualizados.

**Por que WARNING (removendo NOT NULL):** Código existente continua lendo a coluna sem erro. Mas o código agora implicitamente assume que o campo é sempre não-nulo, se novos caminhos de código começarem a inserir NULLs, lógica antes segura falha silenciosamente (NULL se propagando em aritmética, comparações, strings formatadas).

**Caso extremo:** Ambas as direções compartilham o mesmo valor de `change_type` `nullable_changed`. Um override não pode alvejá-las independentemente.

---

### Defaults

#### `default_changed` — WARNING

**Quando acontece:** O valor default de uma coluna foi adicionado, removido ou alterado no banco em produção em relação ao contrato. Todos os três sub-casos emitem `default_changed` com severidade WARNING.

**Por que WARNING:** O schema não quebra estruturalmente, queries e inserts continuam compilando e rodando. Mas o comportamento muda: inserts que omitem essa coluna agora recebem um valor diferente (ou NULL, ou falham se NOT NULL sem default). Esta é uma mudança comportamental silenciosa que pode produzir dado errado em lógica de negócio sem nenhum erro surgindo.

**Como ajustar:**

```yaml
overrides:
  default_changed: BREAKING  # Trata mudanças comportamentais silenciosas como bloqueantes
```

---

### Constraints

#### `primary_key_changed` — BREAKING

**Quando acontece:** As colunas de chave primária de uma tabela mudaram em relação ao contrato.

**Por que BREAKING:** Chaves primárias são contratos de identidade. Foreign keys em outras tabelas que referenciam essa PK podem quebrar. Código que assume uma coluna PK específica (para cache, cursores de paginação, deduplicação) pode produzir joins errados ou resultados incorretos. A mudança é sempre BREAKING porque não há troca segura de PK para um sistema em produção com dependências.

---

#### `unique_changed` — WARNING

**Quando acontece:** Uma constraint unique foi adicionada ou removida de uma coluna em relação ao contrato.

**Por que WARNING (constraint adicionada):** Dados existentes passaram por validação (a constraint foi criada com sucesso). Mas inserts e updates novos que antes passavam podem agora falhar com erros de chave duplicada.

**Por que WARNING (constraint removida):** Código pode ter dependido da unicidade para estratégias de cache, lógica de deduplicação ou correção garantida de joins. A remoção é silenciosa no nível do schema mas barulhenta no comportamento de aplicação.

---

#### `foreign_key_added` — WARNING

**Quando acontece:** Uma nova constraint de foreign key foi adicionada no banco em produção que não estava no contrato.

**Por que WARNING:** Inserts e updates novos precisam agora satisfazer integridade referencial. Código de aplicação que antes escrevia referências órfãs (linhas sem pai correspondente) agora falha no nível do banco. A mudança não quebra leituras existentes, mas quebra escritas existentes que dependiam da ausência da constraint.

---

#### `foreign_key_changed` — BREAKING

**Quando acontece:** A tabela ou coluna referenciada por uma foreign key existente mudou em relação ao contrato.

**Por que BREAKING:** A FK agora aponta para um alvo diferente. Joins existentes podem produzir resultados errados. Linhas existentes podem agora violar integridade referencial se a nova coluna referenciada não contém valores correspondentes.

---

#### `foreign_key_changed` também cobre FK removida — BREAKING (não WARNING)

**Por que BREAKING (FK removida):** Remover uma foreign key remove uma garantia de integridade referencial da qual consumidores podem ter dependido. Comportamento de cascade delete, comportamento de ON UPDATE e semântica de join, tudo muda silenciosamente. O código trata isso como BREAKING porque a suposição embutida no contrato é violada.

---

### Estrutural

#### `ordinal_position_changed` — WARNING

**Quando acontece:** A posição (ordinal) de uma coluna dentro da tabela mudou em relação ao contrato.

**Por que WARNING:** Quem chama `SELECT *` recebe colunas em ordem diferente. Código moderno que mapeia colunas por nome não é afetado. Código legacy que lê result sets por posição (índice 0, índice 1, etc.) quebra silenciosamente. WARNING em vez de BREAKING porque o modo de falha é acesso baseado em posição, que é raro em codebases contemporâneos mas comum o suficiente para sinalizar.

<br>

## Matriz de compatibilidade de tipos

Quando o tipo de uma coluna muda, o DriftBrake consulta o módulo de compatibilidade de tipos antes de decidir a severidade. A matriz abaixo cobre as conversões mais comuns. Conversões não listadas defaultam para **BREAKING**.

> **Canonicalização de tipos (v0.1.1):** Antes de qualquer comparação, o DriftBrake normaliza os aliases do catálogo do PostgreSQL para seus nomes canônicos. Isso evita eventos `type_changed` fantasmas causados por diferenças de representação entre versões do SQLAlchemy ou configurações de driver:
>
> | Alias (como o PostgreSQL pode reportar) | Canônico (usado internamente) |
> |---|---|
> | `character varying(N)` | `varchar(N)` |
> | `decimal` / `decimal(p,s)` | `numeric` / `numeric(p,s)` |
> | `int4` | `integer` |
> | `int8` | `bigint` |
> | `int2` | `smallint` |
> | `float8` | `double precision` |
> | `float4` | `real` |
> | `bool` | `boolean` |
> | `timestamp without time zone` | `timestamp` |
> | `timestamp with time zone` | `timestamptz` |
>
> Dois strings de tipo que são aliases diferentes para o mesmo tipo físico sempre produzirão `SAFE`.

### Strings

| Conversão | Severidade | Raciocínio |
|---|---|---|
| `varchar(50)` → `varchar(100)` | **SAFE** | Ampliação — todo valor que cabia antes ainda cabe. |
| `varchar(100)` → `varchar(50)` | **BREAKING** | Redução — valores com mais de 50 caracteres são truncados ou rejeitados. |
| `varchar(n)` → `text` | **SAFE** | `text` não tem limite de tamanho; todo valor `varchar` cabe sem mudança. |
| `text` → `varchar(n)` | **BREAKING** | Qualquer valor maior que `n` agora é inválido. |


### Inteiros

| Conversão | Severidade | Raciocínio |
|---|---|---|
| `smallint` → `integer` | **SAFE** | Ampliação. |
| `integer` → `bigint` | **WARNING** | Ampliação pro banco, mas código cliente lendo num tipo de largura fixa (int 32 bits) pode estourar em valores grandes. |
| `bigint` → `integer` | **BREAKING** | Redução — valores acima de 2^31-1 estouram. |
| `integer` → `smallint` | **BREAKING** | Redução — valores acima de 2^15-1 estouram. |

**O código retorna WARNING para esses pares específicos:**

| Conversão | Severidade | Raciocínio |
|---|---|---|
| `integer` → `text` | **WARNING** | O código retorna WARNING: o valor numérico é representável como texto sem perda, mas a semântica aritmética é perdida. |
| `bigint` → `text` | **WARNING** | O código retorna WARNING. |


### Decimais

| Conversão | Severidade | Raciocínio |
|---|---|---|
| `numeric(10,2)` → `numeric(12,2)` | **SAFE** | Ampliação de precisão, escala inalterada. |
| `numeric(12,2)` → `numeric(10,2)` | **BREAKING** | Redução de precisão — valores acima de 10 dígitos significativos estouram. |
| `numeric(10,4)` → `numeric(10,2)` | **BREAKING** | Escala reduzida — valores com mais de 2 casas decimais perdem precisão. |

A lógica do código é: `if new_prec < old_prec or new_scale != old_scale: return BREAKING`. Isso significa que **qualquer mudança de escala**, incluindo ampliação de escala, é BREAKING. Consumidores que parseiam a escala de metadados de coluna podem se comportar incorretamente quando a escala muda em qualquer direção.

| Conversão | Severidade | Raciocínio |
|---|---|---|
| `real` → `double precision` | **SAFE** | Ampliação. |
| `double precision` → `real` | **BREAKING** | O código retorna BREAKING: redução de precisão com potencial perda de valor, não apenas perda de acurácia. |

### Datas e horários

| Conversão | Severidade | Raciocínio |
|---|---|---|
| `date` → `timestamp` | **WARNING** | Semântica de data preservada (meia-noite), mas consumidores podem agora processar um componente de hora inesperado. |
| `timestamp` → `date` | **BREAKING** | Perda do componente de hora; linhas com horários diferentes de meia-noite perdem informação silenciosamente. |
| `timestamp` → `timestamptz` | **WARNING** | Interpretação de fuso horário desloca; consumidores precisam concordar em UTC vs. local. |
| `timestamptz` → `timestamp` | **WARNING** | **O código retorna WARNING.** A informação de fuso horário é tecnicamente descartada no nível do banco, mas para muitos consumidores em ambientes de fuso único essa conversão é tolerável, revisão humana é necessária em vez de bloqueio automático. |

### Genéricas

| Conversão | Severidade | Raciocínio |
|---|---|---|
| `numeric` → `text` | **BREAKING** | Semântica numérica perdida. Aritmética, comparações, queries de range — tudo quebra. |
| `text` → `numeric` | **BREAKING** | Parsing necessário; linhas com conteúdo não-numérico falham. |
| `json` → `jsonb` | **SAFE** | `jsonb` é superset estrito de casos de uso de `json`. |
| `jsonb` → `json` | **WARNING** | Perde indexabilidade; queries que dependiam de operadores jsonb quebram. |

### O que a matriz NÃO cobre

Se o DriftBrake encontra um par de tipos não presente em `_COMPAT_RULES` (domínios customizados, tipos de extensão como PostGIS, enums, tipos compostos), ele defaulta pra **BREAKING** para ser conservador. Use um override de policy se seu contexto exige outro comportamento:

```yaml
overrides:
  type_changed: WARNING  # Use apenas após verificar manualmente que cada par de tipos desconhecido é seguro
```

<br>

## O heurístico `possible_rename`

Quando uma coluna é removida de uma tabela e outra coluna é adicionada na mesma tabela com tipo compatível, o DriftBrake trata isso como **suspeita de rename** em vez de duas mudanças independentes.

### Como a suspeita é detectada

O heurístico dispara quando todas as três condições são verdadeiras:

1. Uma coluna foi removida de uma tabela.
2. Uma coluna foi adicionada na mesma tabela.
3. Os tipos são compatíveis segundo a matriz de tipos (a conversão seria SAFE ou WARNING — **nunca BREAKING**).

Quando isso dispara, o DriftBrake emite uma única mudança `possible_rename` em vez de uma `column_removed` (BREAKING) + uma `column_added` ou `nullable_column_added` (SAFE).

**Apenas um par de rename por coluna removida.** Quando múltiplas colunas adicionadas correspondem a uma coluna removida, o DriftBrake seleciona o melhor match e emite um único `possible_rename` para esse par. Os outros candidatos permanecem como adições independentes.

### Quando tipos incompatíveis impedem a detecção de rename

Se o tipo da coluna removida e o tipo da coluna adicionada são BREAKING-incompatíveis segundo a matriz de tipos, o heurístico **não dispara**. Em vez disso, o DriftBrake emite:

- Uma mudança `column_removed` (BREAKING) para a coluna removida.
- Uma mudança `nullable_column_added` (SAFE) ou `column_added` (WARNING/BREAKING) para a coluna adicionada, baseado nas suas propriedades.

Esse é o comportamento correto porque uma mudança de tipo incompatível não é um rename, é uma substituição semântica.

### Por que `possible_rename` é sempre WARNING

Um `possible_rename` nunca é auto-classificado como BREAKING por duas razões:

- Se era realmente um rename, a mudança é essencialmente compatível pra trás — o dado se moveu, mas não desapareceu. Marcar como BREAKING bloquearia migrations que deveriam passar.
- Se era realmente um drop+add coincidente com tipos similares, o aspecto BREAKING está no drop. Marcar o par como BREAKING contaria a severidade duas vezes.

WARNING captura a semântica certa: "isso parece um rename, mas um humano precisa confirmar antes de aprovar."

### Níveis de confiança

Cada `possible_rename` carrega um campo `confidence` que reflete quão forte é o sinal de rename.

| Nível | Critério | Significado prático |
|---|---|---|
| `high` | Nomes de coluna similares **e** mesmo tipo **e** \|diferença_ordinal\| ≤ 2 | Sinal forte de rename. Os três sinais independentes se alinham. Ainda requer confirmação manual, mas é o caso mais provável de rename real. |
| `medium` | Mesmo tipo **e** \|diferença_ordinal\| ≤ 2 | Nomes diferem mas alinhamento de posição+tipo sugere rename. Pode ser um refactor onde a coluna foi renomeada significativamente. Revisão necessária. |
| `low` | Apenas tipo-compatível | Poderia ser rename, poderia ser coincidência. Máxima cautela necessária. Trate como drop+add suspeito até ser provado o contrário. |

### Como escalar a detecção de rename para BREAKING

Se seu pipeline de auditoria exige que toda remoção seja explicitamente aprovada, independentemente de suspeita de rename:

```yaml
overrides:
  possible_rename: BREAKING
```

A mudança ainda é detectada como `possible_rename` (não dividida em drop/add separados), mas vai bloquear o pipeline em vez de avisar.

<br>

## Como overrides interagem com a classificação

Overrides de policy aplicam **depois** da classificação default do DriftBrake. O pipeline:

1. Schema comparator detecta cada mudança e atribui a severidade default (segundo as tabelas acima).
2. Se um policy file foi carregado, `apply_policy()` roda como pós-processamento.
3. Pra cada mudança, a policy verifica `ignore_tables`, depois `ignore_columns`, depois `overrides`.
4. Overrides **substituem a severidade** e anexam `[overridden by policy: SEVERIDADE]` à descrição original para trilha de auditoria.

### Mecânica exata do `apply_policy`

```python
def apply_policy(result, policy: Policy):
    for change in result.changes:
        # Ignore_tables: pula completamente — mudança não é reportada de jeito nenhum
        if change.table_name in policy.ignore_tables:
            continue
        # Ignore_columns: pula (formato "tabela.coluna")
        col_key = f"{change.table_name}.{change.column_name}" if change.column_name else None
        if col_key and col_key in policy.ignore_columns:
            continue
        # Overrides: substitui severidade + anexa à descrição
        change_type_name = change.change_type.value  # ex: "nullable_column_added"
        if change_type_name in policy.overrides:
            new_severity = Severity(policy.overrides[change_type_name])
            change = replace(change, severity=new_severity,
                description=f"{change.description} [overridden by policy: {new_severity.value}]")
```

A chave de override no YAML **deve corresponder exatamente a `change_type.value`** (snake_case). O conjunto completo de chaves válidas é: `table_added`, `table_removed`, `column_added`, `nullable_column_added`, `column_removed`, `type_changed`, `nullable_changed`, `default_changed`, `primary_key_changed`, `unique_changed`, `foreign_key_changed`, `foreign_key_added`, `ordinal_position_changed`, `possible_rename`.

### Exemplos de override

```yaml
overrides:
  nullable_column_added: BREAKING   # Exige aprovação para toda expansão de schema
  ordinal_position_changed: SAFE    # Suprime avisos de mudança posicional no seu ambiente
  default_changed: BREAKING         # Trata mudanças comportamentais silenciosas como bloqueantes
  possible_rename: BREAKING         # Força aprovação explícita de toda suspeita de rename
```

### Listas de ignore são absolutas

`ignore_tables` e `ignore_columns` filtram mudanças **completamente** — o DriftBrake não as reporta de jeito nenhum, independente da severidade. Elas têm prioridade sobre os overrides.

```yaml
ignore_tables:
  - alembic_version        # Artefato de ferramenta de migration
  - flyway_schema_history  # Artefato de ferramenta de migration

ignore_columns:
  - users.updated_at       # Timestamp automático, não faz parte do contrato de API
  - orders.last_synced     # Campo operacional, não relevante para o contrato
```

Use listas de ignore para campos que mudam frequentemente por razões operacionais e não fazem parte do contrato que você quer enforçar.

<br>

## Lógica de decisão: bloquear, perguntar, liberar

Após todas as mudanças serem classificadas (incluindo pós-processamento de policy), o DriftBrake determina a maior severidade presente e decide se vai bloquear, perguntar ou liberar o pipeline.

```python
# Pseudocódigo de decision.py
if sev_upper in fail_on:
    → bloquear (exit code 2)
if sev_upper in ask_on and interactive_effective:
    → perguntar (solicita confirmação do usuário)
else:
    → liberar (exit code 0)
```

Configuração default:
- `fail_on = ["BREAKING"]` — qualquer mudança BREAKING bloqueia automaticamente.
- `ask_on = ["WARNING"]` — qualquer mudança WARNING solicita confirmação em modo interativo; em modo não-interativo (CI), libera sem perguntar.

A decisão é baseada na única severidade mais alta entre todas as mudanças. Uma execução com 10 mudanças SAFE e 1 BREAKING bloqueia tão firmemente quanto uma execução com apenas 1 BREAKING.

<br>

## Formato de saída do reporter

O `FacadeTerminalReporter` formata a saída da seguinte forma:

```
[OK]      DriftBrake: no schema drift detected.
[INFO]    DriftBrake: N safe schema change(s) detected.
[WARN]    DriftBrake: N warning change(s) detected.
[BLOCKED] DriftBrake: N breaking change(s) detected.
[BLOCKED] {motivo}
          Pipeline blocked.
[OK]      Pipeline released.
```

Comportamentos principais:

- `[OK]` sem drift: emitido quando há zero mudanças de qualquer tipo.
- `[INFO]` para SAFE: emite apenas contagem, a não ser que `verbose=True`. Quando `verbose=True`, cada mudança SAFE é listada individualmente.
- `[WARN]` para WARNING: **sempre lista cada mudança individualmente**, independente da configuração de verbose.
- `[BLOCKED]` para BREAKING: **sempre lista cada mudança individualmente**; escrito para stderr.
- `[BLOCKED]` + `Pipeline blocked.`: emitido após a lista de mudanças quando o pipeline é bloqueado; escrito para stderr.
- `[OK]` + `Pipeline released.`: emitido quando o pipeline está autorizado a prosseguir.

### Exemplo: múltiplas severidades presentes

```
[INFO]    DriftBrake: 1 safe schema change(s) detected.
[WARN]    DriftBrake: 1 warning change(s) detected.
  - public.orders.created_at: Column 'created_at' default changed from 'now()' to 'CURRENT_TIMESTAMP'.
[BLOCKED] DriftBrake: 1 breaking change(s) detected.
  - public.users.email: Column 'email' was removed from 'users'.
[BLOCKED] BREAKING in fail_on.
          Pipeline blocked.
```

Mudanças SAFE aparecem apenas como contagem em modo não-verbose. Mudanças WARNING e BREAKING são sempre listadas com tabela, coluna e descrição.

<br>

## Cenários mistos

Quando uma única migration toca múltiplas tabelas ou colunas, o DriftBrake reporta cada mudança independentemente. A decisão no nível de pipeline é baseada na **maior severidade presente**:

| Maior severidade | Resultado do pipeline |
|---|---|
| Sem mudanças | Libera |
| Apenas SAFE | Libera |
| WARNING (não-interativo ou não está em `ask_on`) | Libera |
| WARNING (interativo + `ask_on` inclui WARNING) | Pergunta ao usuário |
| BREAKING (em `fail_on`) | Bloqueia |

Os três níveis de severidade podem aparecer na mesma execução. O reporter mostra cada um presente, em ordem (SAFE → WARNING → BREAKING), cada um com seu próprio prefixo.

<br>

## Casos extremos

### Schemas configurados mas não presentes no banco

Se `schemas=["public", "staging"]` está configurado mas `staging` não existe, o DriftBrake levanta `SchemaNotFoundError` (exit code 5) listando os schemas disponíveis. Isso falha barulhento em vez de silenciosamente reportar "sem drift".

### Arquivo de contrato presente mas corrompido

Se `schema.lock.json` existe mas não é JSON válido, o DriftBrake levanta `SchemaContractNotFoundError` (exit code 4) com a localização do erro de parse. Mesmo exit code que "contrato faltando" porque em ambos os casos o contrato é inutilizável.

### Arquivo de contrato presente mas estruturalmente inválido

Se `schema.lock.json` é JSON válido mas faltam campos obrigatórios (ex: `{}`), o DriftBrake levanta `SchemaContractNotFoundError` listando os campos faltantes.

### Filesystem read-only durante `init`

Se o DriftBrake tenta escrever `schema.lock.json` num filesystem read-only (sandbox de CI, container hardened), levanta `ContractWriteError` (exit code 6) com o caminho e o erro de OS subjacente.

### Banco inacessível

Se o banco não consegue ser conectado, o DriftBrake levanta `SchemaConnectionError` (exit code 3) com o erro subjacente do driver. Exit code 3 cobre tanto "servidor não rodando" quanto "autenticação falhou" — a mensagem distingue os dois.

### Direção ambígua de `nullable_changed`

`nullable_changed` cobre tanto "NOT NULL adicionado" (BREAKING) quanto "NOT NULL removido" (WARNING) sob o mesmo valor de `change_type`. Um override de policy não pode alvejá-los independentemente. Se você precisa tratar "NOT NULL removido" como SAFE, use `ignore_columns` para suprimir a coluna específica, não `nullable_changed: SAFE` (que também rebaixaria a direção BREAKING).

### Severidade de `column_added` depende das propriedades da coluna, não apenas do change type

Uma coluna NOT NULL adicionada sem default é BREAKING. O mesmo change type `column_added` com um default presente é WARNING. Um override de policy de `column_added: WARNING` rebaixaria o caso sem default. Use isso apenas se todo escritor da tabela afetada já foi atualizado para fornecer o campo.

### `possible_rename` + tipos incompatíveis = drop e add separados

Se uma coluna removida e uma coluna adicionada têm tipos BREAKING-incompatíveis, o heurístico de rename não dispara. O resultado é um `column_removed` (BREAKING) + um `nullable_column_added` (SAFE) ou `column_added` (WARNING/BREAKING), dependendo das propriedades da coluna adicionada. Isso reflete uma substituição semântica real, não um rename.

### Formato `driftbrake.yml` depreciado (v0.1.1)

Carregar arquivos `driftbrake.yml` que usam as chaves aninhadas `tables.ignore` / `columns.ignore` (formato v0.0.2) agora emite `DeprecationWarning` em tempo de execução. Este formato será removido na v0.2.0. Migre para `driftbrake.policy.yml` com as chaves planas `ignore_tables` / `ignore_columns`. Os dois formatos são aplicados em etapas diferentes do pipeline (Settings pré-comparação; Policy pós-comparação) e não conflitam quando ambos estão presentes — veja DOCUMENTATION-br.md § *Arquivos de política* para o contrato de precedência.

<br>

## Uso programático para auditores

### Por que classificações importam em pipelines

Quando o DriftBrake está embutido em um pipeline de CI/CD, a classificação determina se um deployment é automaticamente bloqueado, requer aprovação humana ou prossegue. Acertar as classificações significa:

- Mudanças BREAKING interrompem o deployment automaticamente, prevenindo indisponibilidades causadas por drift de schema.
- Mudanças WARNING surgem para revisão sem parar o pipeline em ambientes de CI não-interativo.
- Mudanças SAFE são registradas mas nunca bloqueiam.

Policies mal configuradas (ex: `nullable_column_added: SAFE` quando já defaulta para SAFE, ou `foreign_key_changed: WARNING` quando deveria ser BREAKING) podem silenciosamente passar mudanças que quebram consumidores downstream.

### Sobrescrevendo severidade via YAML

```yaml
# driftbrake.yaml ou seção de policy
policy:
  overrides:
    nullable_column_added: BREAKING   # Mais estrito: exige aprovação para todas as adições
    ordinal_position_changed: SAFE    # Mais solto: ignora mudanças posicionais no seu ambiente
    possible_rename: BREAKING         # Escala: trata toda suspeita de rename como bloqueante
  ignore_tables:
    - alembic_version
  ignore_columns:
    - users.internal_notes
```

A chave de override deve ser exatamente o `change_type.value` em snake_case. Case sensitivity importa — `NULLABLE_COLUMN_ADDED` não vai fazer match.

### Sobrescrevendo severidade via Python API

```python
from driftbrake.models import Policy
from driftbrake.policy import apply_policy

policy = Policy(
    overrides={"nullable_column_added": "BREAKING"},
    ignore_tables=["alembic_version"],
    ignore_columns=["users.updated_at"],
)
result = apply_policy(drift_result, policy)
```

### CLI e Biblioteca

Para uso via CLI, flags de configuração e receitas de integração, veja [`DOCUMENTATION-BR.md`](DOCUMENTATION-BR.md). Este documento (AUDIT-br.md) cobre apenas lógica de classificação e mecânica de policy.

<br>

---

## Nota de manutenção

Esse documento é a trilha de auditoria de decisões de classificação. **Quando uma severidade default muda entre versões, esse documento é atualizado junto com o CHANGELOG.**

Pro código-fonte que implementa essas regras, veja:

- `src/driftbrake/classifiers/impact_classifier.py` — aplica defaults de severidade.
- `src/driftbrake/classifiers/type_compatibility.py` — lógica da matriz de tipos.
- `src/driftbrake/comparators/schema_comparator.py` — detecção de mudanças e heurístico `possible_rename`.
- `src/driftbrake/policy.py` — pós-processamento do `apply_policy()`.
- `src/driftbrake/decision.py` — lógica de decisão bloquear / perguntar / liberar.
- `src/driftbrake/reporters/facade_terminal.py` — formato de saída do reporter terminal.
