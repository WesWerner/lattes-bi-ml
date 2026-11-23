# Fase 1 — decisões de modelagem

## O que foi alterado

1. **ID Lattes ausente:** `id_lattes` guarda apenas o valor encontrado no XML e pode ser `NULL`. O ETL deverá preencher `chave_pesquisador` com o ID Lattes quando presente ou com uma chave técnica derivada do arquivo quando ausente. A chave técnica não deve ser apresentada como um ID Lattes verdadeiro.
2. **Mais de um arquivo para o mesmo ID:** a staging permite arquivos/versões diferentes para o mesmo `id_lattes`. `stg.pesquisador` representa um registro por arquivo XML, não necessariamente uma pessoa única. A consolidação de pessoas distintas será definida e validada antes de carregar as dimensões/fatos do DW.
3. **Rastreabilidade por arquivo:** cada tabela de dados extraídos tem `arquivo_id` relacionado a `stg.curriculo_origem`. As restrições de unicidade das linhas repetíveis usam `(arquivo_id, ordem_xml)`, evitando colisões entre versões do mesmo currículo.
4. **Integridade da staging:** as tabelas da staging têm chaves primárias e as linhas extraídas referenciam o arquivo de origem. As restrições e índices analíticos do DW continuam planejados para depois da validação.
5. **Localização no DW:** `dw.dim_localizacao_trabalhos` não inclui `id_lattes`, porque a localização descreve o local associado à produção e o pesquisador é representado na tabela fato. Isso difere do dicionário de dados do apêndice e deve ser justificado explicitamente no TCC; se a fidelidade literal ao apêndice for prioridade, esse campo deve ser mantido.

## Cuidados antes da carga

- O script usa `CREATE TABLE IF NOT EXISTS`; ele não atualiza tabelas que já existam. Se os scripts anteriores já tiverem sido executados, não basta executá-los novamente para aplicar esta revisão. Em um banco de desenvolvimento vazio, prefira executar a versão revisada desde o início. Não apague schemas/tabelas sem confirmar que não há dados a preservar.
- `hash_sha256` é armazenado para reconhecer arquivos com conteúdo idêntico, mas não tem restrição `UNIQUE`: arquivos duplicados continuam registrados para auditoria. O ETL deverá decidir se os arquivos repetidos serão ignorados na extração ou registrados como duplicatas e documentar essa regra.
- `chave_pesquisador` deve ser calculada de modo determinístico pelo ETL. Para um ID Lattes presente, ela pode usar o ID original; quando ausente, recomenda-se um prefixo explícito e um caminho relativo, por exemplo `ARQUIVO:<caminho_relativo>`. A coluna não tem restrição `UNIQUE`, pois versões diferentes podem representar a mesma pessoa.
- Os nomes e caminhos dos elementos XML ainda devem ser confirmados contra os XMLs reais e o inventário de caminhos antes de construir o mapeamento.
- Nenhuma carga dos 57.624 XMLs é executada por estes scripts. Eles apenas definem a estrutura.


## Regras operacionais aditivas para o ETL

1. **Junções da staging:** todas as tabelas filhas devem ser relacionadas a `stg.curriculo_origem` por `arquivo_id`. A identidade analítica inicial deve ser obtida por `curriculo_origem.chave_pesquisador`; não fazer junções por `id_lattes`, pois ele pode ser `NULL` e pode repetir-se entre arquivos/versões.
2. **Arquivos com erro de parse:** mesmo quando o XML não puder ser interpretado, o registro de origem deve receber `chave_pesquisador = 'ARQUIVO:' || caminho_relativo`, mantendo `id_lattes_original` nulo quando o ID real não puder ser lido. O status será `ERRO`, com tipo/descrição do erro e data de processamento preenchidos quando disponíveis.
3. **Ordem dos elementos:** `ordem_xml` é um contador da posição do elemento repetível dentro do conjunto/trecho XML mapeado, iniciado em 1. Não usar `SEQUENCIA-LINHA` nem `SEQUENCIA-PROJETO` como `ordem_xml`; preservar tais valores em campo próprio ou em `dados_xml` quando necessários.
4. **Indicador de linha ativa:** a origem mapeada é `@FLAG-LINHA-DE-PESQUISA-ATIVA`. Normalizar os valores conhecidos (`SIM`/`NAO`, após confirmação nos XMLs reais) para `TRUE`/`FALSE`. Valores inesperados geram aviso no log e resultam em `NULL`, sem interromper a carga inteira.
5. **Consistência das chaves:** o ETL deve gravar o mesmo `id_lattes` real e a mesma `chave_pesquisador` em `stg.curriculo_origem` e `stg.pesquisador`. Um teste automatizado deve falhar se encontrar divergência.
6. **Duplicatas antes da consolidação:** após carregar `stg.curriculo_origem`, gerar relatório de `id_lattes_original` repetidos e de `hash_sha256` idênticos. Nenhuma regra de deduplicação/consolidação será aplicada até decisão explícita do responsável pelo projeto.
7. **Carga do DW:** para colunas `GENERATED ALWAYS AS IDENTITY`, carregar dimensões e fatos por `INSERT ... SELECT`, omitindo as colunas de identidade. Não usar `COPY` para inserir IDs gerados manualmente, salvo aprovação explícita e uso de `OVERRIDING SYSTEM VALUE` quando aplicável.

