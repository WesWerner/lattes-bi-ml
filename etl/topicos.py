"""Fase 8.3 - modelagem de topicos com BERTopic sobre os embeddings dos titulos unicos.

Le ml.titulo_unico + data/embeddings, ajusta UMAP -> HDBSCAN -> c-TF-IDF e grava:
  ml.topico         (um registro por topico; id_topico = -1 e o grupo "sem tema" / ruido)
  ml.titulo_topico  (um registro por titulo unico)
e um CSV para revisao manual (palavras + titulos de exemplo). Ambiente: .venv-ml. Uso:
    python -m etl.topicos --confirmar-banco dw_lattes --amostra 30000 --dry-run   # teste rapido, nao grava no banco
    python -m etl.topicos --confirmar-banco dw_lattes                             # modelo completo
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

from .db import parametros_conexao as _db_kwargs

# Palavras funcionais pt/en/es + palavras de baixa informacao em titulos academicos.
_FUNCIONAIS = """
a o as os um uma uns umas de da do das dos em no na nos nas ao aos à às e ou com sem para por pelo pela pelos pelas
sobre entre como que se seu sua seus suas num numa através após também não são é ser foi ao sob até desde contra
the of and in on for with to an from by at as is are its their into through or under towards toward after during
about over this that these those be been it a between using via
el la los las del y en con por una un sobre entre como su sus al que se desde hacia mediante más
"""
_RUIDO_TITULO = """
estudo estudos análise analises análises caso casos uso utilização abordagem proposta avaliação aplicação aplicações
perspectiva perspectivas relato relatos experiência experiências brasil brasileira brasileiro
study studies analysis case cases approach use based evaluation application applications proposal new
estudio estudios análisis caso casos enfoque
"""
# Palavras que dominavam rotulos sem distinguir temas (ensaio de 30 mil titulos): lugares e termos genericos.
# Afetam SO a descricao dos topicos (c-TF-IDF); o agrupamento vem dos embeddings e nao muda.
_RUIDO_LUGAR_GENERICO = """
espírito santo vitória brazil brazilian brazilians brasil brasileira brasileiras brasileiro brasileiros
universidade federal ufes município municípios estado região regiões diferentes durante efeito efeitos
effect effects revisão relação desenvolvimento produção trabalho trabalhos
"""
STOPWORDS = sorted(set((_FUNCIONAIS + " " + _RUIDO_TITULO + " " + _RUIDO_LUGAR_GENERICO).split()))

DDL = """
CREATE SCHEMA IF NOT EXISTS ml;
CREATE TABLE IF NOT EXISTS ml.topico (
    id_topico INTEGER PRIMARY KEY,
    rotulo TEXT NOT NULL,
    palavras JSONB NOT NULL,
    n_titulos INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS ml.titulo_topico (
    id_titulo INTEGER PRIMARY KEY REFERENCES ml.titulo_unico(id_titulo),
    id_topico INTEGER NOT NULL REFERENCES ml.topico(id_topico)
);
"""


def ajustar_topicos(textos: list[str], embeddings, *, min_cluster_size: int = 200, min_samples: int = 20,
                    n_neighbors: int = 15, n_components: int = 5, seed: int = 42, min_df: int = 1,
                    max_features: int | None = 150000,
                    nr_topicos: int | None = None, reduzir_outliers: bool = False, log=print):
    """Ajusta o BERTopic com embeddings pre-calculados. Retorna (modelo, lista de topicos por titulo)."""
    from bertopic import BERTopic
    from hdbscan import HDBSCAN
    from sklearn.feature_extraction.text import CountVectorizer
    from umap import UMAP

    umap_model = UMAP(n_neighbors=n_neighbors, n_components=n_components, min_dist=0.0,
                      metric="cosine", random_state=seed)
    hdb = HDBSCAN(min_cluster_size=min_cluster_size, min_samples=min_samples, metric="euclidean",
                  cluster_selection_method="eom", prediction_data=False)
    # ATENCAO: no BERTopic cada TOPICO e um "documento" do vetorizador; por isso min_df deve ser baixo
    # (min_df=10 exigiria a palavra em 10 topicos e eliminaria as palavras especificas de cada um).
    vec = CountVectorizer(stop_words=STOPWORDS, ngram_range=(1, 2), min_df=min_df, max_features=max_features,
                          token_pattern=r"(?u)\b[^\W\d_]{3,}\b")
    # language != "english" e essencial: com "english" o BERTopic apaga todo caractere fora do ASCII
    # antes de montar as palavras dos topicos ("educação" viraria "educao").
    modelo = BERTopic(language="multilingual", embedding_model=None, umap_model=umap_model, hdbscan_model=hdb, vectorizer_model=vec,
                      top_n_words=10, calculate_probabilities=False, nr_topics=nr_topicos, verbose=False)
    t0 = time.time()
    topicos, _ = modelo.fit_transform(textos, embeddings=embeddings)
    log(f"ajuste concluído em {(time.time() - t0) / 60:.1f} min")
    if reduzir_outliers and any(t == -1 for t in topicos):
        topicos = modelo.reduce_outliers(textos, topicos, strategy="embeddings", embeddings=embeddings)
        modelo.update_topics(textos, topics=topicos, vectorizer_model=vec)
    return modelo, list(topicos)


def rotulo_topico(palavras: list[str], n: int = 5) -> str:
    """Rotulo curto: as n primeiras palavras que nao repetem nenhum termo ja usado
    (evita 'educação física, física, educação'). Ex.: ['educação física','física','educação','futebol'] -> 'educação física, futebol'."""
    usados: set[str] = set()
    escolhidas: list[str] = []
    for p in palavras:
        termos = set(p.split())
        if termos & usados:
            continue
        escolhidas.append(p)
        usados |= termos
        if len(escolhidas) == n:
            break
    return ", ".join(escolhidas)


def resumo_topicos(modelo, topicos: list[int], textos: list[str], n_exemplos: int = 3) -> list[dict]:
    """Linhas para ml.topico e para o CSV de revisao manual."""
    from collections import Counter
    contagem = Counter(topicos)
    exemplos = modelo.get_representative_docs() or {}
    linhas = []
    for tid in sorted(contagem):
        palavras = modelo.get_topic(tid) or []
        pal = [[p, round(float(w), 5)] for p, w in palavras]
        rotulo = "sem tema (ruído)" if tid == -1 else rotulo_topico([p for p, _ in pal])
        linhas.append({"id_topico": tid, "rotulo": rotulo, "palavras": pal, "n_titulos": contagem[tid],
                       "exemplos": list(exemplos.get(tid, []))[:n_exemplos]})
    return linhas


def gravar(conn, ids: list[int], topicos: list[int], linhas: list[dict], recriar: bool) -> None:
    if recriar:
        conn.execute("DROP VIEW IF EXISTS ml.v_titulo_tema")  # criada pela Fase 8.5 (etl.macrotemas)
        conn.execute("DROP TABLE IF EXISTS ml.titulo_topico")
        conn.execute("DROP TABLE IF EXISTS ml.topico")
    conn.execute(DDL)
    if conn.execute("select exists(select 1 from ml.topico)").fetchone()[0]:
        raise RuntimeError("ml.topico já tem dados; use --recriar para refazer.")
    with conn.cursor() as cur:
        with cur.copy("COPY ml.topico (id_topico, rotulo, palavras, n_titulos) FROM STDIN") as cp:
            for l in linhas:
                cp.write_row((l["id_topico"], l["rotulo"], json.dumps(l["palavras"], ensure_ascii=False), l["n_titulos"]))
        with cur.copy("COPY ml.titulo_topico (id_titulo, id_topico) FROM STDIN") as cp:
            for i, t in zip(ids, topicos):
                cp.write_row((i, t))
    conn.commit()


def run(args: argparse.Namespace) -> int:
    import numpy as np
    import psycopg
    from etl.embeddings import carregar_embeddings
    with psycopg.connect(**_db_kwargs()) as conn:
        banco = conn.execute("select current_database()").fetchone()[0]
        if banco != args.confirmar_banco:
            raise RuntimeError(f"Banco conectado é {banco!r}, mas --confirmar-banco é {args.confirmar_banco!r}.")
        if not conn.execute("select to_regclass('ml.titulo_unico')").fetchone()[0]:
            raise RuntimeError("ml.titulo_unico não existe; rode a Fase 8.2 (python -m etl.embeddings).")
        linhas_db = conn.execute("select id_titulo, titulo_representante from ml.titulo_unico order by id_titulo").fetchall()
    ids = [r[0] for r in linhas_db]
    textos = [r[1] for r in linhas_db]
    emb = carregar_embeddings(Path(args.emb_dir))
    if emb.shape[0] != len(textos):
        raise RuntimeError(f"{emb.shape[0]} vetores para {len(textos)} títulos únicos; rode a Fase 8.2 até o fim.")
    if args.amostra:
        rng = np.random.default_rng(args.seed)
        sel = np.sort(rng.choice(len(textos), size=min(args.amostra, len(textos)), replace=False))
        ids, textos, emb = [ids[i] for i in sel], [textos[i] for i in sel], emb[sel]
        print(f"Amostra aleatória: {len(textos)} títulos")
    modelo, topicos = ajustar_topicos(
        textos, emb, min_cluster_size=args.min_cluster_size, min_samples=args.min_samples,
        n_neighbors=args.n_neighbors, n_components=args.n_components, seed=args.seed, min_df=args.min_df, max_features=args.max_features,
        nr_topicos=args.nr_topicos, reduzir_outliers=args.reduzir_outliers)
    linhas = resumo_topicos(modelo, topicos, textos)
    n_ruido = sum(1 for t in topicos if t == -1)
    print(f"{len([l for l in linhas if l['id_topico'] != -1])} tópicos | sem tema: {n_ruido} "
          f"({100 * n_ruido / len(topicos):.1f}%) de {len(topicos)} títulos")
    pasta = Path(args.relatorio); pasta.mkdir(parents=True, exist_ok=True)
    with open(pasta / "fase8_topicos.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["id_topico", "n_titulos", "rotulo", "palavras", "exemplo_1", "exemplo_2", "exemplo_3"])
        for l in sorted(linhas, key=lambda x: -x["n_titulos"]):
            ex = l["exemplos"] + [""] * 3
            w.writerow([l["id_topico"], l["n_titulos"], l["rotulo"], "; ".join(p for p, _ in l["palavras"]), *ex[:3]])
    (pasta / "fase8_topicos_parametros.json").write_text(json.dumps(
        {k: v for k, v in vars(args).items() if k not in ("confirmar_banco",)}, indent=2, default=str), encoding="utf-8")
    print("CSV para revisão manual:", pasta / "fase8_topicos.csv")
    if args.dry_run:
        print("--dry-run: nada gravado no banco.")
        return 0
    with psycopg.connect(**_db_kwargs()) as conn:
        gravar(conn, ids, topicos, linhas, args.recriar)
    print("Gravado em ml.topico e ml.titulo_topico.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--confirmar-banco", required=True)
    ap.add_argument("--emb-dir", default="data/embeddings")
    ap.add_argument("--min-cluster-size", type=int, default=200, help="Menor tamanho de um tópico (maior = menos tópicos)")
    ap.add_argument("--min-samples", type=int, default=20)
    ap.add_argument("--n-neighbors", type=int, default=15)
    ap.add_argument("--n-components", type=int, default=5)
    ap.add_argument("--min-df", type=int, default=1, help="Mínimo de TÓPICOS em que a palavra aparece (manter baixo)")
    ap.add_argument("--max-features", type=int, default=150000, help="Tamanho máximo do vocabulário")
    ap.add_argument("--nr-topicos", type=int, help="Reduz/une tópicos até este número (opcional)")
    ap.add_argument("--reduzir-outliers", action="store_true", help="Reatribui títulos 'sem tema' ao tópico mais próximo")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--amostra", type=int, help="Usa só N títulos aleatórios (teste)")
    ap.add_argument("--dry-run", action="store_true", help="Não grava no banco; só gera o CSV")
    ap.add_argument("--recriar", action="store_true", help="Refaz ml.topico e ml.titulo_topico")
    ap.add_argument("--relatorio", default="reports")
    try:
        return run(ap.parse_args())
    except RuntimeError as e:
        print("FALHA:", e); return 1


if __name__ == "__main__":
    raise SystemExit(main())
