-- Fase 4: amplia as colunas de pagina de VARCHAR(10) para VARCHAR(50).
-- Motivo: a auditoria em 500 XMLs reais encontrou pagina_inicial com 23 caracteres (artigos) e 15 (trabalhos_eventos).
-- Nao destrutivo: so aumenta o limite, nao perde dados; pode ser executado mais de uma vez.
-- Aplicar UMA vez no banco dw_lattes ja criado (o 01_stg.sql atualizado cobre bancos novos).
ALTER TABLE stg.artigos           ALTER COLUMN pagina_inicial TYPE VARCHAR(50), ALTER COLUMN pagina_final TYPE VARCHAR(50);
ALTER TABLE stg.capitulos_livros  ALTER COLUMN pagina_inicial TYPE VARCHAR(50), ALTER COLUMN pagina_final TYPE VARCHAR(50);
ALTER TABLE stg.textos_jornais    ALTER COLUMN pagina_inicial TYPE VARCHAR(50), ALTER COLUMN pagina_final TYPE VARCHAR(50);
ALTER TABLE stg.trabalhos_eventos ALTER COLUMN pagina_inicial TYPE VARCHAR(50), ALTER COLUMN pagina_final TYPE VARCHAR(50);
