"""Resumo da integracao dos topicos ao dw (apos sql/21_dw_topicos.sql). Somente leitura. Uso:
   python scripts\fase8_resumo.py [banco_esperado]"""
import os, sys
import psycopg

esperado = sys.argv[1] if len(sys.argv) > 1 else None
with psycopg.connect(host=os.environ.get("PGHOST", "localhost"), port=os.environ.get("PGPORT", "5432"),
                     dbname=os.environ["PGDATABASE"], user=os.environ["PGUSER"], password=os.environ["PGPASSWORD"]) as c:
    banco = c.execute("select current_database()").fetchone()[0]
    print("banco:", banco)
    if esperado and banco != esperado:
        sys.exit(f"ABORTADO: banco conectado e {banco!r}, esperado {esperado!r}.")
    q = lambda sql: c.execute(sql).fetchall()
    n_macro, n_curado = q("select count(*) filter (where id_macrotema <> -1), "
                          "count(*) filter (where id_macrotema <> -1 and macrotema = r.rotulo_curado) "
                          "from dw.dim_macrotema d left join ml.macrotema r using (id_macrotema)")[0]
    print(f"macrotemas: {n_macro} | com nome curado aplicado: {n_curado}"
          + ("" if n_curado == n_macro else "  <-- rode sql\\20_macrotemas_rotulos.sql e depois sql\\21_dw_topicos.sql"))
    total, aprox, sem = q("select sum(qtd_producoes), sum(qtd_topico_aproximado), "
                          "coalesce(sum(qtd_producoes) filter (where id_topico = -1), 0) from dw.fato_pesquisador_topico")[0]
    print(f"itens na fato: {total} | com tópico aproximado: {aprox} ({100*aprox/total:.1f}%) | sem tema: {sem} ({100*sem/total:.1f}%)")
    pesq = q("select count(distinct id_pesquisador) from dw.fato_pesquisador_topico")[0][0]
    print(f"pesquisadores com ao menos um item classificado: {pesq}")
    print("\nItens por macrotema:")
    for nome, qtd in q("select m.macrotema, sum(f.qtd_producoes) from dw.fato_pesquisador_topico f "
                       "join dw.dim_topico t using (id_topico) join dw.dim_macrotema m on m.id_macrotema = t.id_macrotema "
                       "group by 1 order by 2 desc"):
        print(f"  {qtd:>8}  {nome}")
    print("\nItens por tipo de produção e % sem tema:")
    for tipo, qtd, pct in q("select p.tipo_producao, sum(f.qtd_producoes), "
                            "round(100.0*coalesce(sum(f.qtd_producoes) filter (where f.id_topico=-1), 0)/sum(f.qtd_producoes),1) "
                            "from dw.fato_pesquisador_topico f join dw.dim_tipo_producao p using (id_tipo_producao) "
                            "group by 1 order by 2 desc"):
        print(f"  {qtd:>8}  {pct:>5}% sem tema  {tipo}")
    print("\nTópicos marcados para revisão:")
    for i, t, r in q("select id_topico, topico, revisao from dw.dim_topico where revisao is not null order by 1"):
        print(f"  {i}: {t} -> {r}")
