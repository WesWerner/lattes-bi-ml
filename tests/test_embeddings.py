import numpy as np
import pytest
from etl.embeddings import carregar_embeddings, codificar_em_blocos


def encoder_falso(lote):
    # vetor deterministico: [comprimento, ordem do primeiro caractere]
    return np.array([[len(t), ord(t[0])] for t in lote], dtype=np.float32)


TEXTOS = [f"titulo numero {i}" for i in range(25)]


def test_blocos_e_ordem(tmp_path):
    novos = codificar_em_blocos(TEXTOS, encoder_falso, tmp_path, 10, log=lambda *_: None)
    assert novos == 3
    emb = carregar_embeddings(tmp_path)
    assert emb.shape == (25, 2)
    assert np.allclose(emb, encoder_falso(TEXTOS))


def test_retomada_pula_blocos_existentes(tmp_path):
    codificar_em_blocos(TEXTOS[:10], encoder_falso, tmp_path, 10, log=lambda *_: None)  # so o bloco 0
    chamadas = []
    def contador(lote):
        chamadas.append(len(lote)); return encoder_falso(lote)
    novos = codificar_em_blocos(TEXTOS, contador, tmp_path, 10, log=lambda *_: None)
    assert novos == 2 and chamadas == [10, 5]
    assert np.allclose(carregar_embeddings(tmp_path), encoder_falso(TEXTOS))


def test_tamanho_incorreto_falha(tmp_path):
    with pytest.raises(RuntimeError):
        codificar_em_blocos(TEXTOS, lambda lote: np.zeros((1, 2)), tmp_path, 10, log=lambda *_: None)
    assert not list(tmp_path.glob("bloco_*.npy"))  # nada gravado pela metade
