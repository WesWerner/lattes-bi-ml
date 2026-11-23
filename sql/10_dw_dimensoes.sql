-- 10_dw_dimensoes.sql - carga das dimensoes do dw a partir da staging (INSERT ... SELECT, sem COPY).
-- Pre-requisito: sql/02_dw.sql aplicado e dimensoes VAZIAS. Depois: sql/03_dw_constraints.sql.
-- NAO carrega dim_localizacao_trabalhos (aguarda decisao de quais colunas representam "instituicao").
-- Regra de ano: ano valido = 4 digitos entre 1900 e 2026; qualquer outro valor (nulo, formato
-- invalido, fora da faixa) vai para uma unica linha de dim_tempo com ano NULL ("desconhecido").
BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM dw.dim_tempo) OR EXISTS (SELECT 1 FROM dw.dim_tipo_producao)
       OR EXISTS (SELECT 1 FROM dw.dim_pesquisador) OR EXISTS (SELECT 1 FROM dw.dim_area)
       OR EXISTS (SELECT 1 FROM dw.dim_linha_pesquisa) THEN
        RAISE EXCEPTION 'Dimensoes ja possuem dados; esta carga so roda em dimensoes vazias.';
    END IF;
    IF EXISTS (SELECT 1 FROM stg.curriculo_origem WHERE status_processamento <> 'PROCESSADO') THEN
        RAISE EXCEPTION 'Ha arquivos nao PROCESSADO na staging; resolva antes de carregar o dw.';
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

INSERT INTO dw.dim_tipo_producao (tipo_producao)
VALUES ('Artigos'), ('Livros'), ('Capitulos de livros'), ('Textos em jornais ou revistas'),
       ('Trabalhos em eventos'), ('Apresentacoes de trabalho'), ('Outras producoes');

INSERT INTO dw.dim_tempo (ano)
SELECT DISTINCT CASE WHEN ano ~ '^[0-9]{4}$' AND ano::int BETWEEN 1900 AND 2026 THEN ano::int END
FROM tmp_producao
UNION
SELECT NULL;  -- garante a linha "ano desconhecido" mesmo que nao haja casos

INSERT INTO dw.dim_pesquisador (id_lattes, chave_pesquisador, nome, atuacao_profissional)
SELECT p.id_lattes, o.chave_pesquisador, p.nome, p.atuacao_profissional
FROM stg.pesquisador p
JOIN stg.curriculo_origem o ON o.arquivo_id = p.arquivo_id
ORDER BY o.arquivo_id;

INSERT INTO dw.dim_area (grande_area, area)
SELECT DISTINCT nome_grande_area, nome_area
FROM stg.areas_atuacao
WHERE nome_area IS NOT NULL;

-- Normalizacao: minusculas, sem acentos, espacos colapsados. A forma exibida e a variante mais
-- frequente (espacos colapsados) entre as que tem a mesma forma normalizada.
INSERT INTO dw.dim_linha_pesquisa (linha_pesquisa, linha_pesquisa_normalizada)
SELECT mode() WITHIN GROUP (ORDER BY btrim(regexp_replace(linha_pesquisa, '\s+', ' ', 'g'))), n
FROM (
    SELECT linha_pesquisa,
           btrim(regexp_replace(translate(lower(linha_pesquisa),
                 'áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ', 'aaaaaeeeeiiiiooooouuuucaaaaaeeeeiiiiooooouuuuc'), '\s+', ' ', 'g')) AS n
    FROM stg.linha_pesquisador
    WHERE linha_pesquisa IS NOT NULL AND btrim(linha_pesquisa) <> ''
) x
GROUP BY n;

COMMIT;
