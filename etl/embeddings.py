"""Fase 8.2 - embeddings dos titulos unicos (CPU), com medicao de velocidade e retomada por blocos.

1) Cria ml.titulo_unico (um registro por titulo_chave valido, ordenado por titulo_chave).
2) Gera os vetores com sentence-transformers e salva em blocos .npy (retomavel).
Ambiente: .venv-ml (sentence-transformers, psycopg). Uso:
    python -m etl.embeddings --confirmar-banco dw_lattes --benchmark 2000     (so mede a velocidade)
    python -m etl.embeddings --confirmar-banco dw_lattes                      (gera tudo; pode ser interrompido e retomado)
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from .db import parametros_conexao as _db_kwargs

MODELO_PADRAO = "paraphrase-multilingual-MiniLM-L12-v2"

DDL_UNICO = """
CREATE SCHEMA IF NOT EXISTS ml;
CREATE TABLE IF NOT EXISTS ml.titulo_unico (
    id_titulo INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    titulo_chave TEXT NOT NULL UNIQUE,
    titulo_representante TEXT NOT NULL,
    n_ocorrencias INTEGER NOT NULL
);
"""
# O representante e a variante mais frequente do titulo (empate: a menor em ordem alfabetica).
POPULAR_UNICO = """
INSERT INTO ml.titulo_unico (titulo_chave, titulo_representante, n_ocorrencias)
SELECT titulo_chave,
       mode() WITHIN GROUP (ORDER BY titulo_limpo),
       count(*)
