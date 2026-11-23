import pytest
from etl.corpus import chave_titulo, contar_palavras, detectar_idioma, limpar_titulo, preparar


def test_entidades_e_espacos():
    assert limpar_titulo("Estudo&#10;de   caso &amp; análise") == "Estudo de caso & análise"
    assert limpar_titulo("A&#10;&#10;B") == "A B"
    assert limpar_titulo("Dupla &amp;#10; codificação") == "Dupla codificação"
    assert limpar_titulo(None) == "" and limpar_titulo("   ") == ""


def test_acentos_preservados():
    assert limpar_titulo("Educação Matemática") == "Educação Matemática"


def test_chave_ignora_acento_caixa_pontuacao():
    assert chave_titulo("Educação  Matemática!") == chave_titulo("educacao matematica")


@pytest.mark.parametrize("t,esperado", [
    ("Análise da produção científica nas universidades", "pt"),
    ("A study of the effects of temperature on growth", "en"),
    ("Estudio sobre la educación en el país", "es"),
    ("Machine learning", "indeterminado"),
    ("", "indeterminado"),
])
def test_idioma(t, esperado):
    assert detectar_idioma(t) == esperado


def test_validade():
    assert preparar("Estudo de caso do ensino")["valido"]
    assert preparar("Resumo")["motivo_invalido"] == "curto"
    assert preparar("  ")["motivo_invalido"] == "vazio"
    assert preparar(None)["n_palavras"] == 0
    assert contar_palavras("2020 de 12 ab c") == 2  # só tokens com >= 2 letras e sem dígitos
