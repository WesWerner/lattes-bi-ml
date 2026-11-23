from pathlib import Path

import pytest

from etl.extractor import extract_file


def config_minimal():
    return {
        "source": {"root_element": "CURRICULO-VITAE", "id_lattes_xpath": "@NUMERO-IDENTIFICADOR"},
        "mappings": [
            {"table": "stg.curriculo_origem", "source": {"path": "."}, "fields": {}},
            {"table": "stg.pesquisador", "source": {"path": "."}, "fields": {
                "id_lattes": {"derived": "root @NUMERO-IDENTIFICADOR"},
                "chave_pesquisador": {"derived": "same value as stg.curriculo_origem.chave_pesquisador"},
                "nome": {"xpath": "DADOS-GERAIS/@NOME-COMPLETO"},
                "atuacao_profissional": {"derived_from_table": "stg.atuacao_profissional"},
            }},
            {"table": "stg.atuacao_profissional", "source": {"path": "DADOS-GERAIS/ATUACOES-PROFISSIONAIS/ATUACAO-PROFISSIONAL"}, "fields": {
                "id_lattes": {"derived": "root @NUMERO-IDENTIFICADOR"},
                "ordem_xml": {"derived": "1-based"},
                "sequencia_importancia": {"xpath": "@SEQUENCIA-IMPORTANCIA", "cast": "integer_or_null"},
                "nome_instituicao": {"xpath": "@NOME-INSTITUICAO"},
                "dados_xml": {"derived": "JSON object of all attributes"},
            }},
            {"table": "stg.linha_pesquisador", "source": {"path": "DADOS-GERAIS/ATUACOES-PROFISSIONAIS/ATUACAO-PROFISSIONAL/LINHA-DE-PESQUISA"}, "fields": {
                "id_lattes": {"derived": "root @NUMERO-IDENTIFICADOR"},
                "ordem_xml": {"derived": "1-based"},
                "linha_pesquisa": {"xpath": "@TITULO"},
                "indicador_linha_pesquisa_ativa": {"xpath": "@FLAG-LINHA-DE-PESQUISA-ATIVA", "transform": "SIM->true; NAO->false; unexpected->null + warning"},
            }},
            {"table": "stg.artigos", "source": {"path": "PRODUCAO-BIBLIOGRAFICA/ARTIGO-PUBLICADO"}, "fields": {
                "id_lattes": {"derived": "root @NUMERO-IDENTIFICADOR"},
                "ordem_xml": {"derived": "1-based"},
                "titulo": {"xpath": "@TITULO"},
                "autores": {"authors": {"nodes_xpath": "AUTORES", "name_attribute": "NOME", "order_attribute": "ORDEM", "separator": "; "}},
            }},
        ],
    }


def ddl_limits(title_limit=50):
    return {
        "stg.curriculo_origem": {"nome_arquivo": None, "caminho_relativo": None, "hash_sha256": 64,
                                  "id_lattes_original": 100, "chave_pesquisador": None, "status_processamento": 15, "tipo_erro": None},
        "stg.pesquisador": {"id_lattes": 100, "chave_pesquisador": None, "nome": 100, "atuacao_profissional": None},
        "stg.atuacao_profissional": {"id_lattes": 100, "ordem_xml": None, "sequencia_importancia": None, "nome_instituicao": None, "dados_xml": None},
        "stg.linha_pesquisador": {"id_lattes": 100, "ordem_xml": None, "linha_pesquisa": 500, "indicador_linha_pesquisa_ativa": None},
        "stg.artigos": {"id_lattes": 100, "ordem_xml": None, "titulo": title_limit, "autores": None},
    }


def write_xml(tmp_path: Path, xml: str) -> Path:
    path = tmp_path / "sample.xml"
    # Deliberadamente declara ISO-8859-1, embora os bytes do arquivo sejam UTF-8.
    xml = xml.replace('<?xml version="1.0" encoding="UTF-8"?>', '<?xml version="1.0" encoding="ISO-8859-1"?>')
    path.write_bytes(xml.encode("utf-8"))
    return path


def base_xml(extra="", id_attr=""):
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<CURRICULO-VITAE {id_attr}>
  <DADOS-GERAIS NOME-COMPLETO="Ana">
    <ATUACOES-PROFISSIONAIS>
      <ATUACAO-PROFISSIONAL SEQUENCIA-IMPORTANCIA="2" NOME-INSTITUICAO="Instituição B" />
      <ATUACAO-PROFISSIONAL SEQUENCIA-IMPORTANCIA="1" NOME-INSTITUICAO="Instituição A">
        <LINHA-DE-PESQUISA TITULO="Linha" FLAG-LINHA-DE-PESQUISA-ATIVA="SIM" />
      </ATUACAO-PROFISSIONAL>
      <ATUACAO-PROFISSIONAL SEQUENCIA-IMPORTANCIA="3" NOME-INSTITUICAO="Instituição C" />
    </ATUACOES-PROFISSIONAIS>
  </DADOS-GERAIS>
  <PRODUCAO-BIBLIOGRAFICA>
    <ARTIGO-PUBLICADO TITULO="Artigo 1">
      <AUTORES NOME="Autor dois" ORDEM="2" />
      <AUTORES NOME="Autor um" ORDEM="1" />
    </ARTIGO-PUBLICADO>
    <ARTIGO-PUBLICADO TITULO="Artigo 2"><AUTORES NOME="Autora" ORDEM="1" /></ARTIGO-PUBLICADO>
  </PRODUCAO-BIBLIOGRAFICA>
  {extra}
