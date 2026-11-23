-- Relatorio de pre-checagem de duplicatas. Somente leitura; nao consolida nem apaga dados.
-- Executar apos carregar stg.curriculo_origem e antes de decidir regras de consolidacao.

-- 1) IDs Lattes reais repetidos em mais de um arquivo.
SELECT id_lattes_original,
       COUNT(*) AS quantidade_arquivos,
       COUNT(DISTINCT hash_sha256) AS hashes_distintos,
       ARRAY_AGG(caminho_relativo ORDER BY caminho_relativo) AS arquivos
FROM stg.curriculo_origem
WHERE NULLIF(BTRIM(id_lattes_original), '') IS NOT NULL
GROUP BY id_lattes_original
HAVING COUNT(*) > 1
ORDER BY quantidade_arquivos DESC, id_lattes_original;

-- 2) Conteudo identico (hash SHA-256 repetido), sem inferir identidade de pessoa.
SELECT hash_sha256,
       COUNT(*) AS quantidade_arquivos,
       COUNT(DISTINCT id_lattes_original) AS ids_lattes_distintos,
       ARRAY_AGG(caminho_relativo ORDER BY caminho_relativo) AS arquivos
FROM stg.curriculo_origem
WHERE hash_sha256 IS NOT NULL
GROUP BY hash_sha256
HAVING COUNT(*) > 1
ORDER BY quantidade_arquivos DESC, hash_sha256;

-- 3) Arquivos sem ID Lattes ou com erro, para controle de cobertura.
SELECT status_processamento,
       COUNT(*) AS quantidade_arquivos,
       COUNT(*) FILTER (WHERE NULLIF(BTRIM(id_lattes_original), '') IS NULL) AS sem_id_lattes
FROM stg.curriculo_origem
GROUP BY status_processamento
ORDER BY status_processamento;
