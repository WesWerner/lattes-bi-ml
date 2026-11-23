# Guia do Power BI Desktop - dashboards do TCC

## 1. Conexão
1. Power BI Desktop → **Obter dados** → **Banco de dados PostgreSQL**.
   - Servidor: `localhost` (ou `localhost:5432`); Banco: `dw_lattes`; **Modo: Importar**.
   - Se pedir o provedor Npgsql, instale-o (aparece o link na própria mensagem de erro) e reabra o Power BI.
2. Credenciais → aba **Banco de dados** → usuário `bi_app` e a senha que você definiu em `32_bi_login.sql`.
   Esse login só enxerga o esquema `bi`; ele não consegue ler nomes nem IDs Lattes (testado).
3. No navegador, expanda `bi` e marque as 17 views: `d_tempo`, `d_tipo_producao`, `d_grande_area`, `d_macrotema`,
   `v_producao_ano_tipo`, `v_pesquisadores_ano`, `v_distribuicao_producao_pesquisador`, `v_pesquisadores_area`,
   `v_producao_grande_area_ano`, `v_linhas_pesquisa`, `v_macrotema_ano_tipo`, `v_topicos`, `v_macrotema_grande_area`,
   `v_qualidade_classificacao`, `v_pais_ano_tipo`, `v_obras_distintas`, `v_kpis_gerais`. **Carregar**.
4. **Exibir → Temas → Procurar temas** e escolha `powerbi/tema_tcc.json` (paleta segura para daltonismo).

## 2. Modelo (aba Modelo)
Crie relacionamentos **muitos-para-um**, filtro em uma direção (da dimensão `d_*` para a view):
| De (view) | Coluna | Para | Coluna |
|---|---|---|---|
| v_producao_ano_tipo, v_pesquisadores_ano, v_producao_grande_area_ano, v_macrotema_ano_tipo, v_qualidade_classificacao, v_pais_ano_tipo, v_obras_distintas | `ano_rotulo` | d_tempo | `ano_rotulo` |
| v_producao_ano_tipo, v_distribuicao_producao_pesquisador, v_macrotema_ano_tipo, v_qualidade_classificacao, v_pais_ano_tipo, v_obras_distintas | `tipo_producao` | d_tipo_producao | `tipo_producao` |
| v_pesquisadores_area, v_producao_grande_area_ano, v_macrotema_grande_area | `grande_area` | d_grande_area | `grande_area` |
| v_macrotema_ano_tipo, v_macrotema_grande_area, v_topicos | `macrotema` | d_macrotema | `macrotema` |

`v_kpis_gerais`, `v_linhas_pesquisa` e `v_distribuicao_producao_pesquisador` (só por tipo) ficam sem relação com `d_tempo`.
Em `d_tempo`, selecione a coluna `ano_rotulo` → **Classificar por coluna** → `ano`.

## 3. Cuidado com "pesquisadores distintos" (importante)
`qtd_pesquisadores` conta pessoas **distintas dentro de cada linha**. Somar essa coluna entre linhas conta a mesma pessoa várias vezes.
- Em todas as views, deixe `qtd_pesquisadores` como **Não resumir**; use-a apenas em tabelas/tooltips ou nas medidas abaixo, onde o nível do gráfico é o mesmo da view.
- Os totais gerais corretos estão em `v_kpis_gerais`. As views omitem linhas com menos de 5 pesquisadores, então a soma das linhas pode ficar um pouco abaixo desse total. Isso é intencional (privacidade) e deve ser dito no texto do TCC.

