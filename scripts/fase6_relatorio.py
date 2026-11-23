"""Fase 6 - relatorio SOMENTE LEITURA da staging, antes de construir o dw.
Uso: python scripts/fase6_relatorio.py   (variaveis PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD)
Gera reports/fase6_*.csv e imprime um resumo. Nao altera o banco nem decide consolidacao."""
import csv, os
from pathlib import Path
import psycopg

OUT = Path("reports"); OUT.mkdir(exist_ok=True)
ANO = {  # tabela: coluna de ano
    "artigos": "ano", "livros": "ano", "capitulos_livros": "ano", "textos_jornais": "ano",
    "trabalhos_eventos": "ano_realizacao", "apresentacoes_trabalho": "ano", "outras_producoes": "ano",
}

def salvar(nome, cols, rows):
    with open(OUT / nome, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(cols); w.writerows(rows)

with psycopg.connect(host=os.environ.get("PGHOST", "localhost"), port=os.environ.get("PGPORT", "5432"),
                     dbname=os.environ["PGDATABASE"], user=os.environ["PGUSER"],
                     password=os.environ["PGPASSWORD"]) as c:
    q = lambda sql: c.execute(sql).fetchall()
    print("banco:", q("select current_database()")[0][0])

    tot, dist = q("select count(*), count(distinct chave_pesquisador) from stg.curriculo_origem")[0]
    print(f"arquivos={tot} | chaves distintas={dist} | excedente (arquivos repetidos de uma chave)={tot-dist}")

    sem_id = q("""select arquivo_id, caminho_relativo, chave_pesquisador from stg.curriculo_origem
                  where id_lattes_original is null or chave_pesquisador like 'ARQUIVO:%' order by 1""")
    salvar("fase6_sem_id_lattes.csv", ["arquivo_id", "caminho_relativo", "chave_pesquisador"], sem_id)
    print(f"arquivos sem ID Lattes (chave tecnica): {len(sem_id)}")

    ids = q("""select id_lattes_original, count(*) n, array_agg(caminho_relativo order by arquivo_id)
               from stg.curriculo_origem where id_lattes_original is not null
               group by 1 having count(*) > 1 order by n desc, 1""")
    salvar("fase6_id_lattes_repetido.csv", ["id_lattes", "arquivos", "caminhos"],
           [(a, b, " | ".join(cc)) for a, b, cc in ids])
    print(f"ID Lattes presente em mais de um arquivo: {len(ids)} IDs ({sum(r[1] for r in ids)} arquivos)")

    hs = q("""select hash_sha256, count(*) n, array_agg(caminho_relativo order by arquivo_id)
              from stg.curriculo_origem where hash_sha256 is not null
              group by 1 having count(*) > 1 order by n desc""")
    salvar("fase6_hash_repetido.csv", ["hash_sha256", "arquivos", "caminhos"],
           [(a, b, " | ".join(cc)) for a, b, cc in hs])
    print(f"conteudo identico (mesmo hash) em mais de um arquivo: {len(hs)} hashes ({sum(r[1] for r in hs)} arquivos)")

    nome = q("""select count(*) filter (where nome is null or nome = '') from stg.pesquisador""")[0][0]
    print(f"pesquisadores sem nome: {nome}")

    linhas = []
    for t, col in ANO.items():
        r = q(f"""select count(*) total,
                    count(*) filter (where {col} is null) nulos,
                    count(*) filter (where {col} !~ '^[0-9]{{4}}$') nao_ano,
                    count(*) filter (where {col} ~ '^[0-9]{{4}}$' and {col}::int not between 1900 and 2026) fora_faixa,
                    min(case when {col} ~ '^[0-9]{{4}}$' then {col}::int end),
                    max(case when {col} ~ '^[0-9]{{4}}$' then {col}::int end)
                  from stg.{t}""")[0]
        linhas.append((t, col) + r)
        print(f"ano {t}.{col}: total={r[0]} nulos={r[1]} formato_invalido={r[2]} fora_1900-2026={r[3]} min={r[4]} max={r[5]}")
    salvar("fase6_qualidade_ano.csv", ["tabela", "coluna", "total", "nulos", "formato_invalido", "fora_faixa", "min", "max"], linhas)

    for t, col in [("trabalhos_eventos", "pais_evento"), ("apresentacoes_trabalho", "pais"), ("outras_producoes", "pais_publicacao")]:
        r = q(f"select count(*), count(*) filter (where {col} is null or {col}=''), count(distinct {col}) from stg.{t}")[0]
        print(f"pais {t}.{col}: total={r[0]} vazios={r[1]} distintos={r[2]}")
print("relatorios em reports/fase6_*.csv")
