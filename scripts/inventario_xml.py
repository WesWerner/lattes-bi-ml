"""Inventário da estrutura dos XMLs do Lattes (Fase 1).

Percorre uma pasta de XMLs e conta, para cada caminho, quantas vezes a tag, o
atributo ou o texto não vazio aparece e em quantos arquivos. A saída são CSVs
agregados, sem conteúdo dos currículos, usados depois para montar o mapeamento
(`config/mapeamento.yaml`).

Uso:
    python scripts/inventario_xml.py CAMINHO/DOS/XMLS --saida data/inventarios
    python scripts/inventario_xml.py CAMINHO/DOS/XMLS --limite 1000   # amostra
"""
from __future__ import annotations

import argparse
import csv
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


def sem_namespace(nome: str) -> str:
    """Remove o namespace XML ('{uri}tag' -> 'tag'), quando existir."""
    return nome.split("}", 1)[1] if "}" in nome else nome


def novo_contador() -> defaultdict:
    return defaultdict(lambda: {"ocorrencias": 0, "arquivos": set()})


def registrar(contador: defaultdict, caminho: str, arquivo_id: str) -> None:
    contador[caminho]["ocorrencias"] += 1
    contador[caminho]["arquivos"].add(arquivo_id)


def analisar_elemento(elemento, caminho_pai: str, arquivo_id: str, tags, atributos, textos) -> None:
    """Percorre a árvore XML registrando tags, atributos e textos não vazios."""
    caminho = f"{caminho_pai}/{sem_namespace(elemento.tag)}"
    registrar(tags, caminho, arquivo_id)
    for atributo in elemento.attrib:
        registrar(atributos, f"{caminho}/@{sem_namespace(atributo)}", arquivo_id)
    if elemento.text and elemento.text.strip():
        registrar(textos, caminho, arquivo_id)
    for filho in elemento:
        analisar_elemento(filho, caminho, arquivo_id, tags, atributos, textos)


def exportar_csv(destino: Path, contador: defaultdict, tipo: str, total_arquivos: int) -> None:
    campos = ["tipo", "caminho_xml", "ocorrencias_total", "arquivos_com_ocorrencia", "total_arquivos_analisados"]
    with destino.open("w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.DictWriter(f, fieldnames=campos)
        escritor.writeheader()
        for caminho, dados in sorted(contador.items()):
            escritor.writerow({"tipo": tipo, "caminho_xml": caminho,
                               "ocorrencias_total": dados["ocorrencias"],
                               "arquivos_com_ocorrencia": len(dados["arquivos"]),
                               "total_arquivos_analisados": total_arquivos})
    print(f"Relatório gerado: {destino}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pasta_xml", type=Path, help="pasta com os XMLs (busca recursiva)")
    ap.add_argument("--saida", type=Path, default=Path("data/inventarios"), help="pasta dos CSVs de saída")
    ap.add_argument("--limite", type=int, default=None, help="analisa só os N primeiros arquivos (amostra)")
    args = ap.parse_args()

    arquivos = sorted(args.pasta_xml.rglob("*.xml"))[: args.limite]
    if not arquivos:
        print(f"Nenhum XML encontrado em: {args.pasta_xml.resolve()}")
        return 1
    args.saida.mkdir(parents=True, exist_ok=True)
    print(f"Arquivos encontrados: {len(arquivos)}")

    tags, atributos, textos = novo_contador(), novo_contador(), novo_contador()
    erros = []
    for numero, arquivo in enumerate(arquivos, start=1):
        arquivo_id = f"XML_{numero:04d}"  # identificador anônimo: o nome do arquivo não vai para os relatórios
        try:
            analisar_elemento(ET.parse(arquivo).getroot(), "", arquivo_id, tags, atributos, textos)
        except (ET.ParseError, OSError, ValueError) as erro:
            erros.append({"arquivo_id": arquivo_id, "tipo_erro": type(erro).__name__})
            print(f"{arquivo_id}: falha na leitura")

    total = len(arquivos)
    exportar_csv(args.saida / "tags_xml.csv", tags, "tag", total)
    exportar_csv(args.saida / "atributos_xml.csv", atributos, "atributo", total)
    exportar_csv(args.saida / "textos_xml.csv", textos, "texto_nao_vazio", total)
    with (args.saida / "erros_leitura.csv").open("w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.DictWriter(f, fieldnames=["arquivo_id", "tipo_erro"])
        escritor.writeheader()
        escritor.writerows(erros)

    print(f"\nAnálise concluída: {len(tags)} tags, {len(atributos)} atributos, "
          f"{len(textos)} caminhos com texto, {len(erros)} falhas de leitura.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
