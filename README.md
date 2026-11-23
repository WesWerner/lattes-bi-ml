# Business Intelligence e Machine Learning para integração de dados de pesquisas no Brasil

Código do Trabalho de Conclusão de Curso de Wesley Wernersbach Aranha
(Ciência da Computação, Universidade Federal do Espírito Santo, 2026).

O projeto integra 57.624 Currículos Lattes (XML) em um banco PostgreSQL, organiza
os dados em um *data warehouse*, agrupa os títulos das produções em temas com
modelagem de tópicos (BERTopic) e publica indicadores em um painel Power BI.

```
XML Lattes ──► stg (staging) ──► dw (estrela) ──► ml (texto e tópicos) ──► dw (temas) ──► bi (views) ──► Power BI
```

> **Dados fora do repositório.** Os XMLs dos currículos, os *dumps* do banco, os
> embeddings e os relatórios com identificadores de pesquisadores **não** são
> publicados (dados pessoais, LGPD). Aqui estão apenas código, SQL, documentação
> e saídas agregadas. O painel usa somente as views `bi.*`: sem nomes nem
> identificadores Lattes, e grupos com menos de cinco pesquisadores são omitidos.

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `config/mapeamento.yaml` | mapeamento XPath → colunas da staging |
| `etl/` | extração e carga (`extractor`, `load`) e etapas de ML (`corpus`, `embeddings`, `topicos`, `avaliacao`, `macrotemas`) |
| `sql/` | DDL e cargas: `stg`, `dw`, tópicos e views de BI (esquema `bi`) |
| `scripts/` | inventário dos XMLs, auditorias, validações e recorte dos gráficos |
| `tests/` | testes automatizados (os de integração exigem banco e são pulados sem ele) |
| `powerbi/` | painel `TCC_LATTES.pbix`, tema, fundos e descrição da interface |
| `figuras_bi/` | gráficos do painel, um por arquivo |
| `docs/` | decisões de projeto, regras do ETL e guia do painel |

## Instalação

Python 3.11 ou superior e PostgreSQL 16.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

A conexão com o banco usa variáveis de ambiente (nada de senha no código):

```bash
export PGHOST=localhost PGPORT=5432
export PGDATABASE=dw_lattes_dev PGUSER=seu_usuario PGPASSWORD=sua_senha
```

## Ordem de execução

1. **Inventário e mapeamento** (uma vez): `python scripts/inventario_xml.py PASTA_XMLS`,
   depois `python scripts/validate_mapping.py`.
2. **Staging:** `sql/01_stg.sql`, `05_alter_paginas.sql`, `06_alter_limites.sql`, e a carga:
   `python -m etl.load --xml-dir PASTA_XMLS --confirmar-banco dw_lattes_dev`
   (use `--dry-run` para testar sem gravar). Relatório de duplicatas: `sql/04_relatorio_duplicatas.sql`.
3. **Data warehouse:** `sql/02_dw.sql`, `10_dw_dimensoes.sql`, `03_dw_constraints.sql`,
   `11_dw_fatos.sql`, `12_dw_localizacao.sql`, `13_dw_fks_indices.sql`.
   Validação: `python scripts/fase7_validacao.py`.
4. **Tópicos (ML):**
   `python -m etl.corpus`, `python -m etl.embeddings`, `python -m etl.topicos`,
   `python -m etl.avaliacao` e `python -m etl.macrotemas`, todos com
   `--confirmar-banco NOME_DO_BANCO`; depois `sql/20_macrotemas_rotulos.sql` e
   `sql/21_dw_topicos.sql`. Resumo: `python scripts/fase8_resumo.py`.
5. **BI:** `python scripts/rodar_sql.py sql/30_bi_views.sql NOME_DO_BANCO` cria o esquema `bi`;
   edite a senha em `sql/32_bi_login.sql` e rode-o para criar o login de leitura.
   Abra `powerbi/TCC_LATTES.pbix` e aponte para o banco (veja `docs/GUIA_BI_POWERBI.md`).
   Para gerar uma imagem por gráfico: `python scripts/recortar_graficos.py EXPORTACAO.pdf figuras_bi --por-pagina`.

## Testes

```bash
pytest -q
```

Os testes de unidade rodam sem banco. Os de integração (`test_schema.py`,
`test_key_consistency.py`) são pulados, a menos que `PGDATABASE` aponte para um banco
de teste.

## Documentação

- `docs/DECISOES_FASE1.md`: modelagem e decisões de tipos
- `docs/REGRAS_ETL.md`: regras de implementação do ETL
- `docs/RELATORIO_FASE2.md`: validação do mapeamento XML → staging
- `docs/GUIA_BI_POWERBI.md`: conexão, modelo, medidas DAX e páginas do painel

## Licença

A definir (sugestão: MIT para o código).
