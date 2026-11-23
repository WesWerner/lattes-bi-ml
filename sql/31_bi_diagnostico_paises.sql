-- 31_bi_diagnostico_paises.sql - lista os 60 paises mais frequentes (grafia original x normalizada)
-- para decidir se bi.pais_norm precisa de mais regras. So leitura; rode com o usuario dono do banco.
SELECT l.pais AS pais_original, bi.pais_norm(l.pais) AS pais_normalizado,
       sum(f.qtd_producoes) AS qtd_producoes
FROM dw.fato_pesquisador_producao_localizacao f
JOIN dw.dim_localizacao_trabalhos l USING (id_localizacao_trabalhos)
GROUP BY l.pais
ORDER BY sum(f.qtd_producoes) DESC
LIMIT 60;
