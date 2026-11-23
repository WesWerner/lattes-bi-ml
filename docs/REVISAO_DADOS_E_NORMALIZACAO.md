# Revisão dos tipos e da normalização — Fase 1

## Escopo e evidências usadas

A revisão foi feita sobre `sql/01_stg.sql`, `sql/02_dw.sql`, o Apêndice A (dicionário de dados) e os inventários `atributos_xml.csv`, `tags_xml.csv` e `textos_xml.csv`.

Os inventários disponíveis registram caminhos XML, frequência de ocorrência e quantidade de arquivos com ocorrência. **Eles não contêm os valores de cada campo nem o comprimento máximo observado.** Portanto, não é possível afirmar, apenas com esses CSVs, que um `VARCHAR(n)` comporta todos os valores reais. Os limites abaixo seguem o Apêndice A e devem ser verificados pelo ETL com rejeição/log de valores excedentes — nunca truncamento silencioso.

## Alterações feitas

- Alinhados diversos campos da staging aos limites documentados no Apêndice A: nomes, títulos, idioma, natureza, meio de divulgação, volume, páginas, ISSN/ISBN, localização e campos editoriais.
- Mantidos `TEXT` para descrições extensas e campos livres, como `descricao_projeto`, `objetivos`, `objetivos_ingles`, `atuacao_profissional` e listas de autores ainda não decompostas.
- Mantidos anos, páginas, edição, volumes, ISBN/ISSN e códigos como texto na staging. São valores de origem e podem conter formatos não estritamente numéricos, zeros à esquerda ou inconsistências. A conversão analítica deve ocorrer em camada validada, com campo bruto preservado.
- Alterado `hash_sha256` de `CHAR(64)` para `VARCHAR(64)` com validação de formato hexadecimal, evitando preenchimento de espaços de `CHAR`.
- Ajustados alguns tipos descritivos do DW conforme o dicionário. Campos de identificação continuam como texto, pois não são medidas aritméticas.

## O que não deve ser tratado como erro

`TEXT` não é, por si só, um tipo ruim no PostgreSQL e não costuma ser menos eficiente que `VARCHAR` sem limite. A decisão de tipo deve expressar regra de negócio, validação e semântica — não apenas reduzir a contagem de colunas `TEXT`.

## Normalização relacional

### Decisão para esta fase

A staging preserva `autores` como texto bruto para não presumir uma estrutura de autores sem validar os XMLs reais e sem definir uma chave estável de autoria. Não recomendo criar agora uma tabela genérica `autoria(tipo, id_producao)` com chave estrangeira polimórfica: o banco não conseguiria garantir que `id_producao` referencia a tabela correta.

### Próxima melhoria recomendada para o DW

Criar uma dimensão `dim_autor` e uma ponte de autoria associada a cada tipo de produção, ou uma ponte única com uma chave substituta de produção unificada. A escolha depende da regra de deduplicação de autores e da granularidade definida para as fatos. Isso exige extrair os autores individualmente dos XMLs, em vez de gravar uma lista separada por vírgulas.

### Pontos de atenção no modelo atual

1. `stg.pesquisador` tem uma linha por arquivo, não necessariamente por pessoa; essa decisão é correta para rastreabilidade. A consolidação de versões deve acontecer depois.
2. `id_lattes` aparece em tabelas repetíveis junto com `arquivo_id`; para rastreabilidade, `arquivo_id` deve continuar sendo a chave de ligação entre as tabelas.
3. A coluna `autores TEXT` é adequada como valor bruto de staging, mas não é adequada como atributo analítico final para contagem de coautoria.
4. `dim_localizacao_trabalhos` representa a localização da produção, enquanto o pesquisador deve ser relacionado pela fato. A diferença em relação ao Apêndice A precisa continuar justificada no texto do TCC.
5. `qtd_producoes` e `presenca` nas fatos devem ser inteiros; antes da carga, defina se `presenca` será 0/1 e se a granularidade da fato evita contagens duplicadas.

## Validações obrigatórias antes da carga completa

- Medir o comprimento máximo real de cada campo limitado nos XMLs (ou durante uma amostra representativa) e comparar com o `VARCHAR(n)`.
- Se houver valor maior que o limite, registrar caminho do arquivo, caminho XML, coluna e comprimento; não truncar. Rever o limite ou encaminhar o registro para tratamento.
- Validar os formatos de ano e data antes de converter para `INTEGER`/`DATE` no DW.
- Validar valores de `SIM`/`NAO` e outros indicadores categóricos antes de convertê-los para `BOOLEAN`.
- Confirmar que o mapeamento dos autores permite extrair autor individual, identificador quando existir e ordem de autoria.
- Executar testes de esquema em banco de desenvolvimento vazio; `CREATE TABLE IF NOT EXISTS` não altera colunas já criadas.
