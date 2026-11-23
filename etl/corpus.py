"""Fase 8.1 - corpus de titulos para modelagem de topicos (BERTopic / LDA).

Le os titulos das 7 tabelas de producao da staging, limpa o texto, detecta o idioma por
heuristica de palavras funcionais e grava em ml.corpus_titulo, ligado ao dw (id_pesquisador, ano).
NAO altera stg nem dw. Uso:
    python -m etl.corpus --confirmar-banco dw_lattes [--recriar] [--limit N]
Variaveis: PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD.
"""
from __future__ import annotations

import argparse
import csv
import html
import re
import unicodedata
from pathlib import Path
from .db import parametros_conexao as _db_kwargs

# (tipo no dw, tabela da staging, coluna com o titulo, coluna com o idioma ou None)
FONTES = [
    ("Artigos", "artigos", "titulo", "idioma"),
    ("Livros", "livros", "titulo", None),
    ("Capitulos de livros", "capitulos_livros", "titulo_capitulo", "idioma"),
    ("Textos em jornais ou revistas", "textos_jornais", "titulo", "idioma"),
    ("Trabalhos em eventos", "trabalhos_eventos", "titulo", "idioma"),
    ("Apresentacoes de trabalho", "apresentacoes_trabalho", "titulo", "idioma"),
    ("Outras producoes", "outras_producoes", "titulo", "idioma"),
]
MIN_PALAVRAS = 3  # abaixo disso o titulo e marcado como invalido ("curto")

_CTRL = re.compile(r"[\u0000-\u0008\u000b-\u001f\u007f-\u009f​-‏ -‮﻿]")
_ESPACOS = re.compile(r"\s+")
_ENTIDADE = re.compile(r"&(#\d+|#x[0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]+);")
_PALAVRA = re.compile(r"[^\W\d_]{2,}", re.UNICODE)  # >= 2 letras, sem digitos


def limpar_titulo(texto: str | None) -> str:
    """Resolve entidades HTML (inclui o '&#10;' literal), remove controles e colapsa espacos."""
    if not texto:
        return ""
    for _ in range(2):  # cobre '&amp;#10;'
        if not _ENTIDADE.search(texto):
            break
        texto = html.unescape(texto)
    texto = unicodedata.normalize("NFC", texto)
    texto = _CTRL.sub(" ", texto)
    return _ESPACOS.sub(" ", texto).strip()


