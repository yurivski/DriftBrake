<div align="center">

# DriftBrake — Auditoria de Classificação

</div>

Este documento é a **referência independente para cada decisão de classificação** que o DriftBrake toma. Se você está tentando entender por que a ferramenta marcou uma alteração como BREAKING quando esperava WARNING, ou precisa defender uma classificação em uma revisão de código, aqui é onde você deve procurar.

> **Público-alvo:** desenvolvedores que integram o DriftBrake em pipelines críticos, revisores auditando migrações, e qualquer pessoa que esteja criando políticas de severidade personalizadas.  
> **Documento complementar:** para documentação de uso (CLI, biblioteca, configuração), consulte [`DOCUMENTATION.md`](DOCUMENTATION.md).

<br>

## Conteúdo

- [Classificação](#classificação)
- [Tabela de referência completa de tipos de alteração](#tabela-de-referência-completa-de-tipos-de-alteração)
- [Alterações em nível de tabela](#alterações-em-nível-de-tabela)
- [Alterações em nível de coluna](#alterações-em-nível-de-coluna)
- [Alterações em nível de índice](#alterações-em-nível-de-índice)
- [Matriz de compatibilidade de tipos](#matriz-de-compatibilidade-de-tipos)
- [A heurística `possible_rename`](#a-heurística-possible_rename)
- [Como as substituições interagem com a classificação](#como-as-substituições-interagem-com-a-classificação)
- [Lógica de decisão: bloquear, perguntar, liberar](#lógica-de-decisão-bloquear-perguntar-liberar)
- [Formato de saída do reporter](#formato-de-saída-do-reporter)
- [Cenários mistos](#cenários-mistos)
- [Casos de borda](#casos-de-borda)
- [Uso programático para auditores](#uso-programático-para-auditores)

<br>

## Classificação

O DriftBrake classifica cada alteração detectada em uma das três severidades. As regras de decisão seguem três princípios de forma consistente.

**1. O contrato é a fonte da verdade.** Quando o banco de dados ativo difere do contrato, o DriftBrake reporta o banco de dados como divergente do acordo, não o contrato como desatualizado. O vocabulário do comparador reflete isso: uma coluna "removida" significa que o banco de dados perdeu uma coluna que o contrato esperava; uma coluna "adicionada" significa que o banco de dados possui uma coluna com a qual o contrato não concordou.

**2. A severidade é sobre o impacto nos consumidores, não sobre o esforço para corrigir.** Uma alteração é BREAKING quando consumidores downstream que leem o banco de dados de acordo com o contrato receberiam dados errados ou travariam. É WARNING quando os consumidores continuam funcionando, mas o comportamento mudou de uma forma que merece revisão humana. É SAFE quando os consumidores existentes não são afetados.

**3. As classificações padrão são conservadoras.** Em caso de dúvida entre duas severidades, o DriftBrake escolhe a mais restritiva. Exemplos práticos: uma restrição `NOT NULL` removida é WARNING (não SAFE) porque um novo código pode ter começado a depender de NULL não aparecer; uma chave estrangeira adicionada é WARNING (não SAFE) porque restrições referenciais podem rejeitar inserções que funcionavam antes.

<br>

## Tabela de referência completa de tipos de alteração

A tabela abaixo lista todos os valores de `ChangeType` que o DriftBrake pode emitir, sua severidade padrão, a chave exata usada para substituições de política (snake_case, correspondendo a `change_type.value`), e uma breve justificativa.

| `change_type` | Severidade padrão | Chave de substituição (YAML) | Justificativa |
|---|---|---|---|
| `table_added` | **SAFE** | `table_added` | Novas tabelas são invisíveis para os consumidores existentes. |
| `table_removed` | **BREAKING** | `table_removed` | Todos os consumidores que consultam esta tabela travam imediatamente. |
| `column_added_nullable` | **SAFE** | `column_added_nullable` | Adições anuláveis são invisíveis para os consumidores existentes; INSERTs e SELECTs existentes continuam funcionando. |
| `column_added_with_default` | **WARNING** | `column_added_with_default` | Coluna NOT NULL com padrão: inserções ainda funcionam, mas a nova restrição pode surpreender o código da aplicação. |
| `column_added_not_null` | **BREAKING** | `column_added_not_null` | Coluna NOT NULL sem padrão: INSERTs existentes que omitem esta coluna falham com `NotNullViolation`. |
| `column_removed` | **BREAKING** | `column_removed` | Todo SELECT, WHERE e caminho de código que referencia esta coluna quebra. |
| `type_changed` | **ver matriz** | `type_changed` | A severidade depende de ampliação, estreitamento ou mudança semântica; consulte a matriz de compatibilidade de tipos. |
| `not_null_constraint_added` | **BREAKING** | `not_null_constraint_added` | Linhas existentes com NULL falham na validação. Inserções existentes que omitem esta coluna agora falham. |
| `not_null_constraint_removed` | **WARNING** | `not_null_constraint_removed` | A coluna agora aceita NULL; código que assumia não-nulo pode propagar NULLs silenciosamente. |
| `default_changed` | **WARNING** | `default_changed` | Mudança comportamental silenciosa: inserções que omitem esta coluna agora recebem um valor diferente. |
| `primary_key_changed` | **BREAKING** | `primary_key_changed` | A semântica de identidade muda; referências FK podem quebrar; joins em colunas PK podem produzir resultados incorretos. |
| `unique_changed` | **WARNING** | `unique_changed` | Novas inserções podem falhar (restrição adicionada); a dependência existente de unicidade é perdida silenciosamente (restrição removida). |
| `foreign_key_added` | **WARNING** | `foreign_key_added` | Novas restrições referenciais podem rejeitar inserções que anteriormente tiveram êxito. |
| `foreign_key_changed` | **BREAKING** | `foreign_key_changed` | O alvo referenciado mudou; joins existentes podem quebrar; linhas existentes podem violar a integridade referencial. |
| `ordinal_position_changed` | **WARNING** | `ordinal_position_changed` | A ordem do `SELECT *` mudou; consumidores baseados em posição quebram silenciosamente. |
| `possible_rename` | **WARNING** | `possible_rename` | Apenas suspeita heurística; confirmação humana necessária antes de aprovar. |
| `index_added` | **SAFE** | `index_added` | Novos índices são transparentes para os consumidores existentes; as consultas continuam funcionando. |
| `index_removed` | **WARNING** | `index_removed` | Remover um índice pode degradar silenciosamente o desempenho das consultas; as consultas continuam retornando resultados corretos, mas podem ser mais lentas. |
| `index_modified` | **BREAKING** | `index_modified` | Mudanças na definição do índice (colunas, tipo, unicidade, predicado) podem alterar silenciosamente os planos de consulta. |

<br>

## Alterações em nível de tabela

### `table_added` — SAFE

**Quando ocorre:** O banco de dados ativo contém uma tabela que não está presente no contrato.

**Por que SAFE:** Os consumidores existentes ignoram tabelas que não conhecem. Novas tabelas são aditivas por definição; nenhum contrato mantido pelos consumidores atuais é violado. Consultas, inserções e código de aplicação que funcionavam antes da migração continuam funcionando sem alterações.

**Como ajustar:**

```yaml
overrides:
  table_added: WARNING  # Exigir aprovação humana para qualquer expansão de esquema
```

**Casos de borda:** Se uma tabela for adicionada sem migrar o contrato (`init`), execuções subsequentes continuarão reportando-a como drift SAFE. Atualize o contrato quando a adição for intencional.

---

### `table_removed` — BREAKING

**Quando ocorre:** O contrato referencia uma tabela que não existe mais no banco de dados ativo.

**Por que BREAKING:** Todo consumidor que consulta esta tabela trava imediatamente com `UndefinedTable`. Nenhuma recuperação é possível sem restaurar a tabela ou reescrever todo o código dependente e atualizar o contrato.

**Como ajustar:** Não há rebaixamento seguro para `table_removed`. Se a tabela foi removida intencionalmente, atualize o contrato via `driftbrake init`. Se foi removida por acidente, restaure-a.

<br>

## Alterações em nível de coluna

### `column_added_nullable` — SAFE

**Quando ocorre:** Uma nova coluna anulável aparece no banco de dados ativo que não estava no contrato.

**Por que SAFE:** Instruções `INSERT` existentes que listam colunas explicitamente ignoram esta coluna e o banco de dados insere NULL. Consultas `SELECT *` existentes recebem uma coluna NULL extra que geralmente ignoram. Nenhum consumidor quebra.

**Como ajustar:**

```yaml
overrides:
  column_added_nullable: BREAKING  # Auditoria estrita: toda expansão de esquema requer aprovação
```

Esta é uma das substituições mais comuns em ambientes de alta conformidade. Esta chave visa APENAS adições anuláveis e não afeta `column_added_with_default` ou `column_added_not_null`.

---

### `column_added_with_default` — WARNING

**Quando ocorre:** Uma nova coluna NOT NULL com um valor padrão aparece no banco de dados ativo.

**Por que WARNING:** Instruções `INSERT` existentes que não incluem esta coluna ainda têm êxito porque o banco de dados preenche o padrão. A severidade é WARNING (não SAFE) porque o comportamento padrão pode surpreender o código da aplicação que assumia que inserções falhariam quando este campo estivesse ausente, e a nova restrição é uma mudança comportamental que vale revisar.

**Como ajustar:**

```yaml
overrides:
  column_added_with_default: BREAKING  # Tratar qualquer adição NOT NULL como bloqueante
  column_added_with_default: SAFE      # Somente se o padrão cobrir todos os casos e os consumidores já estiverem cientes
```

---

### `column_added_not_null` — BREAKING

**Quando ocorre:** Uma nova coluna NOT NULL sem um valor padrão aparece no banco de dados ativo.

**Por que BREAKING:** Instruções `INSERT` existentes que não incluem esta coluna falham com `NotNullViolation`. Todo escritor desta tabela deve ser atualizado antes que a migração possa ser aplicada com segurança. Não há recuperação automática.

**Como ajustar:**

```yaml
overrides:
  column_added_not_null: WARNING  # Somente se todos os escritores já foram atualizados para fornecer este campo
```

---

### `column_removed` — BREAKING

**Quando ocorre:** O contrato referencia uma coluna que não existe mais no banco de dados ativo.

**Por que BREAKING:** Todo `SELECT column_name`, todo `WHERE column_name = ...`, todo caminho de código da aplicação que lê ou grava este campo quebra. Não há recuperação automática.

**Como ajustar:** Sem rebaixamento seguro. Se a remoção foi intencional, atualize o contrato. Se foi um `possible_rename`, consulte essa seção.

---

### `type_changed` — ver matriz

**Quando ocorre:** O tipo de dado de uma coluna no banco de dados ativo difere do tipo no contrato.

**Por que varia:** Mudanças de tipo vão desde ampliação segura (mais valores cabem) até estreitamento com perda de dados (valores existentes podem ser perdidos ou interpretados incorretamente). Consulte a [matriz de compatibilidade de tipos](#matriz-de-compatibilidade-de-tipos) para pares específicos.

**Como ajustar:**

```yaml
overrides:
  type_changed: WARNING  # Rebaixar todas as mudanças de tipo — somente se você verificou que cada conversão é segura
```

Esta é uma substituição genérica porque `type_changed` cobre todos os pares de tipos. Prefira revisar casos específicos em vez de rebaixar de forma geral.

---

### `not_null_constraint_added` — BREAKING

**Quando ocorre:** Uma coluna que era anulável no contrato agora é NOT NULL no banco de dados ativo.

**Por que BREAKING:** Linhas existentes com NULL falham na validação no nível do banco de dados. Inserções que anteriormente tiveram êxito sem fornecer este campo agora falham. Mesmo que a migração preencha NULLs existentes, todos os escritores devem ser atualizados.

**Como ajustar:**

```yaml
overrides:
  not_null_constraint_added: WARNING  # Somente se os dados existentes foram preenchidos e todos os escritores atualizados
```

---

### `not_null_constraint_removed` — WARNING

**Quando ocorre:** Uma coluna que era NOT NULL no contrato agora é anulável no banco de dados ativo.

**Por que WARNING:** O código existente continua lendo a coluna sem erro. Mas o código agora assume implicitamente que o campo sempre é não-nulo, se novos caminhos de código começarem a inserir NULLs, uma lógica anteriormente segura falha silenciosamente (NULL se propagando em aritmética, comparações, strings formatadas).

**Como ajustar:**

```yaml
overrides:
  not_null_constraint_removed: SAFE  # Somente se os consumidores foram auditados para tratamento de nulos
```

---

### `default_changed` — WARNING

**Quando ocorre:** O valor padrão de uma coluna foi adicionado, removido ou alterado no banco de dados ativo em relação ao contrato. Todos os três subcasos emitem `default_changed` com severidade WARNING.

**Por que WARNING:** O esquema não quebra estruturalmente; consultas e inserções continuam compilando e executando. Mas o comportamento muda: inserções que omitem esta coluna agora recebem um valor diferente (ou NULL, ou falham se NOT NULL sem padrão). Esta é uma mudança comportamental silenciosa que pode produzir dados errados na lógica de negócios sem que nenhum erro apareça.

**Como ajustar:**

```yaml
overrides:
  default_changed: BREAKING  # Tratar mudanças comportamentais silenciosas como bloqueantes
```

---

### `primary_key_changed` — BREAKING

**Quando ocorre:** As coluna(s) de chave primária de uma tabela mudaram em relação ao contrato.

**Por que BREAKING:** Chaves primárias são contratos de identidade. Chaves estrangeiras em outras tabelas que referenciam esta PK podem quebrar. Código que assume uma coluna PK específica (para cache, cursores de paginação, deduplicação) pode produzir joins errados ou resultados incorretos. A alteração é sempre BREAKING porque não há troca segura de PK para um sistema ativo com dependências.

---

### `unique_changed` — WARNING

**Quando ocorre:** Uma restrição de unicidade foi adicionada ou removida de uma coluna em relação ao contrato.

**Por que WARNING (restrição adicionada):** Os dados existentes passaram na validação (a restrição foi criada com êxito). Mas novas inserções e atualizações que anteriormente tiveram êxito podem agora falhar com erros de chave duplicada.

**Por que WARNING (restrição removida):** O código pode ter dependido da unicidade para estratégias de cache, lógica de deduplicação ou correção garantida de join. A remoção é silenciosa no nível do esquema, mas ruidosa no comportamento da aplicação.

---

### `foreign_key_added` — WARNING

**Quando ocorre:** Uma nova restrição de chave estrangeira foi adicionada no banco de dados ativo que não estava no contrato.

**Por que WARNING:** Novas inserções e atualizações agora devem satisfazer a integridade referencial. O código da aplicação que anteriormente escrevia referências órfãs (linhas sem pai correspondente) agora falha no nível do banco de dados. A alteração não quebra leituras existentes, mas quebra escritas existentes que dependiam da ausência de restrição.


---

### `foreign_key_changed` — BREAKING

**Quando ocorre:** A tabela ou coluna referenciada de uma restrição de chave estrangeira existente mudou em relação ao contrato.

**Por que BREAKING:** A FK agora aponta para um alvo diferente. Joins existentes podem produzir resultados errados. Linhas existentes podem agora violar a integridade referencial se a nova coluna referenciada não contiver valores correspondentes.

---

### `foreign_key_changed` também cobre FK removida — BREAKING (não WARNING)

**Por que BREAKING (FK removida):** Remover uma chave estrangeira remove uma garantia de integridade referencial da qual os consumidores podem ter dependido. O comportamento de exclusão em cascata, o comportamento de ON UPDATE e a semântica de join mudam silenciosamente. O código trata isso como BREAKING porque a suposição incorporada no contrato é violada.

---

### `ordinal_position_changed` — WARNING

**Quando ocorre:** A posição (ordinal) de uma coluna dentro da tabela mudou em relação ao contrato.

**Por que WARNING:** Chamadores de `SELECT *` recebem colunas em uma ordem diferente. Código moderno que mapeia colunas por nome não é afetado. Código legado que lê conjuntos de resultados por posição (índice 0, índice 1, etc.) quebra silenciosamente. WARNING em vez de BREAKING porque o modo de falha é acesso baseado em posição, que é raro em bases de código contemporâneas, mas comum o suficiente para sinalizar.

<br>

## Alterações em nível de índice

### `index_added` — SAFE

**Quando ocorre:** Um novo índice aparece no banco de dados ativo em uma tabela já rastreada pelo contrato.

**Por que SAFE:** Índices são um detalhe de desempenho, invisíveis para os consumidores no nível de resultado da consulta. Adicionar um índice não altera quais dados são armazenados ou retornados. As consultas existentes continuam funcionando corretamente.

**Como ajustar:**

```yaml
overrides:
  index_added: WARNING  # Exigir aprovação para cada adição de índice em ambientes de alta conformidade
```

---

### `index_removed` — WARNING

**Quando ocorre:** Um índice que existia no contrato não existe mais no banco de dados ativo.

**Por que WARNING:** Remover um índice não afeta a correção das consultas, os resultados permanecem os mesmos, mas o desempenho pode degradar silenciosamente. Consultas que dependiam do índice para buscas rápidas agora podem realizar varreduras completas da tabela. O DriftBrake inclui uma sugestão na descrição da alteração: "Verifique se nenhuma consulta crítica dependia deste índice."

**Como ajustar:**

```yaml
overrides:
  index_removed: BREAKING  # Tratar toda remoção de índice como exigindo aprovação explícita
```

---

### `index_modified` — BREAKING

**Quando ocorre:** Um índice com o mesmo nome existe tanto no contrato quanto no banco de dados ativo, mas sua definição mudou — colunas diferentes, unicidade diferente, tipo de índice diferente ou predicado parcial diferente.

**Por que BREAKING:** Mudanças na definição do índice podem alterar silenciosamente os planos de consulta. Uma consulta que usava um índice de cobertura pode agora exigir um caminho de acesso diferente. Um índice único tornado não-único remove uma garantia de consistência da qual o código pode depender. Uma mudança no índice parcial (cláusula WHERE) significa que linhas diferentes são indexadas do que antes.

Observação: O DriftBrake compara colunas em ordem classificada, portanto a ordem das colunas dentro de um índice não aciona `index_modified`. Apenas o conjunto de colunas, o sinalizador de unicidade, o tipo de índice e o predicado são comparados.

**Como ajustar:**

```yaml
overrides:
  index_modified: WARNING  # Rebaixar se mudanças no plano de consulta forem aceitáveis em seu ambiente
```

<br>

## Matriz de compatibilidade de tipos

Quando o tipo de uma coluna muda, o DriftBrake consulta o módulo de compatibilidade de tipos antes de decidir a severidade. A matriz abaixo cobre as conversões mais comuns. Conversões não listadas têm como padrão **BREAKING**.

> **Canonicalização de tipos (v0.1.1):** Antes de qualquer comparação, o DriftBrake normaliza aliases do catálogo PostgreSQL para seus nomes canônicos. Isso evita eventos fantasmas de `type_changed` causados por diferenças de representação entre versões do SQLAlchemy ou configurações de driver:
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
> Duas strings de tipo que são aliases diferentes para o mesmo tipo físico sempre produzirão `SAFE`.

### Strings

| Conversão | Severidade | Justificativa |
|---|---|---|
| `varchar(50)` → `varchar(100)` | **SAFE** | Ampliação: todo valor que cabia antes ainda cabe. |
| `varchar(100)` → `varchar(50)` | **BREAKING** | Estreitamento — valores com mais de 50 caracteres são truncados ou rejeitados. |
| `varchar(n)` → `text` | **SAFE** | `text` não tem limite de comprimento; todo valor `varchar` cabe sem alteração. |
| `text` → `varchar(n)` | **BREAKING** | Qualquer valor maior que `n` agora é inválido. |


### Inteiros

| Conversão | Severidade | Justificativa |
|---|---|---|
| `smallint` → `integer` | **SAFE** | Ampliação. |
| `integer` → `bigint` | **WARNING** | Ampliação para o banco de dados, mas o código cliente que lê em um inteiro de 32 bits de largura fixa pode transbordar em valores grandes. |
| `bigint` → `integer` | **BREAKING** | Estreitamento: valores acima de 2^31-1 transbordam. |
| `integer` → `smallint` | **BREAKING** | Estreitamento: valores acima de 2^15-1 transbordam. |

**O código retorna WARNING para estes pares específicos:**

| Conversão | Severidade | Justificativa |
|---|---|---|
| `integer` → `text` | **WARNING** | Código retorna WARNING: valor numérico é representável sem perda como texto, mas semânticas aritméticas são perdidas. |
| `bigint` → `text` | **WARNING** | Código retorna WARNING. |


### Decimais

| Conversão | Severidade | Justificativa |
|---|---|---|
| `numeric(10,2)` → `numeric(12,2)` | **SAFE** | Ampliação de precisão, escala inalterada. |
| `numeric(12,2)` → `numeric(10,2)` | **BREAKING** | Estreitamento de precisão — valores acima de 10 dígitos significativos transbordam. |
| `numeric(10,4)` → `numeric(10,2)` | **BREAKING** | Escala estreitada — valores com mais de 2 casas decimais perdem precisão. |

A lógica no código é a seguinte: `if new_prec < old_prec or new_scale != old_scale: return BREAKING`. Isso significa que **qualquer modificação na escala**, seja aumentando ou diminuindo, é tratada como uma mudança de quebra. Consumidores downstream que dependem de analisar a escala da coluna a partir de metadados podem se comportar de maneira inesperada ou incorreta se a escala mudar em qualquer direção.

| Conversão | Severidade | Justificativa |
|---|---|---|
| `real` → `double precision` | **SAFE** | Ampliação. |
| `double precision` → `real` | **BREAKING** | Código retorna BREAKING: estreitamento de precisão com potencial perda de valor, não apenas perda de acurácia. |

### Datas e horas

| Conversão | Severidade | Justificativa |
|---|---|---|
| `date` → `timestamp` | **WARNING** | Semântica de data preservada (meia-noite), mas os consumidores agora podem processar um componente de tempo inesperado. |
| `timestamp` → `date` | **BREAKING** | Perda do componente de tempo; linhas com horários diferentes de meia-noite perdem informações silenciosamente. |
| `timestamp` → `timestamptz` | **WARNING** | A interpretação do fuso horário muda; os consumidores devem concordar sobre UTC vs. local. |
| `timestamptz` → `timestamp` | **WARNING** | **Código retorna WARNING.** As informações de fuso horário são tecnicamente descartadas no nível do banco de dados, mas para muitos consumidores em um ambiente de fuso horário único, esta conversão é tolerável; revisão humana é necessária em vez de bloqueio automático. |

### Genérico

| Conversão | Severidade | Justificativa |
|---|---|---|
| `numeric` → `text` | **BREAKING** | Semânticas numéricas perdidas. Aritmética, comparações e consultas de intervalo quebram. |
| `text` → `numeric` | **BREAKING** | Análise necessária; linhas com conteúdo não numérico falham. |
| `json` → `jsonb` | **SAFE** | `jsonb` é um superconjunto estrito dos casos de uso de `json`. |
| `jsonb` → `json` | **WARNING** | Perde indexabilidade; consultas que dependem de operadores jsonb quebram. |

### O que a matriz NÃO cobre

Se o DriftBrake encontrar um par de tipos não presente em `_COMPAT_RULES` (domínios personalizados, tipos de extensão como PostGIS, enums, tipos compostos), o padrão é **BREAKING** para ser conservador. Use uma substituição de política se seu contexto exigir o contrário:

```yaml
overrides:
  type_changed: WARNING  # Use somente após verificar manualmente que cada par de tipo desconhecido é seguro
```

<br>

## A heurística `possible_rename`

Quando uma coluna é removida de uma tabela e outra coluna é adicionada à mesma tabela com um tipo compatível, o DriftBrake trata isso como uma **suspeita de renomeação** em vez de duas alterações independentes.

### Como a suspeita é detectada

A heurística é acionada quando todas as três condições se aplicam:

1. Uma coluna foi removida de uma tabela.
2. Uma coluna foi adicionada à mesma tabela.
3. Os tipos são compatíveis de acordo com a matriz de tipos (a conversão seria SAFE ou WARNING — **nunca BREAKING**).

Quando isso ocorre, o DriftBrake emite uma única alteração `possible_rename` em vez de uma `column_removed` (BREAKING) + uma alteração de coluna adicionada (`column_added_nullable`, `column_added_with_default` ou `column_added_not_null`).

**Apenas um par de renomeação por coluna removida.** Quando várias colunas adicionadas correspondem a uma coluna removida, o DriftBrake seleciona a melhor correspondência e emite um único `possible_rename` para esse par. Os outros candidatos permanecem como adições independentes.

### Quando tipos incompatíveis impedem a detecção de renomeação

Se o tipo da coluna removida e o tipo da coluna adicionada são incompatíveis-BREAKING de acordo com a matriz de tipos, a heurística **não** é acionada. Em vez disso, o DriftBrake emite:

- Uma alteração `column_removed` (BREAKING) para a coluna removida.
- Uma alteração de coluna adicionada para a coluna adicionada (`column_added_nullable` SAFE, `column_added_with_default` WARNING ou `column_added_not_null` BREAKING), com base em suas propriedades.

Este é o comportamento correto porque uma mudança de tipo incompatível não é uma renomeação, é uma substituição semântica.

### Por que `possible_rename` é sempre WARNING

Um `possible_rename` nunca é classificado automaticamente como BREAKING por dois motivos:

- Se realmente foi uma renomeação, a alteração é essencialmente retrocompatível, os dados se moveram, mas não desapareceram. Bloqueá-la impediria migrações legítimas de prosseguir.
- Se realmente foi uma remoção + adição coincidentes com tipos semelhantes, a natureza de quebra está na remoção. Marcar o par como BREAKING contaria a severidade duas vezes.

WARNING captura a semântica correta: "isso parece uma renomeação, mas um humano deve confirmar antes de aprovar."

### Níveis de confiança

Cada `possible_rename` carrega um campo `confidence` que reflete a força do sinal de renomeação.

| Nível | Critérios | Significado prático |
|---|---|---|
| `high` | Nomes de coluna semelhantes **e** mesmo tipo **e** \|ordinal_diff\| ≤ 2 | Sinal forte de renomeação. Os três sinais independentes se alinham. Ainda requer confirmação manual, mas é a renomeação verdadeira mais provável. |
| `medium` | Mesmo tipo **e** \|ordinal_diff\| ≤ 2 | Os nomes diferem, mas o alinhamento de posição e tipo sugere renomeação. Pode ser uma refatoração onde a coluna foi renomeada significativamente. Revisão necessária. |
| `low` | Apenas tipo compatível | Pode ser uma renomeação, pode ser coincidência. Mais cautela necessária. Trate como remoção+adição suspeita até prova em contrário. |

### Como escalar a detecção de renomeação para BREAKING

Se seu pipeline de auditoria exige que toda remoção seja explicitamente aprovada independentemente da suspeita de renomeação:

```yaml
overrides:
  possible_rename: BREAKING
```

A alteração ainda é detectada como `possible_rename` (não dividida em remoção/adição separadas), mas bloqueará o pipeline em vez de apenas avisar.

<br>

## Como as substituições interagem com a classificação

As substituições de política se aplicam **após** a classificação padrão do DriftBrake. O pipeline é:

1. O comparador de esquema detecta cada alteração e atribui sua severidade padrão (de acordo com as tabelas acima).
2. Se um arquivo de política estiver carregado, `apply_policy()` é executado como pós-processamento.
3. Para cada alteração, a política verifica `ignore_tables`, depois `ignore_columns`, depois `overrides`.
4. As substituições **substituem a severidade** e acrescentam `[overridden by policy: SEVERITY]` à descrição original para trilha de auditoria.

### Mecânica exata do `apply_policy`

```python
def apply_policy(result, policy: Policy):
    for change in result.changes:
        # Ignore_tables: pular completamente, a alteração não é reportada
        if change.table_name in policy.ignore_tables:
            continue
        # Ignore_columns: pular (formato "table.column")
        col_key = f"{change.table_name}.{change.column_name}" if change.column_name else None
        if col_key and col_key in policy.ignore_columns:
            continue
        # Overrides: substituir severidade + acrescentar à descrição
        change_type_name = change.change_type.value  # ex: "nullable_column_added"
        if change_type_name in policy.overrides:
            new_severity = Severity(policy.overrides[change_type_name])
            change = replace(change, severity=new_severity,
                description=f"{change.description} [overridden by policy: {new_severity.value}]")
```

A chave de substituição no YAML **deve corresponder exatamente a `change_type.value`** (snake_case). O conjunto completo de chaves válidas é: `table_added`, `table_removed`, `column_added_nullable`, `column_added_with_default`, `column_added_not_null`, `column_removed`, `type_changed`, `not_null_constraint_added`, `not_null_constraint_removed`, `default_changed`, `primary_key_changed`, `unique_changed`, `foreign_key_changed`, `foreign_key_added`, `ordinal_position_changed`, `possible_rename`, `index_added`, `index_removed`, `index_modified`.

### Exemplos de substituição

```yaml
overrides:
  column_added_nullable: BREAKING   # Exigir aprovação para toda adição anulável
  column_added_with_default: BREAKING  # Tratar adições NOT NULL+padrão como bloqueantes
  ordinal_position_changed: SAFE    # Suprimir avisos de mudança posicional em seu ambiente
  default_changed: BREAKING         # Tratar mudanças comportamentais silenciosas como bloqueantes
  possible_rename: BREAKING         # Forçar aprovação explícita de toda suspeita de renomeação
  index_removed: BREAKING           # Tratar remoções de índice como bloqueantes
```

### As listas de ignorar são absolutas

`ignore_tables` e `ignore_columns` filtram as alterações completamente, o DriftBrake não as reporta de forma alguma, independentemente da severidade. Elas têm prioridade sobre as substituições.

```yaml
ignore_tables:
  - alembic_version        # Artefato de ferramentas de migração
  - flyway_schema_history  # Artefato de ferramentas de migração

ignore_columns:
  - users.updated_at       # Timestamp automático, não faz parte do contrato da API
  - orders.last_synced     # Campo operacional, não relevante para o contrato
```

Use listas de ignorar para campos que mudam frequentemente por razões operacionais e não fazem parte do contrato que você deseja aplicar.

<br>

## Lógica de decisão: bloquear, perguntar, liberar

Após todas as alterações serem classificadas (incluindo o pós-processamento de política), o DriftBrake determina a severidade mais alta presente e decide se deve bloquear, perguntar ou liberar o pipeline.

```python
# Pseudocódigo de decision.py
if sev_upper in fail_on:
    → bloquear (código de saída 2)
if sev_upper in ask_on and interactive_effective:
    → perguntar (solicitar confirmação do usuário)
else:
    → liberar (código de saída 0)
```

Configuração padrão:
- `fail_on = ["BREAKING"]` — qualquer alteração BREAKING bloqueia automaticamente.
- `ask_on = ["WARNING"]` — qualquer alteração WARNING solicita confirmação no modo interativo; no modo não-interativo (CI), libera sem perguntar.

A decisão é baseada na severidade mais alta única entre todas as alterações. Uma execução com 10 alterações SAFE e 1 alteração BREAKING bloqueia tão firmemente quanto uma execução com 1 alteração BREAKING.

<br>

## Formato de saída do reporter

O `FacadeTerminalReporter` formata a saída da seguinte maneira:

```
[OK]      DriftBrake: no schema drift detected.
[INFO]    DriftBrake: N safe schema change(s) detected.
[WARN]    DriftBrake: N warning change(s) detected.
[BLOCKED] DriftBrake: N breaking change(s) detected.
[BLOCKED] {reason}
          Pipeline blocked.
[OK]      Pipeline released.
```

Comportamentos principais:

- `[OK]` sem drift: emitido quando não há alterações de nenhum tipo.
- `[INFO]` para SAFE: emite apenas uma contagem, a menos que `verbose=True`. Quando `verbose=True`, cada alteração SAFE é listada individualmente.
- `[WARN]` para WARNING: **sempre lista cada alteração individualmente**, independentemente da configuração verbose.
- `[BLOCKED]` para BREAKING: **sempre lista cada alteração individualmente**; escrito no stderr.
- `[BLOCKED]` + `Pipeline blocked.`: emitido após a lista de alterações quando o pipeline está bloqueado; escrito no stderr.
- `[OK]` + `Pipeline released.`: emitido quando o pipeline tem permissão para prosseguir.

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

Alterações SAFE aparecem apenas como uma contagem no modo não-verbose. Alterações WARNING e BREAKING são sempre listadas com tabela, coluna e descrição.

<br>

## Cenários mistos

Quando uma única migração afeta várias tabelas ou colunas, o DriftBrake reporta cada alteração de forma independente. A decisão no nível do pipeline é baseada na **severidade mais alta presente**:

| Severidade mais alta | Resultado do pipeline |
|---|---|
| Sem alterações | Liberar |
| Apenas SAFE | Liberar |
| WARNING (não-interativo ou não em `ask_on`) | Liberar |
| WARNING (interativo + `ask_on` inclui WARNING) | Perguntar ao usuário |
| BREAKING (em `fail_on`) | Bloquear |

Todos os três níveis de severidade podem aparecer na mesma execução. O reporter mostra cada um presente, em ordem (SAFE → WARNING → BREAKING), cada um com seu próprio prefixo.

<br>

## Casos de borda

### Schemas configurados mas não presentes no banco de dados

Se `schemas=["public", "staging"]` estiver configurado mas `staging` não existir, o DriftBrake lança `SchemaNotFoundError` (código de saída 5) listando os schemas disponíveis. Isso falha de forma ruidosa em vez de reportar silenciosamente "sem drift."

### Arquivo de contrato presente mas corrompido

Se `schema.lock.json` existir mas não for JSON válido, o DriftBrake lança `SchemaContractNotFoundError` (código de saída 4) com a localização do erro de análise. Mesmo código de saída que "contrato ausente" porque em ambos os casos o contrato é inutilizável.

### Arquivo de contrato presente mas estruturalmente inválido

Se `schema.lock.json` for JSON válido mas estiver faltando campos obrigatórios (ex: `{}`), o DriftBrake lança `SchemaContractNotFoundError` listando os campos ausentes.

### Sistema de arquivos somente leitura durante `init`

Se o DriftBrake tentar escrever `schema.lock.json` em um sistema de arquivos somente leitura (sandbox CI, contêiner reforçado), ele lança `ContractWriteError` (código de saída 6) com o caminho e o erro do SO subjacente.

### Banco de dados inacessível

Se não for possível conectar-se ao banco de dados, o DriftBrake lança `SchemaConnectionError` (código de saída 3) com o erro do driver subjacente. O código de saída 3 cobre tanto "servidor não está em execução" quanto "autenticação falhou", a mensagem distingue os dois.

### `possible_rename` + tipos incompatíveis = remoção e adição separadas

Se uma coluna removida e uma coluna adicionada tiverem tipos BREAKING-incompatíveis, a heurística de renomeação não é acionada. O resultado é um `column_removed` (BREAKING) + uma alteração de coluna adicionada (`column_added_nullable` SAFE, `column_added_with_default` WARNING ou `column_added_not_null` BREAKING), dependendo das propriedades da coluna adicionada. Isso reflete uma substituição semântica verdadeira, não uma renomeação.

### Formato `driftbrake.yml` removido (v0.2.0)

Carregar arquivos `driftbrake.yml` que usam as chaves aninhadas `tables.ignore` / `columns.ignore` (formato v0.0.2) agora lança `ConfigurationError` imediatamente. Este formato foi descontinuado com um `DeprecationWarning` na v0.1.1 e removido na v0.2.0. Migre para `driftbrake.policy.yml` com as chaves planas `ignore_tables` / `ignore_columns`.

### `index_modified` vs `index_removed` + `index_added` separados

Quando um índice existe tanto antes quanto depois mas sua definição mudou (colunas diferentes, unicidade diferente, tipo diferente ou predicado diferente), o DriftBrake emite um único `index_modified` (BREAKING) em vez de `index_removed` + `index_added`. O nome é a chave de correspondência. Se o mesmo nome não existir em ambos os lados, é detectado como remoção + adição independentes.

Observação: O DriftBrake compara colunas de índice em ordem classificada, a ordem das colunas dentro de um índice não é rastreada como uma alteração. Apenas o conjunto de colunas importa.

<br>

## Uso programático para auditores

### Por que as classificações importam em pipelines

Quando o DriftBrake está incorporado em um pipeline CI/CD, a classificação determina se uma implantação é bloqueada automaticamente, requer aprovação humana ou prossegue. Acertar as classificações significa:

- Alterações BREAKING interrompem a implantação automaticamente, prevenindo interrupções causadas por drift de esquema.
- Alterações WARNING aparecem para revisão sem parar o pipeline em ambientes CI não-interativos.
- Alterações SAFE são registradas, mas nunca bloqueiam.

Políticas mal configuradas (ex: `nullable_column_added: SAFE` quando já é o padrão SAFE, ou `foreign_key_changed: WARNING` quando deveria ser BREAKING) podem silenciosamente aprovar alterações que quebram consumidores downstream.

### Substituindo severidade via YAML

```yaml
# driftbrake.policy.yml
overrides:
  column_added_nullable: BREAKING   # Mais estrito: exigir aprovação para todas as adições
  column_added_not_null: WARNING    # Mais flexível: permitir NOT NULL sem padrão após atualização do escritor
  ordinal_position_changed: SAFE    # Suprimir avisos de mudança posicional em seu ambiente
  possible_rename: BREAKING         # Escalar: tratar toda suspeita de renomeação como bloqueante
  index_removed: BREAKING           # Escalar: tratar remoções de índice como bloqueantes
ignore_tables:
  - alembic_version
ignore_columns:
  - users.internal_notes
```

A chave de substituição deve ser o `change_type.value` exato em snake_case. A sensibilidade a maiúsculas e minúsculas importa, `COLUMN_ADDED_NULLABLE` não corresponderá.

### Substituindo severidade via API Python

```python
from driftbrake.models import Policy
from driftbrake.policy import apply_policy

policy = Policy(
    overrides={"column_added_nullable": "BREAKING"},
    ignore_tables=["alembic_version"],
    ignore_columns=["users.updated_at"],
)
result = apply_policy(drift_result, policy)
```

### CLI e biblioteca

Para uso de CLI, flags de configuração e receitas de integração, consulte [`DOCUMENTATION.md`](DOCUMENTATION.md). Este documento (AUDIT.md) cobre apenas a lógica de classificação e a mecânica de políticas.

<br>

---

## Nota de manutenção

Este documento é a trilha de auditoria de decisões de classificação. **Quando uma severidade padrão muda entre versões, este documento é atualizado juntamente com o CHANGELOG.**

Para o código-fonte que implementa estas regras, consulte:

- `src/driftbrake/classifiers/impact_classifier.py` — aplica os padrões de severidade.
- `src/driftbrake/classifiers/type_compatibility.py` — lógica da matriz de tipos.
- `src/driftbrake/comparators/schema_comparator.py` — detecção de alterações e heurística `possible_rename`.
- `src/driftbrake/policy.py` — pós-processamento `apply_policy()`.
- `src/driftbrake/decision.py` — lógica de decisão bloquear / perguntar / liberar.
- `src/driftbrake/reporters/facade_terminal.py` — formato de saída do reporter de terminal.
