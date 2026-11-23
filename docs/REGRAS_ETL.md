# Regras de implementação do ETL — aditivo à Fase 1

Este documento orienta a implementação sem alterar o DDL aprovado.

- **Chave de junção:** `arquivo_id` é a chave de rastreabilidade de todas as tabelas da staging. Para agrupar por pessoa durante análises preliminares, use `stg.curriculo_origem.chave_pesquisador`; não junte por `id_lattes`.
- **ID ausente/parse com erro:** `id_lattes` permanece `NULL` se não for possível extrair um ID real. A `chave_pesquisador` é sempre preenchida: ID real quando disponível; caso contrário `ARQUIVO:<caminho_relativo>`, inclusive em arquivos com `status_processamento='ERRO'`.
- **Contagem de ordem:** `ordem_xml` começa em 1 e incrementa para cada elemento repetível do mapeamento correspondente. Atributos `SEQUENCIA-LINHA` e `SEQUENCIA-PROJETO` não substituem esse contador; preserve-os separadamente ou dentro de `dados_xml`.
- **Atuação profissional principal:** `stg.pesquisador.atuacao_profissional` recebe o nome da atuação com menor `sequencia_importancia` válida. Todas as ocorrências são preservadas em `stg.atuacao_profissional`. Empates ou ausência de sequência devem ser contabilizados no log e tratados por regra determinística documentada antes da carga.
- **Linha de pesquisa ativa:** ler `@FLAG-LINHA-DE-PESQUISA-ATIVA`; confirmar os valores reais antes da carga completa. Normalizar `SIM` -> `TRUE` e `NAO` -> `FALSE` sem distinção de caixa/espaços. Valores inesperados -> `NULL` e aviso de log com caminho/arquivo e valor original.
- **Consistência de chaves:** após inserir o registro do pesquisador, comparar `id_lattes_original` com `pesquisador.id_lattes` e `chave_pesquisador` em ambas as tabelas, vinculando sempre por `arquivo_id`. O teste deve falhar diante de qualquer divergência.
- **Duplicatas:** após preencher `curriculo_origem`, executar `sql/04_relatorio_duplicatas.sql`. O relatório é informativo; não exclui, ignora nem consolida arquivos. A regra será definida pelo responsável com base nos resultados.
- **DW:** omitir colunas identity nos `INSERT ... SELECT` das dimensões e fatos. Não fornecer IDs manualmente. Aplicar `sql/03_dw_constraints.sql` só depois de carregar e validar as dimensões e antes da carga das fatos; as FKs das fatos pertencem à Fase 7.
