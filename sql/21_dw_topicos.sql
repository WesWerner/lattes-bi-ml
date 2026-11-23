-- 21_dw_topicos.sql - integra os topicos ao dw: dim_macrotema, dim_topico e fato_pesquisador_topico.
-- Pre-requisitos: dw completo (fases 7), ml.corpus_titulo / ml.titulo_unico / ml.topico / ml.titulo_topico
-- (Fase 8.1-8.3) e etl.macrotemas ja executado (cria ml.macrotema e a view ml.v_titulo_tema).
-- Granularidade da fato: pesquisador x ano x tipo de producao x topico. Cada item conta uma vez por
-- pesquisador (uma obra com coautores aparece em cada curriculo, como nas demais fatos).
-- Fora da fato: itens com titulo invalido (vazio/curto); eles continuam so em fato_pesquisador_producoes.
-- Topico final = topico estrito do BERTopic; se "sem tema" e houve topico aproximado (similaridade >= limiar),
-- usa o aproximado (qtd_topico_aproximado conta esses itens); senao id_topico = -1 ("Sem tema").
-- Idempotente: recria as 3 tabelas a cada execucao.
BEGIN;

DO $$
BEGIN
    IF to_regclass('ml.v_titulo_tema') IS NULL OR to_regclass('ml.macrotema') IS NULL THEN
        RAISE EXCEPTION 'Rode antes: python -m etl.macrotemas --confirmar-banco <banco> (cria ml.macrotema e ml.v_titulo_tema).';
    END IF;
END $$;

-- Colunas opcionais (preenchidas por sql/20_macrotemas_rotulos.sql); aqui so garantem que existam.
ALTER TABLE ml.macrotema ADD COLUMN IF NOT EXISTS rotulo_curado TEXT;
ALTER TABLE ml.topico    ADD COLUMN IF NOT EXISTS revisao TEXT;

DROP TABLE IF EXISTS dw.fato_pesquisador_topico;
DROP TABLE IF EXISTS dw.dim_topico;
DROP TABLE IF EXISTS dw.dim_macrotema;

CREATE TABLE dw.dim_macrotema (
    id_macrotema INTEGER PRIMARY KEY,
    macrotema VARCHAR(200) NOT NULL,
    palavras_chave TEXT,
    n_topicos INTEGER NOT NULL,
    n_titulos INTEGER NOT NULL
);

CREATE TABLE dw.dim_topico (
    id_topico INTEGER PRIMARY KEY,
    topico VARCHAR(300) NOT NULL,
    palavras_chave TEXT,
    id_macrotema INTEGER NOT NULL REFERENCES dw.dim_macrotema (id_macrotema),
    revisao TEXT,
    n_titulos_estrito INTEGER NOT NULL
);

CREATE TABLE dw.fato_pesquisador_topico (
    id_fato_pesquisador_topico BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_pesquisador INTEGER NOT NULL REFERENCES dw.dim_pesquisador (id_pesquisador),
    id_tempo INTEGER NOT NULL REFERENCES dw.dim_tempo (id_tempo),
    id_tipo_producao INTEGER NOT NULL REFERENCES dw.dim_tipo_producao (id_tipo_producao),
    id_topico INTEGER NOT NULL REFERENCES dw.dim_topico (id_topico),
    qtd_producoes INTEGER NOT NULL,
    qtd_topico_aproximado INTEGER NOT NULL,
    CONSTRAINT uq_fato_pesq_topico UNIQUE (id_pesquisador, id_tempo, id_tipo_producao, id_topico)
);

-- Macrotemas (nome curado quando existir; -1 = "Sem tema").
INSERT INTO dw.dim_macrotema (id_macrotema, macrotema, palavras_chave, n_topicos, n_titulos)
SELECT m.id_macrotema, COALESCE(m.rotulo_curado, m.rotulo),
       (SELECT string_agg(e ->> 0, '; ' ORDER BY ord) FROM jsonb_array_elements(m.palavras) WITH ORDINALITY t(e, ord)),
       m.n_topicos, m.n_titulos
FROM ml.macrotema m;
INSERT INTO dw.dim_macrotema VALUES (-1, 'Sem tema', NULL, 0, 0);

-- Topicos (-1 = "Sem tema").
INSERT INTO dw.dim_topico (id_topico, topico, palavras_chave, id_macrotema, revisao, n_titulos_estrito)
SELECT t.id_topico, t.rotulo,
       (SELECT string_agg(e ->> 0, '; ' ORDER BY ord) FROM jsonb_array_elements(t.palavras) WITH ORDINALITY x(e, ord)),
       COALESCE(t.id_macrotema, -1), t.revisao, t.n_titulos
