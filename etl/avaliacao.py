"""Fase 8.4 - avaliacao dos topicos: coerencia C_v do BERTopic x linha de base LDA.

Le ml.topico (BERTopic) e os titulos de ml.titulo_unico; calcula C_v por topico (etl/coerencia.py);
ajusta um LDA (scikit-learn) com o mesmo numero de topicos e calcula o C_v dele sobre os mesmos documentos.
Gera reports/fase8_avaliacao_topicos.csv (por topico) e reports/fase8_avaliacao_resumo.csv. Uso:
    python -m etl.avaliacao --confirmar-banco dw_lattes [--pular-lda] [--k 150] [--lda-max-iter 10]
"""
from __future__ import annotations

import argparse
import csv
import statistics
import time
from pathlib import Path

from etl.coerencia import TOKEN_RE, coerencia_cv, diversidade, tokenizar, unigramas_do_topico
from etl.topicos import STOPWORDS
from .db import parametros_conexao as _db_kwargs


def lda_topicos(textos: list[str], k: int, *, max_iter: int = 10, seed: int = 42, max_features: int = 50000,
                min_df: int = 5, max_df: float = 0.5, top_n: int = 10, log=print) -> list[list[str]]:
    """Linha de base: LDA online (scikit-learn) sobre contagens de palavras. Retorna as top_n palavras de cada topico."""
    from sklearn.decomposition import LatentDirichletAllocation
    from sklearn.feature_extraction.text import CountVectorizer
    vec = CountVectorizer(stop_words=STOPWORDS, token_pattern=TOKEN_RE.pattern, min_df=min_df, max_df=max_df,
                          max_features=max_features)
    x = vec.fit_transform(textos)
    log(f"LDA: matriz {x.shape[0]} documentos x {x.shape[1]} palavras, K={k}")
    t0 = time.time()
    lda = LatentDirichletAllocation(n_components=k, learning_method="online", batch_size=4096,
                                    max_iter=max_iter, random_state=seed, n_jobs=-1)
    lda.fit(x)
    log(f"LDA ajustado em {(time.time() - t0) / 60:.1f} min")
    vocab = vec.get_feature_names_out()
    return [[vocab[i] for i in comp.argsort()[::-1][:top_n]] for comp in lda.components_]


def _resumo(nome: str, topicos: list[list[str]], cv: list[float], extra: dict | None = None) -> dict:
    validos = [c for c in cv if c == c]  # descarta nan
    r = {"modelo": nome, "n_topicos": len(topicos), "cv_medio": round(statistics.fmean(validos), 4),
         "cv_mediano": round(statistics.median(validos), 4), "cv_minimo": round(min(validos), 4),
         "diversidade": round(diversidade(topicos), 4)}
    r.update(extra or {})
    return r


def run(args: argparse.Namespace) -> int:
    import psycopg
    with psycopg.connect(**_db_kwargs()) as conn:
        banco = conn.execute("select current_database()").fetchone()[0]
        if banco != args.confirmar_banco:
            raise RuntimeError(f"Banco conectado é {banco!r}, mas --confirmar-banco é {args.confirmar_banco!r}.")
        for t in ("ml.topico", "ml.titulo_unico"):
            if not conn.execute("select to_regclass(%s)", (t,)).fetchone()[0]:
                raise RuntimeError(f"{t} não existe; rode as fases 8.2 e 8.3 antes.")
        textos = [r[0] for r in conn.execute("select titulo_representante from ml.titulo_unico order by id_titulo")]
        linhas = conn.execute("select id_topico, rotulo, palavras, n_titulos from ml.topico order by id_topico").fetchall()
    bert = [(i, rot, unigramas_do_topico([p[0] for p in pal], 10), n) for i, rot, pal, n in linhas if i != -1]
    n_ruido = next((n for i, _, _, n in linhas if i == -1), 0)
    if not bert:
        raise RuntimeError("ml.topico não tem tópicos além do grupo 'sem tema'.")
    print(f"{len(textos)} títulos únicos | {len(bert)} tópicos BERTopic | sem tema: {n_ruido}")
    stop = frozenset(STOPWORDS)
    docs = [tokenizar(t, stop) for t in textos]
    cv_bert = coerencia_cv([b[2] for b in bert], docs)
    resumos = [_resumo("BERTopic", [b[2] for b in bert], cv_bert,
                       {"titulos_sem_tema_pct": round(100 * n_ruido / len(textos), 1)})]
    por_topico = [("BERTopic", i, rot, round(c, 4), n, " ".join(w)) for (i, rot, w, n), c in zip(bert, cv_bert)]
    if not args.pular_lda:
        k = args.k or len(bert)
        lda = lda_topicos(textos, k, max_iter=args.lda_max_iter, seed=args.seed)
        cv_lda = coerencia_cv(lda, docs)
        resumos.append(_resumo("LDA", lda, cv_lda, {"titulos_sem_tema_pct": 0.0}))
        por_topico += [("LDA", i, ", ".join(w[:5]), round(c, 4), "", " ".join(w)) for i, (w, c) in enumerate(zip(lda, cv_lda))]
    pasta = Path(args.relatorio); pasta.mkdir(parents=True, exist_ok=True)
    with open(pasta / "fase8_avaliacao_topicos.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["modelo", "id_topico", "rotulo", "cv", "n_titulos", "palavras"]); w.writerows(por_topico)
    chaves = list(dict.fromkeys(k for r in resumos for k in r))
    with open(pasta / "fase8_avaliacao_resumo.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=chaves); w.writeheader(); w.writerows(resumos)
    print("\nResumo (C_v: quanto maior, mais coerente; diversidade: 1,0 = sem palavras repetidas entre tópicos):")
    for r in resumos:
        print("  ", r)
    print("Relatórios em", pasta)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--confirmar-banco", required=True)
    ap.add_argument("--pular-lda", action="store_true")
    ap.add_argument("--k", type=int, help="Nº de tópicos do LDA (padrão: o mesmo do BERTopic)")
    ap.add_argument("--lda-max-iter", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--relatorio", default="reports")
    try:
        return run(ap.parse_args())
    except RuntimeError as e:
        print("FALHA:", e); return 1


if __name__ == "__main__":
    raise SystemExit(main())
