-- Fase 1 - DDL do Data Warehouse (PostgreSQL)
-- Nesta fase, as tabelas do DW sao criadas sem PK/FK/UNIQUE/CHECK e sem indices.
-- Essas restricoes serao adicionadas apos carga e validacao na fase definida no plano.
-- A staging mantem PKs e FKs para garantir rastreabilidade dos dados de origem.

CREATE SCHEMA IF NOT EXISTS dw;

CREATE TABLE IF NOT EXISTS dw.dim_tempo (
    id_tempo INTEGER GENERATED ALWAYS AS IDENTITY,
    ano INTEGER
);

CREATE TABLE IF NOT EXISTS dw.dim_tipo_producao (
    id_tipo_producao INTEGER GENERATED ALWAYS AS IDENTITY,
    tipo_producao VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS dw.dim_pesquisador (
    id_pesquisador INTEGER GENERATED ALWAYS AS IDENTITY,
    id_lattes VARCHAR(100),
    chave_pesquisador TEXT,
    nome VARCHAR(100),
    atuacao_profissional TEXT
);

CREATE TABLE IF NOT EXISTS dw.dim_area (
    id_area INTEGER GENERATED ALWAYS AS IDENTITY,
    grande_area VARCHAR(255),
    area VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS dw.dim_linha_pesquisa (
    id_linha_pesquisa INTEGER GENERATED ALWAYS AS IDENTITY,
    linha_pesquisa VARCHAR(500),
    linha_pesquisa_normalizada VARCHAR(500)
);

-- A dimensao representa a localizacao da producao; o pesquisador e ligado
-- separadamente pelas tabelas fato. Por isso, id_lattes nao foi mantido aqui,
-- apesar de constar no dicionario original. Registrar esta diferenca no TCC.
CREATE TABLE IF NOT EXISTS dw.dim_localizacao_trabalhos (
    id_localizacao_trabalhos INTEGER GENERATED ALWAYS AS IDENTITY,
    instituicao VARCHAR(500),
    pais VARCHAR(100)
);

-- Granularidade: pesquisador, ano e tipo. id_tempo corrige o campo id_area
-- descrito como ano no dicionario de dados.
CREATE TABLE IF NOT EXISTS dw.fato_pesquisador_producoes (
    id_fato_pesquisador_producoes BIGINT GENERATED ALWAYS AS IDENTITY,
    id_pesquisador INTEGER,
    id_tempo INTEGER,
    id_tipo_producao INTEGER,
    qtd_producoes INTEGER
);

CREATE TABLE IF NOT EXISTS dw.fato_pesquisador_area_atuacao (
    id_fato_pesquisador_area_atuacao BIGINT GENERATED ALWAYS AS IDENTITY,
    id_pesquisador INTEGER,
    id_area INTEGER,
    presenca INTEGER
);

CREATE TABLE IF NOT EXISTS dw.fato_pesquisador_linha_pesquisa (
    id_fato_pesquisador_linha_pesquisa BIGINT GENERATED ALWAYS AS IDENTITY,
    id_pesquisador INTEGER,
    id_linha_pesquisa INTEGER,
    presenca INTEGER
);

CREATE TABLE IF NOT EXISTS dw.fato_pesquisador_producao_localizacao (
    id_fato_pesquisador_producao_localizacao BIGINT GENERATED ALWAYS AS IDENTITY,
    id_pesquisador INTEGER,
    id_tempo INTEGER,
    id_tipo_producao INTEGER,
    id_localizacao_trabalhos INTEGER,
    qtd_producoes INTEGER
);
