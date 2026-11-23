"""Fase 8.5 - macrotemas e cobertura dos "sem tema", SEM reajustar o modelo.

Parte dos 273 topicos ja gravados (ml.topico / ml.titulo_topico) e dos embeddings:
  1. Macrotemas: agrupa os centroides dos topicos (hierarquico, cosseno) em K grupos -> ml.macrotema
     e ml.topico.id_macrotema. Os topicos continuam como subtemas.
  2. Cobertura: cada titulo "sem tema" (id_topico = -1) recebe o topico de centroide mais proximo,
     SO se a similaridade passar de um limiar calibrado com os titulos que ja tem topico
     (menor limiar em que o centroide mais proximo acerta o proprio topico em >= --precisao).
     O resultado fica em colunas separadas (id_topico_aprox, similaridade_aprox): a atribuicao
     estrita do BERTopic nao e alterada. A view ml.v_titulo_tema junta tudo.
Ambiente: .venv-ml. Uso:
    python -m etl.macrotemas --confirmar-banco dw_lattes [--k 30] [--precisao 0.8] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from etl.coerencia import TOKEN_RE, coerencia_cv, diversidade, tokenizar, unigramas_do_topico
from etl.topicos import STOPWORDS, rotulo_topico
from .db import parametros_conexao as _db_kwargs

DDL = """
CREATE TABLE IF NOT EXISTS ml.macrotema (
    id_macrotema INTEGER PRIMARY KEY,
    rotulo TEXT NOT NULL,
    palavras JSONB NOT NULL,
    n_topicos INTEGER NOT NULL,
    n_titulos INTEGER NOT NULL
);
ALTER TABLE ml.topico ADD COLUMN IF NOT EXISTS id_macrotema INTEGER;
ALTER TABLE ml.titulo_topico ADD COLUMN IF NOT EXISTS id_topico_aprox INTEGER;
ALTER TABLE ml.titulo_topico ADD COLUMN IF NOT EXISTS similaridade_aprox REAL;
"""

VIEW = """
CREATE OR REPLACE VIEW ml.v_titulo_tema AS
SELECT tt.id_titulo,
       tt.id_topico                                            AS id_topico_estrito,
       CASE WHEN tt.id_topico <> -1 THEN tt.id_topico
            ELSE tt.id_topico_aprox END                        AS id_topico,
       (tt.id_topico = -1 AND tt.id_topico_aprox IS NOT NULL)  AS topico_aproximado,
       tt.similaridade_aprox,
       t.id_macrotema
FROM ml.titulo_topico tt
LEFT JOIN ml.topico t
       ON t.id_topico = CASE WHEN tt.id_topico <> -1 THEN tt.id_topico ELSE tt.id_topico_aprox END;
