"""Coerencia de topicos C_v (Roder et al., 2015) sem depender do gensim.

O gensim nao tem instalador para o Python 3.14 (a compilacao falha), entao a metrica e calculada aqui.
A implementacao segue o gensim (janela booleana deslizante de 110 tokens, NPMI, vetores de contexto,
similaridade do cosseno, media aritmetica) e e conferida contra ele em tests/test_coerencia.py.
Titulos curtos (ate `janela` tokens) formam uma unica janela: contam-se documentos; nesse caso o resultado e
identico ao do gensim. Para documentos maiores que a janela, o gensim tem uma imprecisao (ao deslizar, apaga
uma palavra que ainda aparece mais adiante na janela); aqui conta-se a presenca real (diferenca ~1e-4).
"""
from __future__ import annotations

import re
from typing import Iterable, Sequence

import numpy as np

EPSILON = 1e-12
TOKEN_RE = re.compile(r"(?u)\b[^\W\d_]{3,}\b")


def tokenizar(texto: str, stopwords: set[str] | frozenset[str] = frozenset()) -> list[str]:
    """Mesmo criterio do vetorizador dos topicos: minusculas, so letras, >= 3 caracteres, sem stopwords."""
    return [t for t in TOKEN_RE.findall(texto.lower()) if t not in stopwords]


def unigramas_do_topico(palavras: Sequence[str], n: int = 10) -> list[str]:
    """Palavras do topico (que podem ser bigramas) -> primeiros n unigramas unicos, em ordem de peso."""
    vistos: list[str] = []
    for p in palavras:
        for u in p.split():
            if u not in vistos:
                vistos.append(u)
            if len(vistos) == n:
                return vistos
    return vistos


def _contagens(docs: Iterable[Sequence[str]], vocab: dict[str, int], janela: int):
    """Retorna (n_janelas, ocorrencias[V], coocorrencias[V,V]) com janela booleana deslizante."""
    v = len(vocab)
    occ = np.zeros(v, dtype=np.int64)
    co = np.zeros((v, v), dtype=np.int64)
    n_janelas = 0

    def contar(ids: Iterable[int]):
        u = sorted(set(ids))
        if not u:
            return
        occ[u] += 1
        if len(u) > 1:
            idx = np.array(u)
            co[np.ix_(idx, idx)] += 1  # inclui diagonal; sera descartada abaixo

    for doc in docs:
        n = len(doc)
        if n <= janela:
            n_janelas += 1
            contar(vocab[t] for t in doc if t in vocab)
        else:  # documento maior que a janela: deslizar de 1 em 1, como o gensim
            ids = [vocab.get(t, -1) for t in doc]
            for i in range(n - janela + 1):
                n_janelas += 1
                contar(j for j in ids[i:i + janela] if j >= 0)
    np.fill_diagonal(co, 0)
    return n_janelas, occ, co


def coerencia_cv(topicos: Sequence[Sequence[str]], docs: Iterable[Sequence[str]], janela: int = 110):
    """C_v de cada topico. `topicos`: listas de palavras (unigramas); `docs`: listas de tokens.
    Palavras que nao aparecem em nenhum documento sao ignoradas. Retorna lista de floats (nan se < 2 palavras)."""
    topicos = [list(dict.fromkeys(t)) for t in topicos]
    vocab = {w: i for i, w in enumerate(sorted({w for t in topicos for w in t}))}
    n, occ, co = _contagens(docs, vocab, janela)
    if n == 0:
        raise ValueError("nenhum documento")
    p = occ / n
    resultados = []
    for t in topicos:
        ids = [vocab[w] for w in t if occ[vocab[w]] > 0]
        if len(ids) < 2:
            resultados.append(float("nan")); continue
        pw = p[ids]
        pco = co[np.ix_(ids, ids)] / n
        npmi = np.log((pco + EPSILON) / np.outer(pw, pw)) / -np.log(pco + EPSILON)
        np.fill_diagonal(npmi, np.log((pw + EPSILON) / (pw * pw)) / -np.log(pw + EPSILON))
        total = npmi.sum(axis=0)  # vetor de contexto do conjunto inteiro (W*)
        sims = (npmi @ total) / (np.linalg.norm(npmi, axis=1) * np.linalg.norm(total))
        resultados.append(float(sims.mean()))
    return resultados


def diversidade(topicos: Sequence[Sequence[str]]) -> float:
    """Proporcao de palavras distintas entre todas as listas (1.0 = nenhum topico repete palavras)."""
    todas = [w for t in topicos for w in t]
    return len(set(todas)) / len(todas) if todas else float("nan")
