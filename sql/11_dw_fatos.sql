-- 11_dw_fatos.sql - carga das fatos (producoes, area de atuacao, linha de pesquisa).
-- Pre-requisito: 10_dw_dimensoes.sql e 03_dw_constraints.sql aplicados; fatos VAZIAS.
-- NAO carrega fato_pesquisador_producao_localizacao (depende de dim_localizacao_trabalhos).
-- Granularidade: producoes = pesquisador x ano x tipo (qtd = numero de itens);
-- area/linha = pesquisador x area/linha com presenca = 1 (sem duplicar).
BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM dw.fato_pesquisador_producoes)
       OR EXISTS (SELECT 1 FROM dw.fato_pesquisador_area_atuacao)
       OR EXISTS (SELECT 1 FROM dw.fato_pesquisador_linha_pesquisa) THEN
        RAISE EXCEPTION 'Fatos ja possuem dados; esta carga so roda em fatos vazias.';
    END IF;
END $$;

CREATE TEMP TABLE tmp_producao ON COMMIT DROP AS
SELECT arquivo_id, 'Artigos' AS tipo, ano FROM stg.artigos
UNION ALL SELECT arquivo_id, 'Livros', ano FROM stg.livros
UNION ALL SELECT arquivo_id, 'Capitulos de livros', ano FROM stg.capitulos_livros
UNION ALL SELECT arquivo_id, 'Textos em jornais ou revistas', ano FROM stg.textos_jornais
UNION ALL SELECT arquivo_id, 'Trabalhos em eventos', ano FROM stg.trabalhos_eventos
UNION ALL SELECT arquivo_id, 'Apresentacoes de trabalho', ano FROM stg.apresentacoes_trabalho
UNION ALL SELECT arquivo_id, 'Outras producoes', ano FROM stg.outras_producoes;

INSERT INTO dw.fato_pesquisador_producoes (id_pesquisador, id_tempo, id_tipo_producao, qtd_producoes)
SELECT dp.id_pesquisador, dt.id_tempo, dtp.id_tipo_producao, count(*)
FROM tmp_producao t
JOIN stg.curriculo_origem o ON o.arquivo_id = t.arquivo_id
JOIN dw.dim_pesquisador dp ON dp.chave_pesquisador = o.chave_pesquisador
JOIN dw.dim_tipo_producao dtp ON dtp.tipo_producao = t.tipo
JOIN dw.dim_tempo dt ON dt.ano IS NOT DISTINCT FROM
     CASE WHEN t.ano ~ '^[0-9]{4}$' AND t.ano::int BETWEEN 1900 AND 2026 THEN t.ano::int END
GROUP BY dp.id_pesquisador, dt.id_tempo, dtp.id_tipo_producao;

INSERT INTO dw.fato_pesquisador_area_atuacao (id_pesquisador, id_area, presenca)
SELECT DISTINCT dp.id_pesquisador, da.id_area, 1
FROM stg.areas_atuacao a
JOIN stg.curriculo_origem o ON o.arquivo_id = a.arquivo_id
JOIN dw.dim_pesquisador dp ON dp.chave_pesquisador = o.chave_pesquisador
JOIN dw.dim_area da ON da.area = a.nome_area AND da.grande_area IS NOT DISTINCT FROM a.nome_grande_area;

INSERT INTO dw.fato_pesquisador_linha_pesquisa (id_pesquisador, id_linha_pesquisa, presenca)
SELECT DISTINCT dp.id_pesquisador, dl.id_linha_pesquisa, 1
FROM stg.linha_pesquisador l
JOIN stg.curriculo_origem o ON o.arquivo_id = l.arquivo_id
JOIN dw.dim_pesquisador dp ON dp.chave_pesquisador = o.chave_pesquisador
JOIN dw.dim_linha_pesquisa dl ON dl.linha_pesquisa_normalizada =
     btrim(regexp_replace(translate(lower(l.linha_pesquisa),
           'áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ', 'aaaaaeeeeiiiiooooouuuucaaaaaeeeeiiiiooooouuuuc'), '\s+', ' ', 'g'))
WHERE l.linha_pesquisa IS NOT NULL AND btrim(l.linha_pesquisa) <> '';

COMMIT;