def chave_titulo(texto: str) -> str:
    """Forma normalizada (sem acento, minusculas, so alfanumericos) para detectar duplicatas."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return _ESPACOS.sub(" ", re.sub(r"[^0-9a-z]+", " ", sem_acento.casefold())).strip()


def contar_palavras(texto: str) -> int:
    return len(_PALAVRA.findall(texto))


_PT = {"da", "do", "das", "dos", "no", "na", "nos", "nas", "uma", "um", "uns", "umas", "os", "as", "ao", "aos",
       "pelo", "pela", "pelos", "pelas", "não", "são", "seu", "sua", "seus", "suas", "ou", "com", "para", "em",
       "de", "sobre", "entre", "como", "que", "à", "às", "é", "numa", "num", "através", "após", "sem", "também"}
_EN = {"the", "of", "and", "in", "on", "for", "with", "to", "an", "from", "by", "at", "as", "is", "are", "using",
       "between", "its", "their", "into", "through", "or", "its", "under", "towards", "toward", "based", "case",
       "study", "analysis", "approach", "after", "during", "about", "over", "this", "that", "new"}
_ES = {"el", "la", "los", "las", "del", "y", "en", "con", "por", "para", "una", "un", "sobre", "entre", "como",
       "su", "sus", "al", "que", "se", "desde", "hacia", "mediante", "una", "unos", "unas", "más"}


def detectar_idioma(texto: str) -> str:
    """pt / en / es / indeterminado, por palavras funcionais e letras caracteristicas.
    Heuristica simples e explicavel; titulos curtos tendem a 'indeterminado'."""
    toks = re.findall(r"[^\W\d_]+", texto.casefold(), re.UNICODE)
    if not toks:
        return "indeterminado"
    pt = sum(t in _PT for t in toks) + 2 * bool(re.search(r"[ãõç]", texto.casefold()))
    en = sum(t in _EN for t in toks)
    es = sum(t in _ES for t in toks) + 2 * bool(re.search(r"[ñ¿¡]", texto.casefold()))
    # 'de', 'para', 'por', 'sobre', 'entre', 'como', 'que', 'com/con' sao comuns a pt e es:
    # nesses casos o desempate vem dos marcadores acima.
    placar = sorted([(pt, "pt"), (en, "en"), (es, "es")], reverse=True)
    (s1, l1), (s2, _) = placar[0], placar[1]
    return l1 if s1 >= 1 and s1 > s2 else "indeterminado"


def preparar(titulo_bruto: str | None) -> dict:
    limpo = limpar_titulo(titulo_bruto)
    n = contar_palavras(limpo)
    motivo = "vazio" if not limpo else ("curto" if n < MIN_PALAVRAS else None)
    return {"titulo_limpo": limpo or None, "titulo_chave": chave_titulo(limpo) or None,
            "n_palavras": n, "idioma_detectado": detectar_idioma(limpo) if limpo else None,
            "valido": motivo is None, "motivo_invalido": motivo}


DDL = """
CREATE SCHEMA IF NOT EXISTS ml;
CREATE TABLE IF NOT EXISTS ml.corpus_titulo (
    id_corpus BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tipo_producao TEXT NOT NULL,
    origem_tabela TEXT NOT NULL,
    origem_id BIGINT NOT NULL,
    arquivo_id BIGINT NOT NULL,
    id_pesquisador INTEGER,
    ano INTEGER,
    titulo_original TEXT,
    titulo_limpo TEXT,
    titulo_chave TEXT,
    n_palavras INTEGER NOT NULL,
    idioma_lattes VARCHAR(50),
    idioma_detectado VARCHAR(15),
    valido BOOLEAN NOT NULL,
    motivo_invalido VARCHAR(10),
    CONSTRAINT uq_corpus_origem UNIQUE (origem_tabela, origem_id)
);
"""
COLUNAS = ("tipo_producao origem_tabela origem_id arquivo_id id_pesquisador ano titulo_original titulo_limpo "
           "titulo_chave n_palavras idioma_lattes idioma_detectado valido motivo_invalido").split()


def _consulta(tabela: str, col_titulo: str, col_idioma: str | None, limit: int | None) -> str:
    idioma = f"s.{col_idioma}" if col_idioma else "NULL::varchar"
    lim = f" LIMIT {int(limit)}" if limit else ""
    return f"""
        SELECT s.id, s.arquivo_id, dp.id_pesquisador,
               CASE WHEN s.ano ~ '^[0-9]{{4}}$' AND s.ano::int BETWEEN 1900 AND 2026 THEN s.ano::int END,
               s.{col_titulo}, {idioma}
        FROM stg.{tabela} s
        JOIN stg.curriculo_origem o ON o.arquivo_id = s.arquivo_id
        JOIN dw.dim_pesquisador dp ON dp.chave_pesquisador = o.chave_pesquisador
        ORDER BY s.id{lim}"""


def run(args: argparse.Namespace) -> int:
    import psycopg
    kw = _db_kwargs()
    # Duas conexoes: leitura (cursor de servidor) e escrita (COPY) nao podem dividir a mesma conexao.
    with psycopg.connect(**kw) as conn, psycopg.connect(**kw) as leitura:
        banco = conn.execute("select current_database()").fetchone()[0]
        if banco != args.confirmar_banco:
            raise RuntimeError(f"Banco conectado é {banco!r}, mas --confirmar-banco é {args.confirmar_banco!r}.")
        if not conn.execute("select to_regclass('dw.dim_pesquisador')").fetchone()[0]:
            raise RuntimeError("dw.dim_pesquisador não existe; carregue o dw antes (Fase 7).")
        if args.recriar:
            conn.execute("DROP TABLE IF EXISTS ml.corpus_titulo")
        conn.execute(DDL)
        if conn.execute("select exists(select 1 from ml.corpus_titulo)").fetchone()[0]:
            raise RuntimeError("ml.corpus_titulo já tem dados; use --recriar para refazer.")
        conn.commit()  # DDL confirmada; a carga abaixo e uma unica transacao
        total = 0
        for tipo, tab, col, col_idioma in FONTES:
            n_tab = 0
            with leitura.cursor(name=f"cur_{tab}") as cur, conn.cursor() as ins:
                cur.itersize = 20000
                cur.execute(_consulta(tab, col, col_idioma, args.limit))
                with ins.copy(f"COPY ml.corpus_titulo ({', '.join(COLUNAS)}) FROM STDIN") as cp:
                    for sid, arq, idp, ano, bruto, idi in cur:
                        p = preparar(bruto)
                        cp.write_row((tipo, tab, sid, arq, idp, ano, bruto, p["titulo_limpo"], p["titulo_chave"],
                                      p["n_palavras"], idi, p["idioma_detectado"], p["valido"], p["motivo_invalido"]))
                        n_tab += 1
            total += n_tab
            print(f"{tipo}: {n_tab} títulos", flush=True)
        conn.commit()
        print(f"Total: {total} títulos em ml.corpus_titulo")
        _relatorio(conn, Path(args.relatorio))
    return 0


def _relatorio(conn, pasta: Path) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    def salvar(nome, cols, rows):
        with open(pasta / nome, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f); w.writerow(cols); w.writerows(rows)
    q = lambda sql: conn.execute(sql).fetchall()
    por_tipo = q("""select tipo_producao, count(*), count(*) filter (where valido),
                    count(*) filter (where motivo_invalido='vazio'), count(*) filter (where motivo_invalido='curto'),
                    count(distinct titulo_chave) filter (where valido)
                    from ml.corpus_titulo group by 1 order by 2 desc""")
    salvar("fase8_corpus_por_tipo.csv", ["tipo", "total", "validos", "vazios", "curtos", "titulos_unicos_validos"], por_tipo)
    idiomas = q("""select idioma_detectado, count(*) from ml.corpus_titulo where valido group by 1 order by 2 desc""")
    salvar("fase8_corpus_idiomas.csv", ["idioma_detectado", "titulos_validos"], idiomas)
    conc = q("""select idioma_lattes, idioma_detectado, count(*) from ml.corpus_titulo
                where valido and idioma_lattes is not null group by 1,2 order by 3 desc limit 40""")
    salvar("fase8_corpus_idioma_lattes_vs_detectado.csv", ["idioma_lattes", "idioma_detectado", "n"], conc)
    print("\nPor tipo (total / válidos / vazios / curtos / únicos válidos):")
    for r in por_tipo: print("  ", r)
    print("Idiomas detectados (títulos válidos):", dict(idiomas))
    print("Relatórios em", pasta)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--confirmar-banco", required=True, help="Nome exato do banco (trava de segurança)")
    ap.add_argument("--recriar", action="store_true", help="Apaga e refaz ml.corpus_titulo")
    ap.add_argument("--limit", type=int, help="Limita títulos por tabela (teste)")
    ap.add_argument("--relatorio", default="reports")
    try:
        return run(ap.parse_args())
    except RuntimeError as e:
        print("FALHA:", e); return 1


if __name__ == "__main__":
    raise SystemExit(main())
