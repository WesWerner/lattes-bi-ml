-- 30_bi_views.sql - camada de BI: views agregadas para o Power BI (esquema bi).
-- Pre-requisito: dw completo (fases 7 e 8.4) e ml.corpus_titulo.
-- Idempotente: recria o esquema bi inteiro a cada execucao (DROP SCHEMA ... CASCADE so afeta o esquema bi).
--
-- PRIVACIDADE (LGPD): nenhuma view expõe nome, id_lattes, chave_pesquisador ou id_pesquisador.
-- Toda view que cruza dimensões traz qtd_pesquisadores (pesquisadores distintos) e OMITE as linhas
-- com menos de bi.k_minimo pesquisadores (padrao 5), para evitar a identificacao individual.
-- Consequencia: somar as linhas de uma view pode dar MENOS que o total real; os totais gerais estao
-- em bi.v_kpis_gerais (nivel agregado alto, sem corte).
BEGIN;

DROP SCHEMA IF EXISTS bi CASCADE;
CREATE SCHEMA bi;

-- Limite minimo de pesquisadores por linha (altere aqui e rode o script de novo).
CREATE FUNCTION bi.k_minimo() RETURNS integer LANGUAGE sql IMMUTABLE AS $$ SELECT 5 $$;

-- Normalizacao de pais: so unifica as grafias de Brasil. Ajuste a lista depois de rodar
-- sql/31_bi_diagnostico_paises.sql, se houver outras variacoes relevantes.
CREATE FUNCTION bi.pais_norm(p text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN p IS NULL OR btrim(p) = '' THEN NULL
        WHEN lower(translate(btrim(p), 'ÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç', 'AAAAEEIOOOUCaaaaeeiooouc'))
             IN ('brasil', 'brazil', 'br', 'bra', 'brasil.') THEN 'Brasil'
        ELSE btrim(p)
    END
$$;


-- Rotulos legiveis (no banco os nomes vem em MAIUSCULAS_COM_SUBLINHADO e sem acento).
-- As funcoes sao usadas em TODAS as views, entao os relacionamentos do Power BI continuam consistentes.
CREATE FUNCTION bi.rotulo_grande_area(g text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE upper(btrim(g))
        WHEN 'CIENCIAS_HUMANAS' THEN 'Ciências Humanas'
        WHEN 'CIENCIAS_SOCIAIS_APLICADAS' THEN 'Ciências Sociais Aplicadas'
        WHEN 'CIENCIAS_DA_SAUDE' THEN 'Ciências da Saúde'
        WHEN 'CIENCIAS_EXATAS_E_DA_TERRA' THEN 'Ciências Exatas e da Terra'
        WHEN 'CIENCIAS_BIOLOGICAS' THEN 'Ciências Biológicas'
        WHEN 'CIENCIAS_AGRARIAS' THEN 'Ciências Agrárias'
        WHEN 'ENGENHARIAS' THEN 'Engenharias'
        WHEN 'LINGUISTICA_LETRAS_E_ARTES' THEN 'Linguística, Letras e Artes'
        WHEN 'OUTROS' THEN 'Outros'
        ELSE initcap(replace(lower(btrim(g)), '_', ' '))
    END
$$;

CREATE FUNCTION bi.rotulo_area(a text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT initcap(replace(lower(btrim(a)), '_', ' '))
$$;

CREATE FUNCTION bi.rotulo_tipo(t text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE t
        WHEN 'Capitulos de livros' THEN 'Capítulos de livros'
        WHEN 'Apresentacoes de trabalho' THEN 'Apresentações de trabalho'
        WHEN 'Outras producoes' THEN 'Outras produções'
        ELSE t
    END
$$;

-- ---------- Dimensoes pequenas para filtros ----------
CREATE VIEW bi.d_tempo AS
SELECT id_tempo,
       ano,
       COALESCE(ano::text, 'Desconhecido') AS ano_rotulo,
       CASE WHEN ano IS NULL THEN 'Desconhecido' ELSE (ano / 10 * 10)::text || 's' END AS decada
FROM dw.dim_tempo;

CREATE VIEW bi.d_tipo_producao AS
SELECT id_tipo_producao, bi.rotulo_tipo(tipo_producao) AS tipo_producao FROM dw.dim_tipo_producao;

CREATE VIEW bi.d_grande_area AS
SELECT DISTINCT bi.rotulo_grande_area(grande_area) AS grande_area FROM dw.dim_area WHERE grande_area IS NOT NULL;

CREATE VIEW bi.d_macrotema AS
SELECT id_macrotema, macrotema, palavras_chave, n_topicos
FROM dw.dim_macrotema;

-- ---------- Indicadores (I1 a I4): volume e evolucao ----------
-- I1 e I2: producoes por ano e tipo.
CREATE VIEW bi.v_producao_ano_tipo AS
SELECT t.ano, COALESCE(t.ano::text, 'Desconhecido') AS ano_rotulo, bi.rotulo_tipo(tp.tipo_producao) AS tipo_producao,
       sum(f.qtd_producoes)::bigint AS qtd_producoes,
       count(DISTINCT f.id_pesquisador) AS qtd_pesquisadores
FROM dw.fato_pesquisador_producoes f
JOIN dw.dim_tempo t USING (id_tempo)
JOIN dw.dim_tipo_producao tp USING (id_tipo_producao)
GROUP BY t.ano, tp.tipo_producao
HAVING count(DISTINCT f.id_pesquisador) >= bi.k_minimo();

-- I3: pesquisadores com producao por ano (todos os tipos).
CREATE VIEW bi.v_pesquisadores_ano AS
SELECT t.ano, COALESCE(t.ano::text, 'Desconhecido') AS ano_rotulo,
       sum(f.qtd_producoes)::bigint AS qtd_producoes,
       count(DISTINCT f.id_pesquisador) AS qtd_pesquisadores
FROM dw.fato_pesquisador_producoes f
JOIN dw.dim_tempo t USING (id_tempo)
GROUP BY t.ano
HAVING count(DISTINCT f.id_pesquisador) >= bi.k_minimo();

-- I4: distribuicao de producoes por pesquisador (faixas, sem identificar ninguem).
CREATE VIEW bi.v_distribuicao_producao_pesquisador AS
WITH p AS (
    SELECT f.id_pesquisador, tp.tipo_producao, sum(f.qtd_producoes) AS q
    FROM dw.fato_pesquisador_producoes f
    JOIN dw.dim_tipo_producao tp USING (id_tipo_producao)
    GROUP BY f.id_pesquisador, tp.tipo_producao
), faixa AS (
    SELECT tipo_producao,
           CASE WHEN q = 1 THEN '1' WHEN q <= 5 THEN '2 a 5' WHEN q <= 10 THEN '6 a 10'
                WHEN q <= 20 THEN '11 a 20' WHEN q <= 50 THEN '21 a 50' ELSE 'Mais de 50' END AS faixa,
           CASE WHEN q = 1 THEN 1 WHEN q <= 5 THEN 2 WHEN q <= 10 THEN 3
                WHEN q <= 20 THEN 4 WHEN q <= 50 THEN 5 ELSE 6 END AS ordem_faixa,
           q
    FROM p
)
SELECT bi.rotulo_tipo(tipo_producao) AS tipo_producao, faixa, ordem_faixa, count(*) AS qtd_pesquisadores, sum(q)::bigint AS qtd_producoes
FROM faixa
GROUP BY tipo_producao, faixa, ordem_faixa
HAVING count(*) >= bi.k_minimo();

-- ---------- Indicadores (I5 a I7): perfil ----------
-- I5: pesquisadores por grande area e area.
CREATE VIEW bi.v_pesquisadores_area AS
SELECT bi.rotulo_grande_area(a.grande_area) AS grande_area, bi.rotulo_area(a.area) AS area, count(DISTINCT f.id_pesquisador) AS qtd_pesquisadores
FROM dw.fato_pesquisador_area_atuacao f
JOIN dw.dim_area a USING (id_area)
GROUP BY a.grande_area, a.area
HAVING count(DISTINCT f.id_pesquisador) >= bi.k_minimo();

-- I6: producoes por grande area e ano (a soma entre areas excede o total: um pesquisador pode ter varias areas).
CREATE VIEW bi.v_producao_grande_area_ano AS
WITH pa AS (
    SELECT DISTINCT f.id_pesquisador, a.grande_area
    FROM dw.fato_pesquisador_area_atuacao f
    JOIN dw.dim_area a USING (id_area)
    WHERE a.grande_area IS NOT NULL
)
SELECT bi.rotulo_grande_area(pa.grande_area) AS grande_area, t.ano, COALESCE(t.ano::text, 'Desconhecido') AS ano_rotulo,
       sum(p.qtd_producoes)::bigint AS qtd_producoes,
       count(DISTINCT p.id_pesquisador) AS qtd_pesquisadores
FROM pa
JOIN dw.fato_pesquisador_producoes p ON p.id_pesquisador = pa.id_pesquisador
JOIN dw.dim_tempo t ON t.id_tempo = p.id_tempo
GROUP BY pa.grande_area, t.ano
HAVING count(DISTINCT p.id_pesquisador) >= bi.k_minimo();

-- I7: principais linhas de pesquisa (forma normalizada; exibe a variante mais frequente).
CREATE VIEW bi.v_linhas_pesquisa AS
SELECT l.linha_pesquisa, count(DISTINCT f.id_pesquisador) AS qtd_pesquisadores
FROM dw.fato_pesquisador_linha_pesquisa f
JOIN dw.dim_linha_pesquisa l USING (id_linha_pesquisa)
GROUP BY l.id_linha_pesquisa, l.linha_pesquisa
HAVING count(DISTINCT f.id_pesquisador) >= bi.k_minimo();

-- ---------- Indicadores (I8 a I13): temas ----------
-- I8, I9 e I11: macrotema x ano x tipo (inclui "Sem tema").
CREATE VIEW bi.v_macrotema_ano_tipo AS
SELECT m.macrotema, t.ano, COALESCE(t.ano::text, 'Desconhecido') AS ano_rotulo, bi.rotulo_tipo(tp.tipo_producao) AS tipo_producao,
       sum(f.qtd_producoes)::bigint AS qtd_producoes,
       sum(f.qtd_topico_aproximado)::bigint AS qtd_topico_aproximado,
       count(DISTINCT f.id_pesquisador) AS qtd_pesquisadores
FROM dw.fato_pesquisador_topico f
JOIN dw.dim_topico tpc USING (id_topico)
JOIN dw.dim_macrotema m ON m.id_macrotema = tpc.id_macrotema
JOIN dw.dim_tempo t USING (id_tempo)
JOIN dw.dim_tipo_producao tp USING (id_tipo_producao)
GROUP BY m.macrotema, t.ano, tp.tipo_producao
HAVING count(DISTINCT f.id_pesquisador) >= bi.k_minimo();

-- I10: topicos (com macrotema, palavras-chave e marca de revisao).
CREATE VIEW bi.v_topicos AS
SELECT tpc.id_topico, tpc.topico, m.macrotema, tpc.palavras_chave,
       (tpc.revisao IS NOT NULL) AS marcado_revisao,
       sum(f.qtd_producoes)::bigint AS qtd_producoes,
       sum(f.qtd_topico_aproximado)::bigint AS qtd_topico_aproximado,
       count(DISTINCT f.id_pesquisador) AS qtd_pesquisadores
FROM dw.fato_pesquisador_topico f
JOIN dw.dim_topico tpc USING (id_topico)
JOIN dw.dim_macrotema m ON m.id_macrotema = tpc.id_macrotema
WHERE tpc.id_topico <> -1
GROUP BY tpc.id_topico, tpc.topico, m.macrotema, tpc.palavras_chave, tpc.revisao
HAVING count(DISTINCT f.id_pesquisador) >= bi.k_minimo();

-- I12: perfil tematico por grande area.
CREATE VIEW bi.v_macrotema_grande_area AS
WITH pa AS (
    SELECT DISTINCT f.id_pesquisador, a.grande_area
    FROM dw.fato_pesquisador_area_atuacao f
    JOIN dw.dim_area a USING (id_area)
    WHERE a.grande_area IS NOT NULL
)
SELECT bi.rotulo_grande_area(pa.grande_area) AS grande_area, m.macrotema,
       sum(f.qtd_producoes)::bigint AS qtd_producoes,
       count(DISTINCT f.id_pesquisador) AS qtd_pesquisadores
FROM pa
JOIN dw.fato_pesquisador_topico f ON f.id_pesquisador = pa.id_pesquisador
JOIN dw.dim_topico tpc USING (id_topico)
JOIN dw.dim_macrotema m ON m.id_macrotema = tpc.id_macrotema
GROUP BY pa.grande_area, m.macrotema
HAVING count(DISTINCT f.id_pesquisador) >= bi.k_minimo();

-- I13: qualidade da classificacao tematica (por tipo e ano).
CREATE VIEW bi.v_qualidade_classificacao AS
SELECT bi.rotulo_tipo(tp.tipo_producao) AS tipo_producao, t.ano, COALESCE(t.ano::text, 'Desconhecido') AS ano_rotulo,
       sum(f.qtd_producoes)::bigint AS qtd_producoes,
       sum(f.qtd_topico_aproximado)::bigint AS qtd_topico_aproximado,
       sum(f.qtd_producoes) FILTER (WHERE f.id_topico = -1)::bigint AS qtd_sem_tema,
       count(DISTINCT f.id_pesquisador) AS qtd_pesquisadores
FROM dw.fato_pesquisador_topico f
JOIN dw.dim_tipo_producao tp USING (id_tipo_producao)
JOIN dw.dim_tempo t USING (id_tempo)
GROUP BY tp.tipo_producao, t.ano
HAVING count(DISTINCT f.id_pesquisador) >= bi.k_minimo();

-- ---------- Indicadores (I14 e I15): internacionalizacao e obras distintas ----------
-- I14: producoes por pais, ano e tipo (so trabalhos em eventos, apresentacoes e outras producoes).
-- pais NULL (so ha instituicao) vira 'Nao informado' e fica fora de "fora do Brasil".
CREATE VIEW bi.v_pais_ano_tipo AS
SELECT COALESCE(bi.pais_norm(l.pais), 'Não informado') AS pais,
       (bi.pais_norm(l.pais) IS NOT NULL AND bi.pais_norm(l.pais) <> 'Brasil') AS fora_do_brasil,
       t.ano, COALESCE(t.ano::text, 'Desconhecido') AS ano_rotulo, bi.rotulo_tipo(tp.tipo_producao) AS tipo_producao,
       sum(f.qtd_producoes)::bigint AS qtd_producoes,
       count(DISTINCT f.id_pesquisador) AS qtd_pesquisadores
FROM dw.fato_pesquisador_producao_localizacao f
JOIN dw.dim_localizacao_trabalhos l USING (id_localizacao_trabalhos)
JOIN dw.dim_tempo t USING (id_tempo)
JOIN dw.dim_tipo_producao tp USING (id_tipo_producao)
GROUP BY COALESCE(bi.pais_norm(l.pais), 'Não informado'),
         (bi.pais_norm(l.pais) IS NOT NULL AND bi.pais_norm(l.pais) <> 'Brasil'),
         t.ano, tp.tipo_producao
HAVING count(DISTINCT f.id_pesquisador) >= bi.k_minimo();

-- I15: obras distintas (titulo + ano) e razao de coautoria, so titulos validos do corpus.
CREATE VIEW bi.v_obras_distintas AS
SELECT c.ano, COALESCE(c.ano::text, 'Desconhecido') AS ano_rotulo, bi.rotulo_tipo(c.tipo_producao) AS tipo_producao,
       count(*) AS qtd_itens,
       count(DISTINCT c.titulo_chave) AS qtd_obras_distintas,
       round(count(*)::numeric / NULLIF(count(DISTINCT c.titulo_chave), 0), 3) AS razao_itens_obras,
       count(DISTINCT c.id_pesquisador) AS qtd_pesquisadores
FROM ml.corpus_titulo c
WHERE c.valido AND c.titulo_chave IS NOT NULL AND c.id_pesquisador IS NOT NULL
GROUP BY c.ano, c.tipo_producao
HAVING count(DISTINCT c.id_pesquisador) >= bi.k_minimo();

-- ---------- Indicadores gerais (cartoes) ----------
CREATE VIEW bi.v_kpis_gerais AS
SELECT
    (SELECT sum(qtd_producoes) FROM dw.fato_pesquisador_producoes)::bigint            AS total_producoes,
    (SELECT count(DISTINCT id_pesquisador) FROM dw.fato_pesquisador_producoes)        AS pesquisadores_com_producao,
    (SELECT count(*) FROM dw.dim_pesquisador)                                         AS curriculos,
    (SELECT min(ano) FROM dw.dim_tempo)                                               AS ano_minimo,
    (SELECT max(ano) FROM dw.dim_tempo)                                               AS ano_maximo,
    (SELECT count(*) FROM dw.dim_topico WHERE id_topico <> -1)                        AS topicos,
    (SELECT count(*) FROM dw.dim_macrotema WHERE id_macrotema <> -1)                  AS macrotemas,
    (SELECT sum(qtd_producoes) FROM dw.fato_pesquisador_topico)::bigint               AS itens_tematicos,
    (SELECT sum(qtd_topico_aproximado) FROM dw.fato_pesquisador_topico)::bigint       AS itens_topico_aproximado,
    (SELECT sum(qtd_producoes) FROM dw.fato_pesquisador_topico WHERE id_topico = -1)::bigint AS itens_sem_tema;

-- ---------- Papel somente leitura para o Power BI ----------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bi_leitor') THEN
        CREATE ROLE bi_leitor NOLOGIN;
    END IF;
END $$;
REVOKE ALL ON SCHEMA bi FROM PUBLIC;
GRANT USAGE ON SCHEMA bi TO bi_leitor;
GRANT SELECT ON ALL TABLES IN SCHEMA bi TO bi_leitor;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA bi TO bi_leitor;

COMMIT;
