"""Somente leitura. Para os arquivos sem ID Lattes na staging, olha a tag raiz do XML e
mostra se o atributo NUMERO-IDENTIFICADOR existe, esta vazio ou tem valor.
Uso: python scripts\\diagnostico_id.py "C:\\...\\Curriculos" reports\\fase6_sem_id_lattes.csv"""
import csv, re, sys
from collections import Counter
from pathlib import Path

xml_dir, csv_path = Path(sys.argv[1]), Path(sys.argv[2])
cont, exemplos = Counter(), {}
for r in csv.DictReader(open(csv_path, encoding="utf-8-sig")):
    p = xml_dir / r["caminho_relativo"]
    try:
        head = p.read_bytes()[:6000].decode("utf-8", errors="replace")
    except OSError as e:
        k = "arquivo_nao_encontrado"; cont[k] += 1; exemplos.setdefault(k, r["caminho_relativo"]); continue
    m = re.search(r"<CURRICULO-VITAE\b[^>]*>", head, re.S)
    if not m:
        k = "sem_tag_raiz_no_inicio"
    else:
        a = re.search(r'NUMERO-IDENTIFICADOR\s*=\s*"([^"]*)"', m.group(0))
        k = "atributo_ausente" if not a else ("atributo_vazio" if not a.group(1).strip() else "atributo_com_valor:" + ("so_digitos" if a.group(1).strip().isdigit() else "outro"))
    cont[k] += 1; exemplos.setdefault(k, r["caminho_relativo"])
for k, n in cont.most_common():
    print(f"{k}: {n}  (ex.: {exemplos[k]})")