</CURRICULO-VITAE>'''


def test_id_ausente_usa_chave_arquivo_e_ordem_xml(tmp_path):
    path = write_xml(tmp_path, base_xml())
    got = extract_file(path, "sample.xml", config_minimal(), ddl_limits())
    assert got["status"] == "OK"
    assert got["id_lattes_original"] is None
    assert got["chave_pesquisador"] == "ARQUIVO:sample.xml"
    assert [r["ordem_xml"] for r in got["rows"]["stg.artigos"]] == [1, 2]
    assert [r["ordem_xml"] for r in got["rows"]["stg.atuacao_profissional"]] == [1, 2, 3]
    assert got["rows"]["stg.pesquisador"][0]["chave_pesquisador"] == "ARQUIVO:sample.xml"


def test_autores_ordenados_pela_ordem_numerica(tmp_path):
    path = write_xml(tmp_path, base_xml())
    got = extract_file(path, "sample.xml", config_minimal(), ddl_limits())
    assert got["rows"]["stg.artigos"][0]["autores"] == "Autor um; Autor dois"


def test_atuacao_principal_usa_menor_sequencia_valida(tmp_path):
    path = write_xml(tmp_path, base_xml(id_attr='NUMERO-IDENTIFICADOR="123"'))
    got = extract_file(path, "sample.xml", config_minimal(), ddl_limits())
    assert got["rows"]["stg.pesquisador"][0]["atuacao_profissional"] == "Instituição A"


@pytest.mark.parametrize(("flag", "expected"), [("SIM", True), ("NAO", False)])
def test_flag_sim_nao(tmp_path, flag, expected):
    xml = base_xml().replace('FLAG-LINHA-DE-PESQUISA-ATIVA="SIM"', f'FLAG-LINHA-DE-PESQUISA-ATIVA="{flag}"')
    path = write_xml(tmp_path, xml)
    got = extract_file(path, "sample.xml", config_minimal(), ddl_limits())
    assert got["rows"]["stg.linha_pesquisador"][0]["indicador_linha_pesquisa_ativa"] is expected


def test_vazio_vira_null(tmp_path):
    xml = base_xml().replace('NOME-COMPLETO="Ana"', 'NOME-COMPLETO="   "')
    path = write_xml(tmp_path, xml)
    got = extract_file(path, "sample.xml", config_minimal(), ddl_limits())
    assert got["rows"]["stg.pesquisador"][0]["nome"] is None


def test_valor_acima_limite_gera_erro_sem_truncar(tmp_path):
    path = write_xml(tmp_path, base_xml())
    got = extract_file(path, "sample.xml", config_minimal(), ddl_limits(title_limit=5))
    assert got["status"] == "ERRO"
    assert got["error"] == "VALOR_EXCEDE_LIMITE:stg.artigos.titulo (8>5)"
    assert got["rows"] == {}


@pytest.mark.parametrize("pad", range(8))
def test_arquivo_grande_com_acentos_e_mojibake(tmp_path, pad):
    """Regressao: XML > 100 KB (varios blocos de 32 KB) com texto acentuado e mojibake em todo o arquivo.
    O iterparse falhava com 'Input is not proper UTF-8' num arquivo valido; o pad desloca as fronteiras de bloco."""
    mojibake = "Educação".encode("utf-8").decode("latin-1")
    artigos = "".join(
        f'<ARTIGO-PUBLICADO TITULO="{"x" * pad}Ciência e ação {i} – {mojibake}">'
        f'<AUTORES NOME="José {i}" ORDEM="1"/></ARTIGO-PUBLICADO>'
        for i in range(1500)
    )
    xml = ('<?xml version="1.0" encoding="UTF-8"?><CURRICULO-VITAE NUMERO-IDENTIFICADOR="123">'
           f'<PRODUCAO-BIBLIOGRAFICA>{artigos}</PRODUCAO-BIBLIOGRAFICA></CURRICULO-VITAE>')
    path = write_xml(tmp_path, xml)
    assert path.stat().st_size > 100_000
    got = extract_file(path, "sample.xml", config_minimal(), ddl_limits(title_limit=500))
    assert got["status"] == "OK", got["error"]
    rows = got["rows"]["stg.artigos"]
    assert len(rows) == 1500
    assert rows[0]["titulo"].endswith("Educação") and "Ciência e ação 0" in rows[0]["titulo"]
    assert rows[-1]["autores"] == "José 1499"