FROM ml.topico t
WHERE t.id_topico <> -1;
INSERT INTO dw.dim_topico VALUES (-1, 'Sem tema', NULL, -1, NULL, 0);

-- Fato.
INSERT INTO dw.fato_pesquisador_topico
    (id_pesquisador, id_tempo, id_tipo_producao, id_topico, qtd_producoes, qtd_topico_aproximado)
SELECT c.id_pesquisador, dt.id_tempo, dtp.id_tipo_producao, COALESCE(v.id_topico, -1),
       count(*), count(*) FILTER (WHERE v.topico_aproximado)
FROM ml.corpus_titulo c
JOIN ml.titulo_unico u ON u.titulo_chave = c.titulo_chave
JOIN ml.v_titulo_tema v ON v.id_titulo = u.id_titulo
JOIN dw.dim_tipo_producao dtp ON dtp.tipo_producao = c.tipo_producao
JOIN dw.dim_tempo dt ON COALESCE(dt.ano, -1) = COALESCE(c.ano, -1)
WHERE c.valido AND c.id_pesquisador IS NOT NULL
GROUP BY c.id_pesquisador, dt.id_tempo, dtp.id_tipo_producao, COALESCE(v.id_topico, -1);

-- n_titulos de "Sem tema" (titulos unicos sem topico final).
UPDATE dw.dim_topico SET n_titulos_estrito = (SELECT count(*) FROM ml.titulo_topico WHERE id_topico = -1)
WHERE id_topico = -1;
UPDATE dw.dim_macrotema SET n_titulos = (
    SELECT count(*) FROM ml.v_titulo_tema WHERE id_topico IS NULL OR id_topico = -1)
WHERE id_macrotema = -1;

CREATE INDEX ix_fato_pesq_topico_topico ON dw.fato_pesquisador_topico (id_topico);
CREATE INDEX ix_fato_pesq_topico_tempo ON dw.fato_pesquisador_topico (id_tempo);
CREATE INDEX ix_fato_pesq_topico_pesq ON dw.fato_pesquisador_topico (id_pesquisador);
CREATE INDEX ix_dim_topico_macro ON dw.dim_topico (id_macrotema);
ANALYZE dw.fato_pesquisador_topico; ANALYZE dw.dim_topico; ANALYZE dw.dim_macrotema;

-- Validacoes: qualquer divergencia aborta (e desfaz) a carga.
DO $$
DECLARE esperado BIGINT; obtido BIGINT; excesso BIGINT; sem_macro BIGINT;
BEGIN
    SELECT count(*) INTO esperado
    FROM ml.corpus_titulo c JOIN ml.titulo_unico u ON u.titulo_chave = c.titulo_chave
    WHERE c.valido AND c.id_pesquisador IS NOT NULL;
    SELECT COALESCE(sum(qtd_producoes), 0) INTO obtido FROM dw.fato_pesquisador_topico;
    IF obtido <> esperado THEN
        RAISE EXCEPTION 'Itens na fato (%) diferem dos itens validos do corpus (%): ha chaves de ano/tipo sem dimensao?', obtido, esperado;
    END IF;

    -- A fato de topicos nunca pode ter mais itens que a fato de producoes, no mesmo pesquisador/ano/tipo.
    SELECT count(*) INTO excesso FROM (
        SELECT f.id_pesquisador, f.id_tempo, f.id_tipo_producao
        FROM dw.fato_pesquisador_topico f
        GROUP BY 1, 2, 3
        HAVING sum(f.qtd_producoes) > COALESCE((
            SELECT p.qtd_producoes FROM dw.fato_pesquisador_producoes p
            WHERE p.id_pesquisador = f.id_pesquisador AND p.id_tempo = f.id_tempo
              AND p.id_tipo_producao = f.id_tipo_producao), 0)
    ) x;
    IF excesso > 0 THEN
        RAISE EXCEPTION '% combinacoes pesquisador/ano/tipo com mais itens em fato_pesquisador_topico que em fato_pesquisador_producoes.', excesso;
    END IF;

    SELECT count(*) INTO sem_macro FROM dw.dim_topico WHERE id_macrotema IS NULL;
    IF sem_macro > 0 THEN RAISE EXCEPTION '% topicos sem macrotema.', sem_macro; END IF;
END $$;

COMMIT;