FROM ml.corpus_titulo
WHERE valido AND titulo_chave IS NOT NULL
GROUP BY titulo_chave
ORDER BY titulo_chave
"""


def codificar_em_blocos(textos: list[str], encoder, pasta: Path, tamanho_bloco: int,
                        log=print) -> int:
    """Codifica `textos` em blocos salvos como bloco_00000.npy... Blocos ja existentes sao pulados
    (retomada). `encoder(lista_de_textos) -> ndarray (n, dim)`. Retorna quantos blocos foram gerados agora."""
    import numpy as np
    pasta.mkdir(parents=True, exist_ok=True)
    n = len(textos)
    blocos = range(0, n, tamanho_bloco)
    gerados, t0, feitos = 0, time.time(), 0
    for k, ini in enumerate(blocos):
        destino = pasta / f"bloco_{k:05d}.npy"
        fim = min(ini + tamanho_bloco, n)
        if destino.exists():
            log(f"bloco {k + 1}/{len(blocos)}: já existe, pulando")
            continue
        emb = np.asarray(encoder(textos[ini:fim]), dtype=np.float32)
        if emb.shape[0] != fim - ini:
            raise RuntimeError(f"bloco {k}: {emb.shape[0]} vetores para {fim - ini} textos")
        tmp = destino.with_suffix(".tmp.npy")
        np.save(tmp, emb)
        os.replace(tmp, destino)  # gravacao atomica: nunca fica bloco pela metade
        gerados += 1
        feitos += fim - ini
        dec = time.time() - t0
        restante = (n - fim) / (feitos / dec) if feitos else 0
        log(f"bloco {k + 1}/{len(blocos)} ok | {fim}/{n} títulos | {feitos / dec:.0f} títulos/s | "
            f"restam ~{restante / 60:.0f} min")
    return gerados


def carregar_embeddings(pasta: Path):
    """Concatena os blocos, na ordem de id_titulo (use na etapa de modelagem de temas)."""
    import numpy as np
    arqs = sorted(p for p in pasta.glob("bloco_*.npy") if not p.name.endswith(".tmp.npy"))
    if not arqs:
        raise FileNotFoundError(f"Nenhum bloco em {pasta}")
    return np.concatenate([np.load(a) for a in arqs])


def preparar_titulo_unico(conn, recriar: bool = False) -> int:
    if not conn.execute("select to_regclass('ml.corpus_titulo')").fetchone()[0]:
        raise RuntimeError("ml.corpus_titulo não existe; rode antes: python -m etl.corpus (Fase 8.1).")
    if recriar:
        conn.execute("DROP TABLE IF EXISTS ml.titulo_unico")
    conn.execute(DDL_UNICO)
    if not conn.execute("select exists(select 1 from ml.titulo_unico)").fetchone()[0]:
        conn.execute(POPULAR_UNICO)
    conn.commit()
    return conn.execute("select count(*) from ml.titulo_unico").fetchone()[0]


def run(args: argparse.Namespace) -> int:
    import psycopg
    with psycopg.connect(**_db_kwargs()) as conn:
        banco = conn.execute("select current_database()").fetchone()[0]
        if banco != args.confirmar_banco:
            raise RuntimeError(f"Banco conectado é {banco!r}, mas --confirmar-banco é {args.confirmar_banco!r}.")
        total = preparar_titulo_unico(conn, args.recriar)
        print(f"ml.titulo_unico: {total} títulos únicos")
        textos = [r[0] for r in conn.execute(
            "select titulo_representante from ml.titulo_unico order by id_titulo")]
    from sentence_transformers import SentenceTransformer
    import torch
    torch.set_num_threads(os.cpu_count() or 1)
    modelo = SentenceTransformer(args.modelo, device="cpu")
    modelo.max_seq_length = args.max_tokens  # titulos sao curtos: limitar acelera sem perder conteudo

    def encoder(lote):
        return modelo.encode(lote, batch_size=args.batch, normalize_embeddings=True,
                             convert_to_numpy=True, show_progress_bar=False)

    if args.benchmark:
        amostra = textos[:: max(1, len(textos) // args.benchmark)][: args.benchmark]
        encoder(amostra[:64])  # aquecimento
        t0 = time.time(); encoder(amostra); dt = time.time() - t0
        taxa = len(amostra) / dt
        print(f"Benchmark: {len(amostra)} títulos em {dt:.1f}s = {taxa:.0f} títulos/s")
        print(f"Estimativa para {total} títulos: ~{total / taxa / 60:.0f} minutos (CPU, {os.cpu_count()} threads)")
        return 0

    pasta = Path(args.saida)
    pasta.mkdir(parents=True, exist_ok=True)
    manifesto = {"modelo": args.modelo, "n_titulos": total, "bloco": args.bloco,
                 "max_tokens": args.max_tokens, "normalizado": True}
    arq_man = pasta / "manifesto.json"
    if arq_man.exists() and json.loads(arq_man.read_text(encoding="utf-8")) != manifesto:
        raise RuntimeError(f"{arq_man} diverge dos parâmetros atuais; use outra pasta (--saida) ou apague a atual.")
    arq_man.write_text(json.dumps(manifesto, indent=2), encoding="utf-8")
    novos = codificar_em_blocos(textos, encoder, pasta, args.bloco)
    emb = carregar_embeddings(pasta)
    if emb.shape[0] != total:
        raise RuntimeError(f"{emb.shape[0]} vetores para {total} títulos únicos")
    print(f"Concluído: {emb.shape[0]} vetores de {emb.shape[1]} dimensões ({novos} blocos gerados nesta execução).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--confirmar-banco", required=True)
    ap.add_argument("--modelo", default=MODELO_PADRAO)
    ap.add_argument("--benchmark", type=int, metavar="N", help="Só mede a velocidade com N títulos e estima o total")
    ap.add_argument("--saida", default="data/embeddings")
    ap.add_argument("--bloco", type=int, default=20000, help="Títulos por bloco salvo (retomada)")
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--max-tokens", type=int, default=64)
    ap.add_argument("--recriar", action="store_true", help="Refaz ml.titulo_unico")
    try:
        return run(ap.parse_args())
    except RuntimeError as e:
        print("FALHA:", e); return 1


if __name__ == "__main__":
    raise SystemExit(main())
