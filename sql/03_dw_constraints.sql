-- Fase 1 - constraints aditivas das dimensoes DW.
-- Executar somente APOS carregar e validar as dimensoes e ANTES de carregar as fatos.
-- Nao cria FKs das fatos (essas ficam para a Fase 7). Nao apaga nem recria tabelas.
-- As verificacoes abaixo tornam o script repetivel sem depender de DROP/ALTER destrutivo.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace WHERE c.conname = 'pk_dim_tempo' AND n.nspname = 'dw' AND t.relname = 'dim_tempo') THEN
        ALTER TABLE dw.dim_tempo ADD CONSTRAINT pk_dim_tempo PRIMARY KEY (id_tempo);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace WHERE c.conname = 'uq_dim_tempo_ano' AND n.nspname = 'dw' AND t.relname = 'dim_tempo') THEN
        ALTER TABLE dw.dim_tempo ADD CONSTRAINT uq_dim_tempo_ano UNIQUE (ano);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace WHERE c.conname = 'pk_dim_tipo_producao' AND n.nspname = 'dw' AND t.relname = 'dim_tipo_producao') THEN
        ALTER TABLE dw.dim_tipo_producao ADD CONSTRAINT pk_dim_tipo_producao PRIMARY KEY (id_tipo_producao);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace WHERE c.conname = 'uq_dim_tipo_producao_tipo' AND n.nspname = 'dw' AND t.relname = 'dim_tipo_producao') THEN
        ALTER TABLE dw.dim_tipo_producao ADD CONSTRAINT uq_dim_tipo_producao_tipo UNIQUE (tipo_producao);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace WHERE c.conname = 'pk_dim_pesquisador' AND n.nspname = 'dw' AND t.relname = 'dim_pesquisador') THEN
        ALTER TABLE dw.dim_pesquisador ADD CONSTRAINT pk_dim_pesquisador PRIMARY KEY (id_pesquisador);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace WHERE c.conname = 'uq_dim_pesquisador_chave' AND n.nspname = 'dw' AND t.relname = 'dim_pesquisador') THEN
        ALTER TABLE dw.dim_pesquisador ADD CONSTRAINT uq_dim_pesquisador_chave UNIQUE (chave_pesquisador);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace WHERE c.conname = 'pk_dim_area' AND n.nspname = 'dw' AND t.relname = 'dim_area') THEN
        ALTER TABLE dw.dim_area ADD CONSTRAINT pk_dim_area PRIMARY KEY (id_area);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace WHERE c.conname = 'uq_dim_area_grande_area_area' AND n.nspname = 'dw' AND t.relname = 'dim_area') THEN
        ALTER TABLE dw.dim_area ADD CONSTRAINT uq_dim_area_grande_area_area UNIQUE (grande_area, area);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace WHERE c.conname = 'pk_dim_linha_pesquisa' AND n.nspname = 'dw' AND t.relname = 'dim_linha_pesquisa') THEN
        ALTER TABLE dw.dim_linha_pesquisa ADD CONSTRAINT pk_dim_linha_pesquisa PRIMARY KEY (id_linha_pesquisa);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace WHERE c.conname = 'uq_dim_linha_pesquisa_normalizada' AND n.nspname = 'dw' AND t.relname = 'dim_linha_pesquisa') THEN
        ALTER TABLE dw.dim_linha_pesquisa ADD CONSTRAINT uq_dim_linha_pesquisa_normalizada UNIQUE (linha_pesquisa_normalizada);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace WHERE c.conname = 'pk_dim_localizacao_trabalhos' AND n.nspname = 'dw' AND t.relname = 'dim_localizacao_trabalhos') THEN
        ALTER TABLE dw.dim_localizacao_trabalhos ADD CONSTRAINT pk_dim_localizacao_trabalhos PRIMARY KEY (id_localizacao_trabalhos);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace WHERE c.conname = 'uq_dim_localizacao_instituicao_pais' AND n.nspname = 'dw' AND t.relname = 'dim_localizacao_trabalhos') THEN
        ALTER TABLE dw.dim_localizacao_trabalhos ADD CONSTRAINT uq_dim_localizacao_instituicao_pais UNIQUE (instituicao, pais);
    END IF;
END $$;
