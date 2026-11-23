"""Parâmetros de conexão com o PostgreSQL, lidos de variáveis de ambiente.

Nenhuma credencial fica no código. Defina antes de executar:
PGDATABASE, PGUSER, PGPASSWORD (obrigatórias) e PGHOST, PGPORT (opcionais).
"""
from __future__ import annotations

import os

OBRIGATORIAS = ("PGDATABASE", "PGUSER", "PGPASSWORD")


def parametros_conexao() -> dict:
    """Devolve os argumentos para `psycopg.connect(**parametros_conexao())`."""
    faltam = [v for v in OBRIGATORIAS if not os.environ.get(v)]
    if faltam:
        raise RuntimeError("Configure as variáveis de ambiente: " + ", ".join(faltam))
    return dict(host=os.environ.get("PGHOST", "localhost"), port=os.environ.get("PGPORT", "5432"),
                dbname=os.environ["PGDATABASE"], user=os.environ["PGUSER"],
                password=os.environ["PGPASSWORD"])
