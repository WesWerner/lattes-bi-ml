import numpy as np
import pytest

pytest.importorskip("sklearn")
from etl.avaliacao import lda_topicos
from etl.coerencia import coerencia_cv, tokenizar

TEMAS = [
    "saúde vacina epidemia hospital paciente tratamento clínico".split(),
    "educação ensino escola professor currículo aprendizagem didática".split(),
    "bacia hidrográfica solo erosão água manejo florestal agrícola".split(),
]


def _textos(n=300, seed=0):
    rng = np.random.default_rng(seed)
    return [" ".join(rng.choice(TEMAS[i % 3], 4, replace=False)) for i in range(n)]


def test_lda_recupera_temas_e_cv_alto():
    textos = _textos()
    topicos = lda_topicos(textos, 3, max_iter=15, min_df=2, max_df=1.0, log=lambda *_: None)
    assert len(topicos) == 3 and all(len(t) == 10 for t in topicos)
    docs = [tokenizar(t) for t in textos]
    cv = coerencia_cv([t[:6] for t in topicos], docs)
    assert np.mean(cv) > 0.5
