-- 13_dw_fks_indices.sql - PKs das fatos, unicidade do grao, FKs para as dimensoes e indices para BI.
-- Pre-requisito: 02, 10, 03, 11, 12 aplicados e validados (fase7_validacao.py = TUDO CONFERE).
-- Repetivel: cada constraint so e criada se ainda nao existir. Nao apaga nem altera dados.
BEGIN;

DO $$
DECLARE r record;
BEGIN
    FOR r IN SELECT * FROM (VALUES
        -- chaves primarias das fatos
        ('fato_pesquisador_producoes',            'pk_fato_pesq_producoes',     'PRIMARY KEY (id_fato_pesquisador_producoes)'),
        ('fato_pesquisador_area_atuacao',         'pk_fato_pesq_area',          'PRIMARY KEY (id_fato_pesquisador_area_atuacao)'),
        ('fato_pesquisador_linha_pesquisa',       'pk_fato_pesq_linha',         'PRIMARY KEY (id_fato_pesquisador_linha_pesquisa)'),
        ('fato_pesquisador_producao_localizacao', 'pk_fato_pesq_prod_loc',      'PRIMARY KEY (id_fato_pesquisador_producao_localizacao)'),
        -- grao unico (evita dupla contagem em BI)
        ('fato_pesquisador_producoes',            'uq_fato_pesq_producoes_grao','UNIQUE (id_pesquisador, id_tempo, id_tipo_producao)'),
        ('fato_pesquisador_area_atuacao',         'uq_fato_pesq_area_grao',     'UNIQUE (id_pesquisador, id_area)'),
        ('fato_pesquisador_linha_pesquisa',       'uq_fato_pesq_linha_grao',    'UNIQUE (id_pesquisador, id_linha_pesquisa)'),
        ('fato_pesquisador_producao_localizacao', 'uq_fato_pesq_prod_loc_grao', 'UNIQUE (id_pesquisador, id_tempo, id_tipo_producao, id_localizacao_trabalhos)'),
        -- chaves estrangeiras
        ('fato_pesquisador_producoes',            'fk_prod_pesquisador',  'FOREIGN KEY (id_pesquisador) REFERENCES dw.dim_pesquisador(id_pesquisador)'),
        ('fato_pesquisador_producoes',            'fk_prod_tempo',        'FOREIGN KEY (id_tempo) REFERENCES dw.dim_tempo(id_tempo)'),
        ('fato_pesquisador_producoes',            'fk_prod_tipo',         'FOREIGN KEY (id_tipo_producao) REFERENCES dw.dim_tipo_producao(id_tipo_producao)'),
        ('fato_pesquisador_area_atuacao',         'fk_area_pesquisador',  'FOREIGN KEY (id_pesquisador) REFERENCES dw.dim_pesquisador(id_pesquisador)'),
        ('fato_pesquisador_area_atuacao',         'fk_area_area',         'FOREIGN KEY (id_area) REFERENCES dw.dim_area(id_area)'),
        ('fato_pesquisador_linha_pesquisa',       'fk_linha_pesquisador', 'FOREIGN KEY (id_pesquisador) REFERENCES dw.dim_pesquisador(id_pesquisador)'),
        ('fato_pesquisador_linha_pesquisa',       'fk_linha_linha',       'FOREIGN KEY (id_linha_pesquisa) REFERENCES dw.dim_linha_pesquisa(id_linha_pesquisa)'),
        ('fato_pesquisador_producao_localizacao', 'fk_loc_pesquisador',   'FOREIGN KEY (id_pesquisador) REFERENCES dw.dim_pesquisador(id_pesquisador)'),
        ('fato_pesquisador_producao_localizacao', 'fk_loc_tempo',         'FOREIGN KEY (id_tempo) REFERENCES dw.dim_tempo(id_tempo)'),
        ('fato_pesquisador_producao_localizacao', 'fk_loc_tipo',          'FOREIGN KEY (id_tipo_producao) REFERENCES dw.dim_tipo_producao(id_tipo_producao)'),
        ('fato_pesquisador_producao_localizacao', 'fk_loc_localizacao',   'FOREIGN KEY (id_localizacao_trabalhos) REFERENCES dw.dim_localizacao_trabalhos(id_localizacao_trabalhos)')
    ) AS v(tabela, nome, ddl)
    LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_constraint c
                       JOIN pg_class t ON t.oid = c.conrelid
                       JOIN pg_namespace n ON n.oid = t.relnamespace
                       WHERE c.conname = r.nome AND n.nspname = 'dw' AND t.relname = r.tabela) THEN
            EXECUTE format('ALTER TABLE dw.%I ADD CONSTRAINT %I %s', r.tabela, r.nome, r.ddl);
        END IF;
    END LOOP;
END $$;

-- Indices para filtros e junções de BI (o pesquisador ja e coberto pelo inicio das UNIQUE acima).
CREATE INDEX IF NOT EXISTS ix_prod_tempo       ON dw.fato_pesquisador_producoes (id_tempo);
CREATE INDEX IF NOT EXISTS ix_prod_tipo        ON dw.fato_pesquisador_producoes (id_tipo_producao);
CREATE INDEX IF NOT EXISTS ix_area_area        ON dw.fato_pesquisador_area_atuacao (id_area);
CREATE INDEX IF NOT EXISTS ix_linha_linha      ON dw.fato_pesquisador_linha_pesquisa (id_linha_pesquisa);
CREATE INDEX IF NOT EXISTS ix_loc_tempo        ON dw.fato_pesquisador_producao_localizacao (id_tempo);
CREATE INDEX IF NOT EXISTS ix_loc_tipo         ON dw.fato_pesquisador_producao_localizacao (id_tipo_producao);
CREATE INDEX IF NOT EXISTS ix_loc_localizacao  ON dw.fato_pesquisador_producao_localizacao (id_localizacao_trabalhos);
CREATE INDEX IF NOT EXISTS ix_dim_pesq_id_lattes ON dw.dim_pesquisador (id_lattes);
CREATE INDEX IF NOT EXISTS ix_dim_loc_pais     ON dw.dim_localizacao_trabalhos (pais);

COMMIT;

ANALYZE dw.dim_pesquisador; ANALYZE dw.dim_tempo; ANALYZE dw.dim_tipo_producao; ANALYZE dw.dim_area;
ANALYZE dw.dim_linha_pesquisa; ANALYZE dw.dim_localizacao_trabalhos;
ANALYZE dw.fato_pesquisador_producoes; ANALYZE dw.fato_pesquisador_area_atuacao;
ANALYZE dw.fato_pesquisador_linha_pesquisa; ANALYZE dw.fato_pesquisador_producao_localizacao;
