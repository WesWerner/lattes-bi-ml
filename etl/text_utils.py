"""Correção conservadora de mojibake residual nos textos extraídos."""
from __future__ import annotations
import re

MOJI = re.compile(r"[\u00c3\u00c2][\u0080-\u00bf]|Â[°±µ]")   # UTF-8 lido como Latin-1 (ex.: 'PortuguÃªs')

MOJI_SEQ = re.compile(r"[\u00c2-\u00df][\u0080-\u00bf]|[\u00e0-\u00ef][\u0080-\u00bf]{2}|[\u00f0-\u00f4][\u0080-\u00bf]{3}|Â[°±µ]")


def _fix_seq(m: "re.Match") -> str:
    try:
        return m.group(0).encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return m.group(0)


def repair(s: str) -> tuple[str, bool]:
    """Repara codificacao duplicada. Retorna (texto, mudou).
    1) Texto inteiro (ate 3 niveis), so quando cada ida-e-volta latin-1 -> utf-8 e valido.
    2) Se ainda sobrar padrao de mojibake (texto misto: trechos corretos + trechos quebrados, ex.: aspas curvas
       junto de 'Ã§Ã£'), repara so as sequencias quebradas, trecho a trecho, ate 3 passadas."""
    orig = s
    for _ in range(3):
        if not MOJI.search(s):
            break
        try:
            s = s.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
    for _ in range(3):
        if not MOJI.search(s):
            break
        t = MOJI_SEQ.sub(_fix_seq, s)
        if t == s:
            break
        s = t
    return s, s != orig

