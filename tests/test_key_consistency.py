"""Validacao pos-carga: chaves de curriculo_origem e pesquisador devem coincidir.

Execute apos o ETL, com PGHOST/PGDATABASE/PGUSER/PGPASSWORD apontando para o banco
que contem os dados carregados. Este teste e somente leitura.
"""
import os
import psycopg
import pytest


def test_chaves_consistentes_por_arquivo():
    if not os.getenv("PGDATABASE"):
        pytest.skip("Teste de integração: defina PGDATABASE e as demais variáveis PG* para executá-lo.")
    kwargs = {
        "dbname": os.environ["PGDATABASE"],
        "user": os.getenv("PGUSER"),
        "password": os.getenv("PGPASSWORD"),
        "host": os.getenv("PGHOST", "localhost"),
    }
    if os.getenv("PGPORT"):
        kwargs["port"] = int(os.environ["PGPORT"])
    with psycopg.connect(**kwargs) as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT c.arquivo_id, c.caminho_relativo,
                   c.id_lattes_original, p.id_lattes,
                   c.chave_pesquisador, p.chave_pesquisador,
                   p.arquivo_id IS NULL AS pesquisador_ausente
            FROM stg.curriculo_origem AS c
            LEFT JOIN stg.pesquisador AS p ON p.arquivo_id = c.arquivo_id
            WHERE p.arquivo_id IS NULL
               OR c.id_lattes_original IS DISTINCT FROM p.id_lattes
               OR c.chave_pesquisador IS DISTINCT FROM p.chave_pesquisador
            ORDER BY c.arquivo_id
            LIMIT 100
        """)
        divergencias = cur.fetchall()
    assert not divergencias, (
        "Foram encontrados arquivos sem registro correspondente em stg.pesquisador "
        "ou com id_lattes/chave_pesquisador divergentes. Primeiras ocorrencias: "
        f"{divergencias}"
    )
