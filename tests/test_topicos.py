import numpy as np
import pytest

pytest.importorskip("bertopic")
from etl.topicos import STOPWORDS, ajustar_topicos, resumo_topicos

TEMAS = {
    0: "saúde pública vacina epidemia hospital paciente tratamento clínico".split(),
    1: "educação ensino escola professor currículo aprendizagem didática".split(),
    2: "bacia hidrográfica solo erosão água manejo florestal agrícola".split(),
}


def _dados(n_por_tema=400, dim=32, seed=0):
    rng = np.random.default_rng(seed)
    textos, emb = [], []
    for t, palavras in TEMAS.items():
        centro = np.zeros(dim); centro[t * 8:(t + 1) * 8] = 4.0
        for _ in range(n_por_tema):
            textos.append(" ".join(rng.choice(palavras, 4, replace=False)) + f" {rng.integers(1000)}x")
            emb.append(centro + rng.normal(0, 0.4, dim))
    return textos, np.array(emb, dtype=np.float32)


def test_encontra_tres_temas():
    textos, emb = _dados()
    modelo, topicos = ajustar_topicos(textos, emb, min_cluster_size=50, min_samples=10, log=lambda *_: None)
    linhas = resumo_topicos(modelo, topicos, textos)
    reais = [l for l in linhas if l["id_topico"] != -1]
    assert len(reais) == 3
    assert sum(l["n_titulos"] for l in linhas) == len(textos)
    assert all(len(l["palavras"]) > 0 for l in reais)


def test_stopwords_cobrem_tres_idiomas():
    assert {"de", "the", "del", "estudo"} <= set(STOPWORDS)


def test_acentos_preservados_nos_rotulos():
    # BERTopic com language="english" (padrao) apaga acentos: 'educação' viraria 'educao'.
    textos, emb = _dados()
    modelo, topicos = ajustar_topicos(textos, emb, min_cluster_size=50, min_samples=10, log=lambda *_: None)
    palavras = {p for l in resumo_topicos(modelo, topicos, textos) for p, _ in l["palavras"]}
    assert {"saúde", "pública", "educação", "currículo"} <= palavras
    assert "sade" not in palavras and "educao" not in palavras


def test_reduzir_outliers_sem_ruido_nao_falha():
    textos, emb = _dados()
    ajustar_topicos(textos, emb, min_cluster_size=50, min_samples=10, reduzir_outliers=True, log=lambda *_: None)