## Desvios do Apêndice A

Os desvios e extensões deliberados do dicionário original são:

- **Tipos da staging revisados:** `TEXT` permanece em campos livres ou de formato variável (nomes, títulos, objetivos, descrições, caminhos, autores e paginação/volume cuja forma real ainda precisa ser validada). Campos de domínio mais previsível passaram a usar `VARCHAR` com limite conservador: `status_processamento` (15), `identificador_projeto` (100), `doi` (255), `idioma` (50), `natureza` (50, e 100 em projetos/outras produções), `meio_divulgacao` (50), `issn` (20) e `isbn` (50), conforme o Apêndice A. Os anos ficaram como `VARCHAR(10)` na staging (texto, não inteiro), para não interromper a ingestão por valores inesperados; o ETL valida e converte ao carregar o DW. Os limites de DOI/ISBN/ISSN devem ser conferidos com os XMLs reais antes da carga completa.
- `dw.dim_localizacao_trabalhos` não contém `id_lattes`; a dimensão descreve a localização, enquanto o pesquisador é relacionado nas fatos.
- Foram adicionadas tabelas/colunas para rastreabilidade e preservação da origem: `stg.curriculo_origem`, `stg.atuacao_profissional`, `arquivo_id`, `caminho_relativo`, `hash_sha256`, `chave_pesquisador`, `status_processamento`, `tipo_erro`, `data_processamento`, `ordem_xml`, `sequencia_importancia` e `dados_xml`, além das colunas extras aprovadas em linhas de pesquisa e projetos (`titulo_ingles`, `objetivos`, `objetivos_ingles`, `indicador_linha_pesquisa_ativa`, `identificador_projeto`).
- `dw.fato_pesquisador_producoes.id_tempo` substitui `id_area` do apêndice, pois o campo representa o tempo/ano.
- `dw.dim_linha_pesquisa` inclui `linha_pesquisa_normalizada`; `dw.dim_area` mantém apenas `grande_area` e `area`.
- A tabela auxiliar `stg.atuacao_profissional` preserva todas as atuações profissionais; `stg.pesquisador.atuacao_profissional` recebe a atuação de menor `sequencia_importancia`.

## Ajustes da Fase 4 (auditoria em 500 XMLs reais)

- **Páginas:** `pagina_inicial` e `pagina_final` de `artigos`, `capitulos_livros`, `textos_jornais` e `trabalhos_eventos` passaram de `VARCHAR(10)` para `VARCHAR(50)` (`sql/05_alter_paginas.sql`). Desvio do Apêndice A: a amostra real trouxe valores de até 23 caracteres e a regra é nunca truncar.
- **Codificação:** os XMLs declaram `ISO-8859-1`, mas os bytes são UTF-8 (199 de 200 arquivos verificados). O extrator deve forçar `encoding="utf-8"` no parser e reparar por string a dupla codificação residual (`repair()` em `scripts/fase4_audit.py`), alterando o texto só quando a conversão de ida e volta latin-1→utf-8 for válida.
- **Nomes de arquivo:** `caminho_relativo` e `chave_pesquisador` (`ARQUIVO:<caminho_relativo>`) preservam o nome exato do arquivo no disco, mesmo com mojibake, para reabrir o arquivo e manter a rastreabilidade. Nenhuma normalização é aplicada nessas chaves; se for preciso um nome legível, será uma coluna adicional.
- **`stg.outras_producoes`:** a origem correta é `PRODUCAO-BIBLIOGRAFICA/DEMAIS-TIPOS-DE-PRODUCAO-BIBLIOGRAFICA/OUTRA-PRODUCAO-BIBLIOGRAFICA` (10.028 ocorrências em 3.307 arquivos). O ramo anterior (`OUTRA-PRODUCAO/DEMAIS-TRABALHOS`) não tinha editora, cidade da editora, ISSN/ISBN nem número de páginas.
- **DOI vazio:** em `textos_jornais`, `apresentacoes_trabalho` e `outras_producoes` o DOI vem vazio em praticamente todos os registros; a deduplicação nessas tabelas usará título + ano.


## Ajustes da Fase 5 (carga completa em dw_lattes_dev)
- `stg.outras_producoes.natureza`: VARCHAR(100) -> VARCHAR(200) (volta ao Apêndice A; maior valor visto: 109).
- `stg.artigos.volume`: VARCHAR(20) -> VARCHAR(50) (desvio do Apêndice A; maior valor visto: 22).
- Aplicado via `sql/06_alter_limites.sql` (aditivo, idempotente). Regra mantida: nunca truncar; excesso marca o arquivo como ERRO.
