import numpy as np
import pytest

from etl.coerencia import coerencia_cv, diversidade, tokenizar, unigramas_do_topico

gensim = pytest.importorskip("gensim", reason="gensim so e usado aqui para conferir a implementacao")


def _corpus(n=600, seed=1, longos=False):
    rng = np.random.default_rng(seed)
    temas = [list("abcdefgh"), list("ijklmnop"), list("qrstuvwx")]
    docs = []
    for _ in range(n):
        t = temas[rng.integers(3)]
        doc = [f"{c}{c}{c}" for c in rng.choice(t, rng.integers(3, 7), replace=False)]
        if rng.random() < 0.3:
            doc.append(f"{rng.choice(temas[rng.integers(3)])}{'z'*2}")
        docs.append(doc)
    if longos:  # documentos maiores que a janela
        docs.append([f"{c}{c}{c}" for c in rng.choice(list("abcdefghijklmnopqrstuvwx"), 20, replace=True)])
    return docs, [[f"{c}{c}{c}" for c in t[:6]] for t in temas]


# Docs <= janela: identico ao gensim (1e-6). Docs maiores que a janela: o gensim apaga palavras repetidas
# ao deslizar a janela (imprecisao dele), entao a tolerancia e maior.
@pytest.mark.parametrize("janela,longos,tol", [(110, False, 1e-6), (10, True, 1e-3)])
def test_igual_ao_gensim(janela, longos, tol):
    from gensim.corpora import Dictionary
    from gensim.models.coherencemodel import CoherenceModel
    docs, topicos = _corpus(longos=longos)
    esperado = CoherenceModel(topics=topicos, texts=docs, dictionary=Dictionary(docs), coherence="c_v",
                              window_size=janela, processes=1).get_coherence_per_topic()
    obtido = coerencia_cv(topicos, docs, janela=janela)
    assert np.allclose(obtido, esperado, atol=tol), (obtido, esperado)


def test_topico_coerente_vence_topico_aleatorio():
    docs, topicos = _corpus()
    coerente = coerencia_cv([topicos[0]], docs)[0]
    misturado = coerencia_cv([[topicos[0][0], topicos[1][0], topicos[2][0], topicos[0][1], topicos[1][1], topicos[2][1]]], docs)[0]
    assert coerente > misturado


def test_utilitarios():
    assert tokenizar("Educação, saúde e o ensino de 2020!", {"ensino"}) == ["educação", "saúde"]
    assert unigramas_do_topico(["saúde pública", "saúde", "vacina"], 3) == ["saúde", "pública", "vacina"]
    assert diversidade([["a", "b"], ["b", "c"]]) == 0.75
