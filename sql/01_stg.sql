-- Fase 1 - DDL da staging (PostgreSQL)
-- Tipos de texto limitados alinhados ao Apêndice A quando aplicável.
-- Os inventários disponíveis informam caminhos e frequências, não comprimentos
-- máximos dos valores; o ETL deve detectar valores acima dos limites antes do COPY.
-- Objetivos:
--   1) preservar cada XML como uma unidade de origem;
--   2) manter o ID Lattes original sem inventar um ID Lattes quando ele estiver ausente;
--   3) permitir mais de um arquivo/versao para o mesmo id_lattes;
--   4) preservar rastreabilidade e integridade das linhas extraidas.
--
-- Observacao: execute em uma base de desenvolvimento. Este script cria tabelas,
-- mas nao apaga nem altera tabelas que ja existam.

CREATE SCHEMA IF NOT EXISTS stg;

-- Uma linha por arquivo XML analisado. caminho_relativo identifica o arquivo
-- dentro do conjunto de origem; hash_sha256 ajuda a reconhecer arquivos iguais.
CREATE TABLE IF NOT EXISTS stg.curriculo_origem (
    arquivo_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome_arquivo TEXT NOT NULL,
    caminho_relativo TEXT NOT NULL UNIQUE,
    hash_sha256 VARCHAR(64)
        CHECK (hash_sha256 IS NULL OR hash_sha256 ~ '^[0-9a-fA-F]{64}$'),
    id_lattes_original VARCHAR(100),
    chave_pesquisador TEXT NOT NULL,
    status_processamento VARCHAR(15) NOT NULL DEFAULT 'PENDENTE'
        CHECK (status_processamento IN ('PENDENTE', 'PROCESSADO', 'ERRO')),
    tipo_erro TEXT,
    data_processamento TIMESTAMPTZ
);

-- Uma linha por XML, e nao necessariamente uma linha por pessoa distinta.
-- id_lattes preserva o valor encontrado no XML; fica NULL se ausente.
-- chave_pesquisador e preenchida pelo ETL:
--   ID original, quando existe; caso contrario, uma chave tecnica baseada no arquivo.
-- Nao ha UNIQUE em id_lattes porque podem existir versoes/arquivos repetidos.
CREATE TABLE IF NOT EXISTS stg.pesquisador (
    id_pesquisador BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    arquivo_id BIGINT NOT NULL UNIQUE
        REFERENCES stg.curriculo_origem(arquivo_id),
    id_lattes VARCHAR(100),
    chave_pesquisador TEXT NOT NULL,
    nome VARCHAR(100),
    atuacao_profissional TEXT
);

-- Tabela auxiliar para preservar todas as atuacoes profissionais encontradas.
CREATE TABLE IF NOT EXISTS stg.atuacao_profissional (
    id_atuacao BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    arquivo_id BIGINT NOT NULL
        REFERENCES stg.curriculo_origem(arquivo_id),
    id_lattes VARCHAR(100),
    ordem_xml INTEGER NOT NULL,
    sequencia_importancia INTEGER,
    nome_instituicao TEXT,
    dados_xml JSONB,
    CONSTRAINT uq_atuacao_por_arquivo_ordem UNIQUE (arquivo_id, ordem_xml)
);

CREATE TABLE IF NOT EXISTS stg.linha_pesquisador (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    arquivo_id BIGINT NOT NULL
        REFERENCES stg.curriculo_origem(arquivo_id),
    id_lattes VARCHAR(100),
    ordem_xml INTEGER NOT NULL,
    linha_pesquisa VARCHAR(500),
    titulo_ingles VARCHAR(1000),
    objetivos TEXT,
    objetivos_ingles TEXT,
    indicador_linha_pesquisa_ativa BOOLEAN,
    CONSTRAINT uq_linha_por_arquivo_ordem UNIQUE (arquivo_id, ordem_xml)
);

