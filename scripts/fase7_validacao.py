"""Somente leitura. Compara o dw com a staging e confere integridade referencial.
Uso: python scripts\fase7_validacao.py   (variaveis PG*)"""
import os, sys
import psycopg

FAIL = []
def check(nome, obtido, esperado):
    ok = obtido == esperado
    print(("OK    " if ok else "FALHA ") + f"{nome}: dw={obtido} esperado={esperado}")
    if not ok: FAIL.append(nome)

NORM = ("btrim(regexp_replace(translate(lower({c}),'áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ',"
        "'aaaaaeeeeiiiiooooouuuucaaaaaeeeeiiiiooooouuuuc'),'\\s+',' ','g'))")
TIPOS = {"Artigos": "artigos", "Livros": "livros", "Capitulos de livros": "capitulos_livros",
         "Textos em jornais ou revistas": "textos_jornais", "Trabalhos em eventos": "trabalhos_eventos",
         "Apresentacoes de trabalho": "apresentacoes_trabalho", "Outras producoes": "outras_producoes"}

with psycopg.connect(host=os.environ.get("PGHOST", "localhost"), port=os.environ.get("PGPORT", "5432"),
                     dbname=os.environ["PGDATABASE"], user=os.environ["PGUSER"],
                     password=os.environ["PGPASSWORD"]) as c:
    one = lambda sql: c.execute(sql).fetchone()[0]
    print("banco:", one("select current_database()"))

    check("dim_pesquisador", one("select count(*) from dw.dim_pesquisador"), one("select count(*) from stg.pesquisador"))
    check("dim_pesquisador chaves distintas", one("select count(distinct chave_pesquisador) from dw.dim_pesquisador"),
          one("select count(*) from dw.dim_pesquisador"))
    check("dim_tipo_producao", one("select count(*) from dw.dim_tipo_producao"), 7)
    check("dim_area", one("select count(*) from dw.dim_area"),
          one("select count(*) from (select distinct nome_grande_area, nome_area from stg.areas_atuacao where nome_area is not null) x"))
    check("dim_linha_pesquisa", one("select count(*) from dw.dim_linha_pesquisa"),
          one("select count(distinct " + NORM.format(c="linha_pesquisa") + ") from stg.linha_pesquisador where btrim(coalesce(linha_pesquisa,''))<>''"))

    for tipo, tab in TIPOS.items():
        check(f"producoes '{tipo}'",
              one(f"select coalesce(sum(f.qtd_producoes),0) from dw.fato_pesquisador_producoes f "
                  f"join dw.dim_tipo_producao d using(id_tipo_producao) where d.tipo_producao='{tipo}'"),
              one(f"select count(*) from stg.{tab}"))
    check("producoes total", one("select sum(qtd_producoes) from dw.fato_pesquisador_producoes"),
          sum(one(f"select count(*) from stg.{t}") for t in TIPOS.values()))

    loc = {"Trabalhos em eventos": ("trabalhos_eventos", "nome_evento", "pais_evento"),
           "Apresentacoes de trabalho": ("apresentacoes_trabalho", "instituicao_promotora", "pais"),
           "Outras producoes": ("outras_producoes", "editora", "pais_publicacao")}
    for tipo, (tab, i, p) in loc.items():
        check(f"localizacao '{tipo}'",
              one(f"select coalesce(sum(f.qtd_producoes),0) from dw.fato_pesquisador_producao_localizacao f "
                  f"join dw.dim_tipo_producao d using(id_tipo_producao) where d.tipo_producao='{tipo}'"),
              one(f"select count(*) from stg.{tab} where nullif(btrim({i}),'') is not null or nullif(btrim({p}),'') is not null"))

    check("presencas area", one("select count(*) from dw.fato_pesquisador_area_atuacao"),
          one("select count(*) from (select distinct o.chave_pesquisador, a.nome_grande_area, a.nome_area from stg.areas_atuacao a "
              "join stg.curriculo_origem o using(arquivo_id) where a.nome_area is not null) x"))
    check("presencas linha", one("select count(*) from dw.fato_pesquisador_linha_pesquisa"),
          one("select count(*) from (select distinct o.chave_pesquisador, " + NORM.format(c="l.linha_pesquisa") +
              " from stg.linha_pesquisador l join stg.curriculo_origem o using(arquivo_id) "
              "where btrim(coalesce(l.linha_pesquisa,''))<>'') x"))

    for fato, cols in {
        "fato_pesquisador_producoes": [("id_pesquisador", "dim_pesquisador"), ("id_tempo", "dim_tempo"), ("id_tipo_producao", "dim_tipo_producao")],
        "fato_pesquisador_area_atuacao": [("id_pesquisador", "dim_pesquisador"), ("id_area", "dim_area")],
        "fato_pesquisador_linha_pesquisa": [("id_pesquisador", "dim_pesquisador"), ("id_linha_pesquisa", "dim_linha_pesquisa")],
        "fato_pesquisador_producao_localizacao": [("id_pesquisador", "dim_pesquisador"), ("id_tempo", "dim_tempo"),
              ("id_tipo_producao", "dim_tipo_producao"), ("id_localizacao_trabalhos", "dim_localizacao_trabalhos")]}.items():
        for col, dim in cols:
            orf = one(f"select count(*) from dw.{fato} f left join dw.{dim} d using({col}) where f.{col} is null or d.{col} is null")
            check(f"orfaos {fato}.{col}", orf, 0)

    dup = one("select count(*) from (select id_pesquisador,id_tempo,id_tipo_producao from dw.fato_pesquisador_producoes "
              "group by 1,2,3 having count(*)>1) x")
    check("grao unico fato_producoes", dup, 0)
    print("anos desconhecidos (dim_tempo ano NULL) em fato_producoes:",
          one("select coalesce(sum(qtd_producoes),0) from dw.fato_pesquisador_producoes f join dw.dim_tempo t using(id_tempo) where t.ano is null"))

print("\nRESULTADO:", "TUDO CONFERE" if not FAIL else "FALHAS em: " + ", ".join(FAIL))
sys.exit(1 if FAIL else 0)
