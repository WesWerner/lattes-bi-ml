"""Executa um arquivo .sql no banco indicado pelas variaveis PG*. Uso:
   python scripts\rodar_sql.py sql\10_dw_dimensoes.sql [nome_do_banco_esperado]
Se o 2o argumento for informado, so executa se o banco conectado tiver exatamente esse nome."""
import os, sys
from pathlib import Path
import psycopg

sql = Path(sys.argv[1]).read_text(encoding="utf-8")
esperado = sys.argv[2] if len(sys.argv) > 2 else None
with psycopg.connect(host=os.environ.get("PGHOST", "localhost"), port=os.environ.get("PGPORT", "5432"),
                     dbname=os.environ["PGDATABASE"], user=os.environ["PGUSER"],
                     password=os.environ["PGPASSWORD"], autocommit=True) as c:
    banco = c.execute("select current_database()").fetchone()[0]
    print("banco:", banco)
    if esperado and banco != esperado:
        sys.exit(f"ABORTADO: banco conectado e {banco!r}, esperado {esperado!r}.")
    c.execute(sql)
    print("OK:", sys.argv[1])