CREATE TABLE IF NOT EXISTS stg.areas_atuacao (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    arquivo_id BIGINT NOT NULL
        REFERENCES stg.curriculo_origem(arquivo_id),
    id_lattes VARCHAR(100),
    ordem_xml INTEGER NOT NULL,
    nome_grande_area VARCHAR(255),
    nome_area VARCHAR(255),
    nome_sub_area VARCHAR(255),
    nome_especialidade VARCHAR(255),
    CONSTRAINT uq_area_por_arquivo_ordem UNIQUE (arquivo_id, ordem_xml)
);

CREATE TABLE IF NOT EXISTS stg.projetos_pesquisa (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    arquivo_id BIGINT NOT NULL
        REFERENCES stg.curriculo_origem(arquivo_id),
    id_lattes VARCHAR(100),
    ordem_xml INTEGER NOT NULL,
    identificador_projeto VARCHAR(100),
    ano_inicio VARCHAR(10),
    ano_fim VARCHAR(10),
    nome_projeto VARCHAR(500),
    descricao_projeto TEXT,
    situacao VARCHAR(100),
    natureza VARCHAR(100),
    CONSTRAINT uq_projeto_por_arquivo_ordem UNIQUE (arquivo_id, ordem_xml)
);

CREATE TABLE IF NOT EXISTS stg.artigos (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    arquivo_id BIGINT NOT NULL
        REFERENCES stg.curriculo_origem(arquivo_id),
    id_lattes VARCHAR(100),
    ordem_xml INTEGER NOT NULL,
    ano VARCHAR(10),
    titulo VARCHAR(1000),
    doi VARCHAR(255),
    idioma VARCHAR(50),
    natureza VARCHAR(50),
    meio_divulgacao VARCHAR(50),
    titulo_periodico VARCHAR(500),
    volume VARCHAR(50),
    pagina_inicial VARCHAR(50),
    pagina_final VARCHAR(50),
    issn VARCHAR(20),
    local_publicacao VARCHAR(255),
    autores TEXT,
    CONSTRAINT uq_artigo_por_arquivo_ordem UNIQUE (arquivo_id, ordem_xml)
);

CREATE TABLE IF NOT EXISTS stg.livros (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    arquivo_id BIGINT NOT NULL
        REFERENCES stg.curriculo_origem(arquivo_id),
    id_lattes VARCHAR(100),
    ordem_xml INTEGER NOT NULL,
    ano VARCHAR(10),
    titulo VARCHAR(1000),
    numero_edicao VARCHAR(50),
    cidade_editora VARCHAR(255),
    nome_editora VARCHAR(255),
    numero_volumes VARCHAR(50),
    numero_paginas VARCHAR(50),
    isbn VARCHAR(50),
    autores TEXT,
    CONSTRAINT uq_livro_por_arquivo_ordem UNIQUE (arquivo_id, ordem_xml)
);

CREATE TABLE IF NOT EXISTS stg.capitulos_livros (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    arquivo_id BIGINT NOT NULL
        REFERENCES stg.curriculo_origem(arquivo_id),
    id_lattes VARCHAR(100),
    ordem_xml INTEGER NOT NULL,
    ano VARCHAR(10),
    titulo_capitulo VARCHAR(1000),
    titulo_livro VARCHAR(1000),
    doi VARCHAR(255),
    idioma VARCHAR(50),
    meio_divulgacao VARCHAR(50),
    numero_edicao VARCHAR(50),
    cidade_editora VARCHAR(255),
    nome_editora VARCHAR(255),
    isbn VARCHAR(50),
    pagina_inicial VARCHAR(50),
    pagina_final VARCHAR(50),
    numero_volumes VARCHAR(50),
    organizadores VARCHAR(1000),
    autores TEXT,
    CONSTRAINT uq_capitulo_por_arquivo_ordem UNIQUE (arquivo_id, ordem_xml)
);

