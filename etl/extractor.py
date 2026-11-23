"""Extração de um XML Lattes conforme config/mapeamento.yaml, sem acesso ao banco."""
from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path
from typing import Any

import yaml
from lxml import etree

from .text_utils import repair


class ExtractionError(Exception):
    """Erro de extração que impede carregar qualquer linha do arquivo."""


def make_parser() -> etree.XMLParser:
    return etree.XMLParser(encoding="utf-8", resolve_entities=False,
                           no_network=True, recover=False, huge_tree=True)


def clean(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = repair(value)[0].strip()
    return value or None


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_ddl_limits(path: Path) -> tuple[dict[str, dict[str, int | None]], set[str], int | None]:
    """Extrai limites VARCHAR e estados permitidos diretamente do DDL aprovado."""
    text = path.read_text(encoding="utf-8")
    tables: dict[str, dict[str, int | None]] = {}
    for match in re.finditer(r"CREATE TABLE IF NOT EXISTS\s+(stg\.\w+)\s*\((.*?)\n\)\s*;", text, re.S | re.I):
        cols: dict[str, int | None] = {}
        for line in match.group(2).splitlines():
            col = re.match(r"\s{4}(\w+)\s+([A-Z]+)(?:\((\d+)\))?", line, re.I)
            if col:
                name, typ, size = col.groups()
                cols[name] = int(size) if typ.upper() in {"VARCHAR", "CHAR"} and size else None
        tables[match.group(1)] = cols
    status_match = re.search(r"status_processamento\s+VARCHAR\((\d+)\).*?CHECK\s*\(\s*status_processamento\s+IN\s*\(([^)]*)\)\s*\)", text, re.S | re.I)
    if not status_match:
        raise ValueError("Não foi possível identificar no DDL o tamanho e o CHECK de status_processamento.")
    status_length = int(status_match.group(1))
    statuses = set(re.findall(r"'([^']+)'", status_match.group(2)))
    return tables, statuses, status_length


def _xpath_value(node: etree._Element, xpath: str) -> str | None:
    if xpath.startswith("@"):
        return node.get(xpath[1:])
    found = node.xpath("./" + xpath)
    if not found:
        return None
    first = found[0]
    if isinstance(first, etree._Element):
        return "".join(first.itertext())
    return str(first)


def _author_value(node: etree._Element, spec: dict) -> str | None:
    author_spec = spec["authors"]
    authors = []
    for source_order, author in enumerate(node.xpath("./" + author_spec["nodes_xpath"])):
        name = clean(author.get(author_spec["name_attribute"]))
        raw_order = clean(author.get(author_spec["order_attribute"]))
        try:
            order = int(raw_order) if raw_order is not None else 10**9
        except ValueError:
            order = 10**9
        authors.append((order, source_order, name))
    authors.sort(key=lambda x: (x[0], x[1]))
    names = [name for _, _, name in authors if name]
    return author_spec.get("separator", "; ").join(names) or None


def _convert_value(table: str, column: str, spec: dict, node: etree._Element,
                   root_id: str | None, relative_path: str) -> Any:
    if "xpath" in spec:
        value = clean(_xpath_value(node, spec["xpath"]))
        transform = spec.get("transform", "")
        if "SIM->true" in transform:
            if value is None:
                return None
            flag = value.upper()
            if flag == "SIM":
                return True
            if flag == "NAO":
                return False
            return None
        if spec.get("cast") == "integer_or_null":
            if value is None:
                return None
            try:
                return int(value)
            except ValueError:
                return None
        return value
    if "authors" in spec:
        return _author_value(node, spec)
    derived = spec.get("derived", "")
    if isinstance(derived, str) and derived.startswith("root "):
        return root_id
    if column == "ordem_xml":
        # Preenchido pelo chamador, que conhece a posição dentro do caminho de origem.
        return None
    if column == "dados_xml":
        return {k: clean(v) for k, v in node.attrib.items()}
    if column == "chave_pesquisador":
        return root_id if root_id else "ARQUIVO:" + relative_path
    if column == "atuacao_profissional":
        return None
    return None


def extract_file(path: Path | str, relative_path: str, config: dict,
                 ddl_limits: dict[str, dict[str, int | None]]) -> dict:
    """Retorna metadados, linhas por tabela, avisos e erro sem escrever no banco."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return {
            "path": str(path), "caminho_relativo": relative_path, "nome_arquivo": path.name,
            "hash_sha256": None, "id_lattes_original": None,
            "chave_pesquisador": "ARQUIVO:" + relative_path,
            "rows": {}, "error": f"ERRO_LEITURA_XML:{type(exc).__name__}", "warnings": [], "status": "ERRO",
        }
    sha256 = hashlib.sha256(raw).hexdigest()
    result = {
        "path": str(path), "caminho_relativo": relative_path, "nome_arquivo": path.name,
        "hash_sha256": sha256, "id_lattes_original": None,
        "chave_pesquisador": "ARQUIVO:" + relative_path,
        "rows": {}, "error": None, "warnings": [], "status": "OK",
    }
    try:
        # parse(bytes) força UTF-8 mesmo quando a declaração XML informa ISO-8859-1.
        # Não usar iterparse: em alguns ambientes (libxml2 mais antigo) ele falha na fronteira dos blocos
        # de 32 KB com "Input is not proper UTF-8" em arquivos válidos (caso Rebeca_Matos_Groner.xml).
        root = etree.parse(io.BytesIO(raw), make_parser()).getroot()
        if etree.QName(root).localname != config["source"]["root_element"]:
            raise ExtractionError("RAIZ_XML_INESPERADA")
        id_xpath = config["source"].get("id_lattes_xpath")
        if not id_xpath:
            raise ExtractionError("MAPEAMENTO_SEM_ID_LATTES_XPATH")
        result["id_lattes_original"] = clean(_xpath_value(root, id_xpath))
        if result["id_lattes_original"]:
            result["chave_pesquisador"] = result["id_lattes_original"]
        all_rows: dict[str, list[dict]] = {}
        activity_rows: list[dict] = []
        for mapping in config["mappings"]:
            table = mapping["table"]
            if table == "stg.curriculo_origem":
                continue
            source_path = mapping["source"]["path"]
            nodes = [root] if source_path == "." else root.xpath("./" + source_path)
            rows = []
            for position, node in enumerate(nodes, start=1):
                row = {}
                for column, spec in mapping["fields"].items():
                    value = _convert_value(table, column, spec, node,
                                           result["id_lattes_original"], relative_path)
                    if column == "ordem_xml":
                        value = position
                    if column == "indicador_linha_pesquisa_ativa":
                        raw_flag = clean(_xpath_value(node, spec["xpath"]))
                        if raw_flag and raw_flag.upper() not in {"SIM", "NAO"}:
                            result["warnings"].append(f"FLAG_LINHA_ATIVA_INESPERADA:{raw_flag[:30]}")
                    limit = ddl_limits.get(table, {}).get(column)
                    if value is not None and limit is not None and isinstance(value, str) and len(value) > limit:
                        raise ExtractionError(f"VALOR_EXCEDE_LIMITE:{table}.{column} ({len(value)}>{limit})")
                    row[column] = value
                row["arquivo_id"] = None
                rows.append(row)
            all_rows[table] = rows
            if table == "stg.atuacao_profissional":
                activity_rows = rows
        # A atuação principal é a instituição da menor sequência numérica válida; desempate por ordem_xml.
        valid_activities = [r for r in activity_rows if r.get("sequencia_importancia") is not None]
        valid_activities.sort(key=lambda r: (r["sequencia_importancia"], r["ordem_xml"]))
        main_activity = valid_activities[0].get("nome_instituicao") if valid_activities else None
        researcher_mapping = next(m for m in config["mappings"] if m["table"] == "stg.pesquisador")
        researcher = {}
        for column, spec in researcher_mapping["fields"].items():
            if column == "atuacao_profissional":
                researcher[column] = main_activity
            else:
                researcher[column] = _convert_value("stg.pesquisador", column, spec, root,
                                                    result["id_lattes_original"], relative_path)
            limit = ddl_limits.get("stg.pesquisador", {}).get(column)
            value = researcher[column]
            if value is not None and limit is not None and isinstance(value, str) and len(value) > limit:
                raise ExtractionError(f"VALOR_EXCEDE_LIMITE:stg.pesquisador.{column} ({len(value)}>{limit})")
        researcher["arquivo_id"] = None
        all_rows["stg.pesquisador"] = [researcher]
        result["rows"] = all_rows
    except (OSError, etree.XMLSyntaxError) as exc:
        # Evita registrar conteúdo do XML ou dados pessoais na mensagem do erro.
        line = getattr(exc, "position", (None, None))[0]
        result["error"] = f"ERRO_PARSE_XML:linha={line}" if line else "ERRO_LEITURA_XML"
        result["status"] = "ERRO"
        result["rows"] = {}
    except ExtractionError as exc:
        result["error"] = str(exc)
        result["status"] = "ERRO"
        result["rows"] = {}
    return result
