-- 12_dw_localizacao.sql - dim_localizacao_trabalhos + fato_pesquisador_producao_localizacao.
-- Pre-requisitos: 10, 03 e 11 aplicados; dimensao e fato de localizacao VAZIAS.
-- Decisao de origem (instituicao, pais) por tipo de producao:
--   Trabalhos em eventos      -> nome_evento           , pais_evento
--   Apresentacoes de trabalho -> instituicao_promotora , pais
--   Outras producoes          -> editora               , pais_publicacao
-- Artigos, livros, capitulos e textos em jornais nao tem local na staging: ficam fora desta fato.
-- Texto: apenas btrim + espacos colapsados; vazio vira NULL. Maiusculas/minusculas NAO sao unificadas.
-- Linhas com instituicao E pais nulos nao entram. instituicao ampliada para 500 (volta ao Apendice A).
BEGIN;

ALTER TABLE dw.dim_localizacao_trabalhos ALTER COLUMN instituicao TYPE VARCHAR(500);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM dw.dim_localizacao_trabalhos)
       OR EXISTS (SELECT 1 FROM dw.fato_pesquisador_producao_localizacao) THEN
        RAISE EXCEPTION 'Localizacao ja possui dados; esta carga so roda com as tabelas vazias.';
    END IF;
END $$;

-- COALESCE em vez de IS NOT DISTINCT FROM permite hash join (a outra forma compara linha a linha)
CREATE TEMP TABLE tmp_local ON COMMIT DROP AS
SELECT arquivo_id, tipo, ano, NULLIF(btrim(regexp_replace(inst, '\s+', ' ', 'g')), '') AS instituicao,
       NULLIF(btrim(regexp_replace(pais, '\s+', ' ', 'g')), '') AS pais
FROM (
    SELECT arquivo_id, 'Trabalhos em eventos' AS tipo, ano, nome_evento AS inst, pais_evento AS pais FROM stg.trabalhos_eventos
    UNION ALL SELECT arquivo_id, 'Apresentacoes de trabalho', ano, instituicao_promotora, pais FROM stg.apresentacoes_trabalho
    UNION ALL SELECT arquivo_id, 'Outras producoes', ano, editora, pais_publicacao FROM stg.outras_producoes
) x;

ANALYZE tmp_local;

INSERT INTO dw.dim_localizacao_trabalhos (instituicao, pais)
SELECT DISTINCT instituicao, pais FROM tmp_local
WHERE instituicao IS NOT NULL OR pais IS NOT NULL;

ANALYZE dw.dim_localizacao_trabalhos;

INSERT INTO dw.fato_pesquisador_producao_localizacao
    (id_pesquisador, id_tempo, id_tipo_producao, id_localizacao_trabalhos, qtd_producoes)
SELECT dp.id_pesquisador, dt.id_tempo, dtp.id_tipo_producao, dl.id_localizacao_trabalhos, count(*)
FROM tmp_local t
JOIN stg.curriculo_origem o ON o.arquivo_id = t.arquivo_id
JOIN dw.dim_pesquisador dp ON dp.chave_pesquisador = o.chave_pesquisador
JOIN dw.dim_tipo_producao dtp ON dtp.tipo_producao = t.tipo
JOIN dw.dim_tempo dt ON dt.ano IS NOT DISTINCT FROM
     CASE WHEN t.ano ~ '^[0-9]{4}$' AND t.ano::int BETWEEN 1900 AND 2026 THEN t.ano::int END
JOIN dw.dim_localizacao_trabalhos dl ON COALESCE(dl.instituicao, '') = COALESCE(t.instituicao, '')
                                    AND COALESCE(dl.pais, '') = COALESCE(t.pais, '')
WHERE t.instituicao IS NOT NULL OR t.pais IS NOT NULL
GROUP BY dp.id_pesquisador, dt.id_tempo, dtp.id_tipo_producao, dl.id_localizacao_trabalhos;

COMMIT;
