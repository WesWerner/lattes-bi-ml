-- 32_bi_login.sql - cria o login somente leitura usado pelo Power BI (so enxerga o esquema bi).
-- ANTES DE RODAR: troque TROQUE_ESTA_SENHA por uma senha sua. Nao versione o arquivo com a senha.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bi_app') THEN
        CREATE ROLE bi_app LOGIN PASSWORD 'TROQUE_ESTA_SENHA' IN ROLE bi_leitor;
    END IF;
END $$;
