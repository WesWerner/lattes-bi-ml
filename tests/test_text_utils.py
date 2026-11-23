from etl.text_utils import repair


def mojibake_once(text: str) -> str:
    return text.encode("utf-8").decode("latin-1")


def test_texto_correto_nao_muda():
    text = "Produção científica — análise “correta”"
    assert repair(text) == (text, False)


def test_mojibake_um_nivel():
    assert repair("PortuguÃªs") == ("Português", True)


def test_mojibake_dois_niveis():
    text = "Informação"
    broken = mojibake_once(mojibake_once(text))
    assert repair(broken) == (text, True)


def test_texto_misto_preserva_aspas_curvas_e_travessao():
    text = "“Título” — PortuguÃªs"
    assert repair(text) == ("“Título” — Português", True)


def test_graus_celsius():
    assert repair("25Â°C") == ("25°C", True)


def test_a_isolado_nao_muda():
    assert repair("Ã") == ("Ã", False)