CREATE TABLE IF NOT EXISTS stg.textos_jornais (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    arquivo_id BIGINT NOT NULL
        REFERENCES stg.curriculo_origem(arquivo_id),
    id_lattes VARCHAR(100),
    ordem_xml INTEGER NOT NULL,
    ano VARCHAR(10),
    titulo VARCHAR(1000),
    titulo_jornal VARCHAR(500),
    doi VARCHAR(255),
    idioma VARCHAR(50),
    natureza VARCHAR(100),
    meio_divulgacao VARCHAR(50),
    data_publicacao VARCHAR(20),
    local_publicacao VARCHAR(255),
    pagina_inicial VARCHAR(50),
    pagina_final VARCHAR(50),
    volume VARCHAR(20),
    issn VARCHAR(20),
    autores TEXT,
    CONSTRAINT uq_texto_jornal_por_arquivo_ordem UNIQUE (arquivo_id, ordem_xml)
);

CREATE TABLE IF NOT EXISTS stg.trabalhos_eventos (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    arquivo_id BIGINT NOT NULL
        REFERENCES stg.curriculo_origem(arquivo_id),
    id_lattes VARCHAR(100),
    ordem_xml INTEGER NOT NULL,
    ano VARCHAR(10),
    titulo VARCHAR(1000),
    nome_evento VARCHAR(500),
    titulo_anais VARCHAR(500),
    doi VARCHAR(255),
    idioma VARCHAR(50),
    natureza VARCHAR(50),
    meio_divulgacao VARCHAR(50),
    pais_evento VARCHAR(100),
    ano_realizacao VARCHAR(10),
    cidade_evento VARCHAR(255),
    classificacao_evento VARCHAR(100),
    nome_editora VARCHAR(255),
    cidade_editora VARCHAR(255),
    isbn VARCHAR(50),
    volume VARCHAR(20),
    pagina_inicial VARCHAR(50),
    pagina_final VARCHAR(50),
    autores TEXT,
    CONSTRAINT uq_trabalho_evento_por_arquivo_ordem UNIQUE (arquivo_id, ordem_xml)
);

CREATE TABLE IF NOT EXISTS stg.apresentacoes_trabalho (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    arquivo_id BIGINT NOT NULL
        REFERENCES stg.curriculo_origem(arquivo_id),
    id_lattes VARCHAR(100),
    ordem_xml INTEGER NOT NULL,
    ano VARCHAR(10),
    titulo VARCHAR(1000),
    doi VARCHAR(255),
    idioma VARCHAR(50),
    natureza VARCHAR(100),
    pais VARCHAR(100),
    nome_evento VARCHAR(500),
    cidade_apresentacao VARCHAR(255),
    local_apresentacao VARCHAR(255),
    instituicao_promotora VARCHAR(500),
    autores TEXT,
    CONSTRAINT uq_apresentacao_por_arquivo_ordem UNIQUE (arquivo_id, ordem_xml)
);

CREATE TABLE IF NOT EXISTS stg.outras_producoes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    arquivo_id BIGINT NOT NULL
        REFERENCES stg.curriculo_origem(arquivo_id),
    id_lattes VARCHAR(100),
    ordem_xml INTEGER NOT NULL,
    ano VARCHAR(10),
    titulo VARCHAR(1000),
    doi VARCHAR(255),
    idioma VARCHAR(50),
    natureza VARCHAR(200),
    meio_divulgacao VARCHAR(50),
    pais_publicacao VARCHAR(100),
    cidade_editora VARCHAR(255),
    editora VARCHAR(255),
    issn_isbn VARCHAR(50),
    numero_paginas VARCHAR(50),
    autores TEXT,
    CONSTRAINT uq_outra_producao_por_arquivo_ordem UNIQUE (arquivo_id, ordem_xml)
);

-- Indices de consulta (principalmente por id_lattes) serao criados apos a carga.
-- As chaves estrangeiras de cada linha para curriculo_origem e as PKs da staging
-- sao mantidas desde o inicio para evitar linhas sem arquivo de origem.
