#!/usr/bin/env python3
"""Diagnostico de UM XML que falhou no parse (SOMENTE LEITURA, sem banco).

Uso:  python scripts/diagnostico_xml.py "C:/caminho/Curriculos/Rebeca_Matos_Groner.xml"

Nao imprime texto do curriculo: so tamanhos, posicoes, codigos de caracteres e bytes em hexadecimal.
"""
import io
import re
import sys
from pathlib import Path

from lxml import etree

# caracteres proibidos em XML 1.0 (controles exceto TAB/LF/CR, substitutos e nao-caracteres)
ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def kw():
    return dict(encoding="utf-8", resolve_entities=False, no_network=True, recover=False, huge_tree=True)


def attempt(label, fn):
    try:
        fn()
        print(f"  {label}: OK")
    except etree.XMLSyntaxError as e:
        print(f"  {label}: ERRO de sintaxe -> {e}")
    except Exception as e:  # noqa: BLE001
        print(f"  {label}: ERRO {type(e).__name__} -> {e}")


def main(p: Path):
    raw = p.read_bytes()
    print(f"Arquivo: {p.name}  |  {len(raw):,} bytes  |  linhas: {raw.count(b'\\n') + 1}")
    print(f"BOM UTF-8: {raw.startswith(b'\\xef\\xbb\\xbf')}  |  bytes NUL: {raw.count(b'\\x00')}")
    m = re.search(rb'encoding\s*=\s*["\']([\w.-]+)["\']', raw[:200])
    print(f"Declaracao de encoding: {m.group(1).decode() if m else '(nenhuma)'}")
    print(f"Termina com </CURRICULO-VITAE>: {raw.rstrip().endswith(b'</CURRICULO-VITAE>')}  (False = arquivo truncado?)")

    print("\nParse:")
    attempt("etree.parse(caminho)        [como a auditoria]", lambda: etree.parse(str(p), etree.XMLParser(**kw())))
    attempt("etree.parse(bytes)", lambda: etree.parse(io.BytesIO(raw), etree.XMLParser(**kw())))

    def it():
        ctx = etree.iterparse(io.BytesIO(raw), events=("end",), **kw())
        for _ in ctx:
            pass
    attempt("etree.iterparse(bytes)      [como o carregador]", it)

    print("\nCausas possiveis:")
    found = False
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        found = True
        a, b = max(0, e.start - 8), min(len(raw), e.end + 8)
        print(f"  * Bytes que NAO sao UTF-8 valido na posicao de byte {e.start:,} "
              f"(hex vizinho: {raw[a:b].hex(' ')}). Provavel arquivo em Latin-1 de verdade.")
        text = raw.decode("utf-8", errors="replace")
    bad = list(ILLEGAL.finditer(text))
    if bad:
        found = True
        shown = ", ".join(f"U+{ord(m.group()):04X}@{m.start():,}" for m in bad[:8])
        print(f"  * {len(bad)} caractere(s) proibido(s) em XML 1.0: {shown}")
    if not raw.rstrip().endswith(b"</CURRICULO-VITAE>"):
        found = True
        print("  * O arquivo nao termina com a tag de fechamento: possivelmente truncado.")
    if not found:
        print("  * Nenhuma das causas comuns encontrada; envie a mensagem de erro acima.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))