## 4. Medidas DAX (tabela `Medidas`: Inserir dados → tabela vazia chamada `Medidas`)
```DAX
Total de produções = SUM ( v_kpis_gerais[total_producoes] )
Pesquisadores com produção = SUM ( v_kpis_gerais[pesquisadores_com_producao] )
Tópicos = SUM ( v_kpis_gerais[topicos] )
Macrotemas = SUM ( v_kpis_gerais[macrotemas] )

Produções = SUM ( v_producao_ano_tipo[qtd_producoes] )
Pesquisadores por ano = SUM ( v_pesquisadores_ano[qtd_pesquisadores] )   -- use só em gráficos por ano

Produções por grande área = SUM ( v_producao_grande_area_ano[qtd_producoes] )
Pesquisadores por área = SUM ( v_pesquisadores_area[qtd_pesquisadores] )   -- use só por grande área/área

Produções por macrotema = SUM ( v_macrotema_ano_tipo[qtd_producoes] )
Participação do macrotema =
    DIVIDE (
        [Produções por macrotema],
        CALCULATE ( [Produções por macrotema], ALL ( v_macrotema_ano_tipo[macrotema] ) )
    )

% tópico aproximado =
    DIVIDE ( SUM ( v_qualidade_classificacao[qtd_topico_aproximado] ), SUM ( v_qualidade_classificacao[qtd_producoes] ) )
% sem tema =
    DIVIDE ( SUM ( v_qualidade_classificacao[qtd_sem_tema] ), SUM ( v_qualidade_classificacao[qtd_producoes] ) )

Produções com país =
    CALCULATE ( SUM ( v_pais_ano_tipo[qtd_producoes] ), v_pais_ano_tipo[pais] <> "Não informado" )
% fora do Brasil =
    DIVIDE (
        CALCULATE ( SUM ( v_pais_ano_tipo[qtd_producoes] ), v_pais_ano_tipo[fora_do_brasil] = TRUE () ),
        [Produções com país]
    )

Itens = SUM ( v_obras_distintas[qtd_itens] )
Obras distintas = SUM ( v_obras_distintas[qtd_obras_distintas] )   -- distintas dentro de cada ano e tipo
Razão itens/obras = DIVIDE ( [Itens], [Obras distintas] )
```
Formate os `%` como porcentagem (1 casa) e `Razão` com 2 casas.

## 5. Páginas sugeridas (16:9, uma ideia por página)
Em todas: título claro, segmentação **Ano** (faixa, a partir de `d_tempo[ano]`, ignorando "Desconhecido") e **Tipo de produção**
(sincronize com **Exibir → Sincronizar segmentações**). Rodapé: "Fonte: currículos Lattes da UFES (STI/UFES), 2026. Dados agregados; grupos com menos de 5 pesquisadores omitidos."

**Página 1 - Visão geral** (I1 a I4)
- 4 cartões: Total de produções, Pesquisadores com produção, Tópicos, Macrotemas.
- Linhas: `ano_rotulo` × `Produções`, legenda `tipo_producao` (I1, I2).
- Barras horizontais: `tipo_producao` × `Produções` (I2).
- Colunas: faixas de `v_distribuicao_producao_pesquisador` (`faixa` classificada por `ordem_faixa`) × `qtd_pesquisadores` (I4).
- Linha (eixo secundário): `Pesquisadores por ano` (I3).

**Página 2 - Perfil dos pesquisadores** (I5 a I7)
- Barras: `grande_area` × `Pesquisadores por área` (I5); detalhamento por `area` com **drill down**.
- Barras: `grande_area` × `Produções por grande área` (I6). Nota na página: "um pesquisador pode atuar em mais de uma área".
- Top 15 `linha_pesquisa` por `qtd_pesquisadores` (filtro **N superior**) (I7).

**Página 3 - Temas** (I8 a I12)
- Barras: `macrotema` × `Produções por macrotema`, **filtrando fora** "Sem tema" (I8).
- Linhas: `ano_rotulo` × `Produções por macrotema`, legenda `macrotema`, filtro N superior 5 (I9).
- Matriz: `macrotema` (linhas) × `tipo_producao` (colunas) com formatação condicional (I11).
- Tabela: `topico`, `macrotema`, `palavras_chave`, `qtd_producoes`, `marcado_revisao` (I10). Segmentação por `d_macrotema[macrotema]`.
- Mapa de árvore ou matriz: `grande_area` × `macrotema` com `qtd_producoes` de `v_macrotema_grande_area` (I12).

**Página 4 - Internacionalização** (I14)
- Mapa preenchido por `pais` × `Produções com país` (se algum país não for reconhecido, ajuste **Categoria de dados → País/Região**).
- Linha: `% fora do Brasil` por `ano_rotulo`.
- Barras: top 15 países excluindo "Brasil" e "Não informado".
- Nota: "Disponível apenas para trabalhos em eventos, apresentações e outras produções."

**Página 5 - Qualidade e obras distintas** (I13, I15)
- Barras: `tipo_producao` × `% tópico aproximado` e `% sem tema` (I13).
- Linha: `Razão itens/obras` por `ano_rotulo` (I15), com barras de `Obras distintas`.
- Nota: "Considera apenas títulos válidos (3 palavras ou mais). Uma obra com coautores aparece uma vez em cada currículo."

## 6. Capturas para o TCC
**Arquivo → Exportar → PDF** ou use a ferramenta de recorte em cada página (1920x1080). Numere as figuras no texto
("Figura X - Painel de ..."), cite os indicadores (I1...I15) e deixe as notas de privacidade visíveis nas capturas.
Salve o `.pbix` na pasta do projeto, sem credenciais salvas no arquivo (Arquivo → Opções → Configurações de fonte de dados → Limpar permissões antes de compartilhar).
