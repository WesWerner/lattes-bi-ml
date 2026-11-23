#!/usr/bin/env python3
"""Diagnostico de codificacao dos XMLs (SOMENTE LEITURA).

Descobre por que o texto extraido aparece como 'PortuguÃªs' em vez de 'Português'.
Uso:  python scripts/diagnostico_encoding.py --xml-dir "C:/caminho/Curriculos" [--n 200]
"""
import argparse, random, re
from collections import Counter
from pathlib import Path
from lxml import etree

MOJI = re.compile(r"[ÃÂ][\u0080-\u00bf]")          # padrao tipico de UTF-8 lido como Latin-1


def declared(b: bytes) -> str:
    m = re.search(rb'encoding\s*=\s*["\']([\w.-]+)["\']', b[:200])
    return m.group(1).decode().upper() if m else "UTF-8 (padrao)"


def classify(b: bytes) -> str:
    decl = declared(b)
    latin_decl = any(k in decl for k in ("8859", "LATIN", "1252"))
    try:
        txt = b.decode("utf-8")
        utf8_ok = True
    except UnicodeDecodeError:
        txt, utf8_ok = "", False
    nonascii = any(c > 127 for c in b)
    if not nonascii:
        return "SEM_ACENTOS"
    if utf8_ok and MOJI.search(txt):
        return "B_DUPLA_CODIFICACAO (bytes UTF-8 de texto que ja era mojibake)"
    if utf8_ok and latin_decl:
        return "A_DECLARA_ISO_MAS_BYTES_SAO_UTF8 (forcar encoding utf-8 no parser)"
    if utf8_ok:
        return "OK_UTF8"
    return "OK_ISO_8859_1 (latin-1 genuino)" if latin_decl else "INDEFINIDO (nem UTF-8 valido nem declarado Latin-1)"


def fix(s: str) -> str:
    """Repara mojibake no nivel da string; so altera se o ida-e-volta for valido."""
    if not MOJI.search(s):
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml-dir", type=Path, required=True)
    ap.add_argument("--n", type=int, default=200)
    a = ap.parse_args()
    files = sorted(a.xml_dir.rglob("*.xml"))
    pick = random.Random(42).sample(files, min(a.n, len(files)))
    cls, decl = Counter(), Counter()
    ex = {}
    for p in pick:
        b = p.read_bytes()
        decl[declared(b)] += 1
        c = classify(b)
        cls[c] += 1
        ex.setdefault(c, p)
    print(f"{len(pick)} arquivos analisados\n\nDeclaracao no cabecalho: {dict(decl)}\n\nClassificacao:")
    for c, n in cls.most_common():
        print(f"  {n:4d}  {c}   (ex.: {ex[c].name})")
    p = ex[cls.most_common(1)[0][0]]
    print(f"\nPrimeiros bytes de {p.name}:\n  {p.read_bytes()[:160]!r}")
    root = etree.parse(str(p), etree.XMLParser(huge_tree=True, resolve_entities=False, no_network=True)).getroot()
    shown = 0
    print("\nExemplos de texto (como o lxml le hoje -> apos reparo de string):")
    for el in root.iter():
        for v in el.attrib.values():
            if MOJI.search(v) and shown < 5:
                print(f"  {v[:60]!r} -> {fix(v)[:60]!r}")
                shown += 1
    if shown == 0:
        print("  (nenhum texto com mojibake neste arquivo)")
    print("\nNomes de arquivo com mojibake na amostra:", sum(bool(MOJI.search(f.name)) for f in pick))


if __name__ == "__main__":
    main()
