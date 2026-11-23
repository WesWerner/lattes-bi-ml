import numpy as np

from etl.macrotemas import (agrupar_macrotemas, calibrar_limiar, centroides, mais_proximo, rotular_macrotemas,
                            similaridade_propria)


def _dados(seed=0):
    rng = np.random.default_rng(seed)
    # 4 topicos em 2 "regioes": (0,1) perto do eixo x, (2,3) perto do eixo y
    bases = np.array([[1, 0.15, 0, 0], [1, -0.15, 0, 0], [0, 0, 1, 0.15], [0, 0, 1, -0.15]], dtype=np.float32)
    emb, top = [], []
    for t, b in enumerate(bases):
        emb.append(b + rng.normal(0, 0.05, size=(300, 4)))
        top.append(np.full(300, t))
    # ruido: 100 pontos proximos do topico 0 e 100 aleatorios
    emb.append(bases[0] + rng.normal(0, 0.05, size=(100, 4))); top.append(np.full(100, -1))
    emb.append(rng.normal(0, 1, size=(100, 4))); top.append(np.full(100, -1))
    return np.vstack(emb).astype(np.float32), np.concatenate(top)


def test_centroides_e_macrotemas():
    emb, top = _dados()
    ids, cent = centroides(emb, top)
    assert list(ids) == [0, 1, 2, 3]
    assert np.allclose(np.linalg.norm(cent, axis=1), 1, atol=1e-5)
    macro = agrupar_macrotemas(cent, 2)
    assert macro[0] == macro[1] and macro[2] == macro[3] and macro[0] != macro[2]


def test_mais_proximo():
    emb, top = _dados()
    ids, cent = centroides(emb, top)
    idx, sim = mais_proximo(emb[:5], cent)
    assert all(ids[i] == 0 for i in idx) and (sim > 0.9).all()


def test_calibrar_limiar_e_cobertura():
    emb, top = _dados()
    ids, cent = centroides(emb, top)
    limiar, tabela = calibrar_limiar(emb, top, ids, cent, precisao=0.8)
    assert 0.3 <= limiar <= 0.96 and tabela
    ruido = np.where(top == -1)[0]
    _, sim = mais_proximo(emb[ruido], cent)
    ok = sim >= limiar
    assert ok[:100].mean() > 0.9      # os 100 proximos do topico 0 sao aceitos
    assert ok[100:].mean() < 0.6      # o ruido aleatorio e em boa parte rejeitado


def test_rotular_macrotemas():
    textos = ["futebol e esporte escolar", "treino de futebol", "ensino de matemática", "geometria e matemática", "sem macro"]
    macro = np.array([0, 0, 1, 1, -1])
    pal = rotular_macrotemas(textos, macro, 2)
    assert pal[0][0][0].split()[0] in ("futebol", "esporte", "treino", "escolar")
    assert any("matemática" in p for p, _ in pal[1])


def test_similaridade_propria():
    emb, top = _dados()
    ids, cent = centroides(emb, top)
    sp = similaridade_propria(emb, top, ids, cent)
    assert len(sp) == (top != -1).sum() and (sp > 0.9).all()


def test_macrotemas_ward():
    emb, top = _dados()
    ids, cent = centroides(emb, top)
    macro = agrupar_macrotemas(cent, 2, "ward")
    assert macro[0] == macro[1] and macro[2] == macro[3] and macro[0] != macro[2]