"""


def _normalizar(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return m / n


def centroides(emb: np.ndarray, topicos: np.ndarray):
    """Centroide (media normalizada) de cada topico != -1. Retorna (ids_ordenados, matriz)."""
    ids = np.array(sorted(int(t) for t in np.unique(topicos) if t != -1))
    if len(ids) == 0:
        raise ValueError("nenhum tópico além de -1")
    mat = np.zeros((len(ids), emb.shape[1]), dtype=np.float32)
    for k, t in enumerate(ids):
        mat[k] = emb[topicos == t].mean(axis=0)
    return ids, _normalizar(mat)


def agrupar_macrotemas(cent: np.ndarray, k: int, ligacao: str = "average") -> np.ndarray:
    """Rotulos 0..k-1 para cada centroide (aglomerativo). 'average' usa distancia cosseno; 'ward' usa distancia
    euclidiana sobre vetores normalizados (equivale ao cosseno) e tende a formar grupos mais equilibrados."""
    from sklearn.cluster import AgglomerativeClustering
    if ligacao not in ("average", "ward"):
        raise ValueError("ligacao deve ser 'average' ou 'ward'")
    k = max(1, min(k, len(cent)))
    metric = "euclidean" if ligacao == "ward" else "cosine"
    return AgglomerativeClustering(n_clusters=k, metric=metric, linkage=ligacao).fit_predict(cent)


def mais_proximo(emb: np.ndarray, cent: np.ndarray, bloco: int = 20000):
    """Para cada linha de emb: indice do centroide mais proximo e a similaridade (cosseno)."""
    emb = _normalizar(emb.astype(np.float32))
    idx = np.empty(len(emb), dtype=np.int32)
    sim = np.empty(len(emb), dtype=np.float32)
    for i in range(0, len(emb), bloco):
        s = emb[i:i + bloco] @ cent.T
        idx[i:i + bloco] = s.argmax(axis=1)
        sim[i:i + bloco] = s.max(axis=1)
    return idx, sim


def calibrar_limiar(emb: np.ndarray, topicos: np.ndarray, ids_topico: np.ndarray, cent: np.ndarray, *,
                    precisao: float = 0.8, amostra: int = 60000, seed: int = 42):
    """Menor limiar de similaridade em que o centroide mais proximo acerta o topico real (>= precisao).
    Usa titulos que JA tem topico (vies otimista: sao pontos centrais; o limiar e um piso razoavel, nao garantia).
    Retorna (limiar, tabela [(limiar, precisao, cobertura)])."""
    com = np.where(topicos != -1)[0]
    rng = np.random.default_rng(seed)
    if len(com) > amostra:
        com = rng.choice(com, size=amostra, replace=False)
    idx, sim = mais_proximo(emb[com], cent)
    acerto = ids_topico[idx] == topicos[com]
    tabela = []
    limiar = None
    for lim in np.round(np.arange(0.30, 0.96, 0.02), 2):
        m = sim >= lim
        if m.sum() < 100:
            break
        p = float(acerto[m].mean())
        tabela.append((float(lim), round(p, 4), round(float(m.mean()), 4)))
        if limiar is None and p >= precisao:
            limiar = float(lim)
    if limiar is None:  # nunca atinge a precisao: usa o maior limiar avaliado
        limiar = tabela[-1][0] if tabela else 0.9
    return limiar, tabela


def similaridade_propria(emb: np.ndarray, topicos: np.ndarray, ids_topico: np.ndarray, cent: np.ndarray, *,
                         amostra: int = 60000, seed: int = 42) -> np.ndarray:
    """Similaridade (cosseno) de titulos JA classificados ao centroide do proprio topico (amostra)."""
    com = np.where(topicos != -1)[0]
    rng = np.random.default_rng(seed)
    if len(com) > amostra:
        com = rng.choice(com, size=amostra, replace=False)
    pos = {int(t): k for k, t in enumerate(ids_topico)}
    e = _normalizar(emb[com].astype(np.float32))
    return np.einsum("ij,ij->i", e, cent[[pos[int(t)] for t in topicos[com]]])


def rotular_macrotemas(textos: list[str], macro_por_titulo: np.ndarray, n_macro: int, *, top_n: int = 10):
    """Palavras de cada macrotema por c-TF-IDF (1-2 palavras) sobre os titulos com macrotema (-1 = ignorado)."""
    from sklearn.feature_extraction.text import CountVectorizer
    sel = np.where(macro_por_titulo >= 0)[0]
    docs = [[] for _ in range(n_macro)]
    for i in sel:
        docs[int(macro_por_titulo[i])].append(textos[i])
    vec = CountVectorizer(stop_words=STOPWORDS, token_pattern=TOKEN_RE.pattern, ngram_range=(1, 2),
                          max_features=150000, min_df=1)
    x = vec.fit_transform([" ".join(d) for d in docs]).astype(np.float64)
    tf = x.multiply(1.0 / np.maximum(x.sum(axis=1), 1)).tocsr()
    freq = np.asarray(x.sum(axis=0)).ravel()
    idf = np.log(1 + x.sum() / np.maximum(freq, 1))
    ctfidf = tf.multiply(idf).tocsr()
    vocab = vec.get_feature_names_out()
    saida = []
    for m in range(n_macro):
        linha = ctfidf.getrow(m).toarray().ravel()
        top = linha.argsort()[::-1][:top_n]
        saida.append([[str(vocab[j]), round(float(linha[j]), 5)] for j in top if linha[j] > 0])
    return saida


def run(args: argparse.Namespace) -> int:
    import psycopg
    from etl.embeddings import carregar_embeddings
    with psycopg.connect(**_db_kwargs()) as conn:
        banco = conn.execute("select current_database()").fetchone()[0]
        if banco != args.confirmar_banco:
            raise RuntimeError(f"Banco conectado é {banco!r}, mas --confirmar-banco é {args.confirmar_banco!r}.")
        for t in ("ml.topico", "ml.titulo_topico", "ml.titulo_unico"):
            if not conn.execute("select to_regclass(%s)", (t,)).fetchone()[0]:
                raise RuntimeError(f"{t} não existe; rode as fases 8.2 e 8.3 antes.")
        linhas = conn.execute("select id_titulo, titulo_representante from ml.titulo_unico order by id_titulo").fetchall()
        tt = dict(conn.execute("select id_titulo, id_topico from ml.titulo_topico").fetchall())
        rot_topico = dict(conn.execute("select id_topico, rotulo from ml.topico").fetchall())
    ids = [r[0] for r in linhas]
    textos = [r[1] for r in linhas]
    if len(tt) != len(ids):
        raise RuntimeError("ml.titulo_topico não cobre todos os títulos; refaça a Fase 8.3.")
    topicos = np.array([tt[i] for i in ids], dtype=np.int64)
    emb = carregar_embeddings(Path(args.emb_dir))
    if emb.shape[0] != len(ids):
        raise RuntimeError(f"{emb.shape[0]} vetores para {len(ids)} títulos.")

    ids_top, cent = centroides(emb, topicos)
    macro_cent = agrupar_macrotemas(cent, args.k, args.ligacao)
    n_macro = int(macro_cent.max()) + 1
    mapa = {int(t): int(m) for t, m in zip(ids_top, macro_cent)}
    macro_titulo = np.array([mapa.get(int(t), -1) for t in topicos], dtype=np.int64)
    palavras = rotular_macrotemas(textos, macro_titulo, n_macro)
    rotulos = [rotulo_topico([p for p, _ in pal]) or f"macrotema {m}" for m, pal in enumerate(palavras)]
    n_top = np.bincount(macro_cent, minlength=n_macro)
    n_tit = np.bincount(macro_titulo[macro_titulo >= 0], minlength=n_macro)
    print(f"{len(ids_top)} tópicos -> {n_macro} macrotemas (maior: {n_tit.max()} títulos, menor: {n_tit.min()})")

    limiar_prec, tabela = calibrar_limiar(emb, topicos, ids_top, cent, precisao=args.precisao, seed=args.seed)
    propria = similaridade_propria(emb, topicos, ids_top, cent, seed=args.seed)
    limiar_perc = float(np.percentile(propria, args.percentil))
    ruido = np.where(topicos == -1)[0]
    idx, sim = mais_proximo(emb[ruido], cent)
    q = [10, 25, 50, 75, 90]
    print("Similaridade ao centroide mais próximo - já classificados (própria): "
          + ", ".join(f"p{k}={np.percentile(propria, k):.2f}" for k in q))
    print("Similaridade ao centroide mais próximo - 'sem tema':                  "
          + ", ".join(f"p{k}={np.percentile(sim, k):.2f}" for k in q))
    if args.limiar is not None:
        limiar = args.limiar
    else:  # o mais exigente entre o critério de precisão e o percentil dos já classificados
        limiar = max(limiar_prec, limiar_perc)
    print(f"Limiar por precisão {limiar_prec:.2f} | por percentil p{args.percentil:g} dos classificados {limiar_perc:.2f} "
          f"-> usado {limiar:.2f}")
    aceitos = sim >= limiar
    cobertura_final = 100 * (1 - (len(ruido) - int(aceitos.sum())) / len(ids))
    print(f"Limiar de similaridade {limiar:.2f} (precisão alvo {args.precisao:.0%}): "
          f"{int(aceitos.sum())} de {len(ruido)} títulos sem tema ganham tópico aproximado; "
          f"cobertura total {cobertura_final:.1f}%")

    resumo = {"ligacao": args.ligacao, "k_macrotemas": n_macro, "n_topicos": int(len(ids_top)), "limiar": round(limiar, 3),
              "limiar_precisao": limiar_prec, "limiar_percentil": round(limiar_perc, 3), "percentil": args.percentil,
              "precisao_alvo": args.precisao, "sem_tema_estrito": int(len(ruido)),
              "recuperados": int(aceitos.sum()), "cobertura_total_pct": round(cobertura_final, 1)}
    if not args.sem_cv:
        stop = frozenset(STOPWORDS)
        docs = [tokenizar(t, stop) for t in textos]
        uni = [unigramas_do_topico([p for p, _ in pal], 10) for pal in palavras]
        cv = [c for c in coerencia_cv(uni, docs) if c == c]
        resumo.update({"macro_cv_medio": round(float(np.mean(cv)), 4), "macro_cv_mediano": round(float(np.median(cv)), 4),
                       "macro_diversidade": round(diversidade(uni), 4)})
    print("Resumo:", resumo)

    pasta = Path(args.relatorio); pasta.mkdir(parents=True, exist_ok=True)
    with open(pasta / "fase8_macrotemas.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id_macrotema", "n_topicos", "n_titulos", "rotulo", "palavras", "topicos_componentes"])
        for m in np.argsort(-n_tit):
            comp = [f"{t}:{rot_topico[int(t)]}" for t, mm in zip(ids_top, macro_cent) if mm == m]
            w.writerow([int(m), int(n_top[m]), int(n_tit[m]), rotulos[m], "; ".join(p for p, _ in palavras[m]), " | ".join(comp)])
    with open(pasta / "fase8_limiar_similaridade.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["limiar", "precisao", "cobertura_dos_ja_classificados"]); w.writerows(tabela)
    (pasta / "fase8_macrotemas_resumo.json").write_text(json.dumps(resumo, indent=2), encoding="utf-8")
    print("Relatórios em", pasta)
    if args.dry_run:
        print("--dry-run: nada gravado no banco.")
        return 0

    with psycopg.connect(**_db_kwargs()) as conn:
        conn.execute(DDL)
        conn.execute("TRUNCATE ml.macrotema")
        with conn.cursor() as cur:
            with cur.copy("COPY ml.macrotema (id_macrotema, rotulo, palavras, n_topicos, n_titulos) FROM STDIN") as cp:
                for m in range(n_macro):
                    cp.write_row((m, rotulos[m], json.dumps(palavras[m], ensure_ascii=False), int(n_top[m]), int(n_tit[m])))
            cur.execute("CREATE TEMP TABLE _tm (id_topico INT, id_macrotema INT) ON COMMIT DROP")
            with cur.copy("COPY _tm FROM STDIN") as cp:
                for t, m in mapa.items():
                    cp.write_row((t, m))
            cur.execute("UPDATE ml.topico t SET id_macrotema = m.id_macrotema FROM _tm m WHERE m.id_topico = t.id_topico")
            cur.execute("CREATE TEMP TABLE _ta (id_titulo INT, id_topico_aprox INT, sim REAL) ON COMMIT DROP")
            with cur.copy("COPY _ta FROM STDIN") as cp:
                for j, ok in zip(range(len(ruido)), aceitos):
                    if ok:
                        cp.write_row((ids[int(ruido[j])], int(ids_top[idx[j]]), float(sim[j])))
            cur.execute("UPDATE ml.titulo_topico SET id_topico_aprox = NULL, similaridade_aprox = NULL")
            cur.execute("UPDATE ml.titulo_topico tt SET id_topico_aprox = a.id_topico_aprox, similaridade_aprox = a.sim "
                        "FROM _ta a WHERE a.id_titulo = tt.id_titulo")
            cur.execute(VIEW)
        conn.commit()
    print("Gravado: ml.macrotema, ml.topico.id_macrotema, ml.titulo_topico.id_topico_aprox/similaridade_aprox, view ml.v_titulo_tema.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--confirmar-banco", required=True)
    ap.add_argument("--emb-dir", default="data/embeddings")
    ap.add_argument("--k", type=int, default=30, help="Número de macrotemas")
    ap.add_argument("--ligacao", choices=["average", "ward"], default="average",
                    help="Critério de agrupamento dos tópicos (ward costuma equilibrar melhor os tamanhos)")
    ap.add_argument("--precisao", type=float, default=0.8, help="Precisão mínima para aceitar o tópico aproximado")
    ap.add_argument("--percentil", type=float, default=25.0,
                    help="Limiar mínimo = este percentil da similaridade dos títulos já classificados ao próprio tópico")
    ap.add_argument("--limiar", type=float, help="Força o limiar de similaridade (ignora os critérios automáticos)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--sem-cv", action="store_true", help="Pula o cálculo de C_v dos macrotemas")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--relatorio", default="reports")
    try:
        return run(ap.parse_args())
    except (RuntimeError, ValueError) as e:
        print("FALHA:", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
