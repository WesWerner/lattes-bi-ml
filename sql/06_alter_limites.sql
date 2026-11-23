-- 06_alter_limites.sql
-- Migração aditiva e idempotente: amplia dois limites que os dados reais excedem.
-- Nunca trunca valores; apenas alarga as colunas (VARCHAR maior não perde dados).
--  * stg.outras_producoes.natureza: 100 -> 200 (volta ao previsto no Apêndice A)
--  * stg.artigos.volume:            20  -> 50  (dado real chegou a 22 caracteres)
-- Executar SOMENTE em dw_lattes_dev (conferir: SELECT current_database();)

ALTER TABLE stg.outras_producoes ALTER COLUMN natureza TYPE VARCHAR(200);
ALTER TABLE stg.artigos          ALTER COLUMN volume   TYPE VARCHAR(50);

SELECT table_name, column_name, character_maximum_length
FROM information_schema.columns
WHERE table_schema = 'stg'
  AND ((table_name = 'outras_producoes' AND column_name = 'natureza')
    OR (table_name = 'artigos'          AND column_name = 'volume'));
