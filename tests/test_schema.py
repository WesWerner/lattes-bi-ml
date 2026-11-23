"""Testes do esquema aprovado. Requer pytest e psycopg (v3).

Configure PGHOST, PGPORT (opcional), PGDATABASE, PGUSER e PGPASSWORD para um banco
DESCARTAVEL vazio cujo nome contenha 'test' ou 'dev'. O teste executa os dois DDLs
aprovados duas vezes; nao faz DROP/TRUNCATE e falha se ja houver tabelas stg/dw.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[1]
STG_SQL = ROOT / "sql" / "01_stg.sql"
DW_SQL = ROOT / "sql" / "02_dw.sql"
MANIFEST = ROOT / "tests" / "expected_schema.json"


def _connection_kwargs():
    database = os.getenv("PGDATABASE", "")
    if not database or not any(token in database.lower() for token in ("test", "dev")):
        pytest.skip("Teste de integração: defina PGDATABASE apontando para um banco descartável com 'test' ou 'dev' no nome.")
    kwargs = {"dbname": database, "user": os.getenv("PGUSER"), "password": os.getenv("PGPASSWORD"), "host": os.getenv("PGHOST", "localhost")}
    if os.getenv("PGPORT"):
        kwargs["port"] = int(os.environ["PGPORT"])
    return kwargs


def test_ddl_idempotencia_e_colunas():
    expected = json.loads(MANIFEST.read_text(encoding="utf-8"))
    with psycopg.connect(**_connection_kwargs(), autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_schema IN ('stg', 'dw') AND table_type = 'BASE TABLE'
                ORDER BY table_schema, table_name
            """)
            existing = cur.fetchall()
            assert not existing, (
                "O banco de teste nao esta vazio nos schemas stg/dw; use um banco descartavel novo. "
                f"Tabelas encontradas: {existing}"
            )
            for _ in range(2):
                cur.execute(STG_SQL.read_text(encoding="utf-8"))
                cur.execute(DW_SQL.read_text(encoding="utf-8"))

            cur.execute("""
                SELECT table_schema || '.' || table_name, column_name
                FROM information_schema.columns
                WHERE table_schema IN ('stg', 'dw')
                ORDER BY table_schema, table_name, ordinal_position
            """)
            actual_rows = cur.fetchall()
            actual = {}
            for table, column in actual_rows:
                actual.setdefault(table, []).append(column)
            assert actual == expected, (
                "Diferenca entre information_schema.columns e o manifesto do Apêndice A "
                "mais as extensoes aprovadas. Consulte o diff de chaves/colunas.\n"
                f"Tabelas faltando: {sorted(set(expected) - set(actual))}\n"
                f"Tabelas extras: {sorted(set(actual) - set(expected))}\n"
                f"Diferencas: { {t: (expected[t], actual[t]) for t in expected.keys() & actual.keys() if expected[t] != actual[t]} }"
            )
        conn.rollback()  # mantem o banco descartavel sem persistir a execucao de teste
