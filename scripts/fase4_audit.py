#!/usr/bin/env python3
"""Fase 4 - auditoria do mapeamento XPath -> coluna (SOMENTE LEITURA).

Nao importa psycopg e nao abre conexao com o PostgreSQL: nada e gravado na stg.
Le os XMLs, aplica config/mapeamento.yaml em memoria (dry-run) e compara o que
foi encontrado com os inventarios (tags_xml.csv / atributos_xml.csv) e com os
limites VARCHAR de sql/01_stg.sql.

Uso (na raiz do projeto, na maquina onde esta a pasta dos XMLs):
    python scripts/fase4_audit.py --xml-dir "C:/caminho/Curriculos"
Opcional: --sample-size 500 --seed 42 --pool 1500 --sample-file data/amostra_fase4.txt
Codificacao: por padrao o parser FORCA utf-8 (os XMLs declaram ISO-8859-1 mas os bytes sao UTF-8)
e textos com dupla codificacao residual sao reparados por string. Use --encoding auto para honrar o cabecalho.
"""
from __future__ import annotations

import argparse
import csv
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml
from lxml import etree

MOJI = re.compile(r"[\u00c3\u00c2][\u0080-\u00bf]")   # UTF-8 lido como Latin-1 (ex.: 'PortuguÃªs')


def make_parser(encoding: str | None):
    return etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True, recover=False,
                           encoding=None if encoding in (None, "auto") else encoding)


PARSER = make_parser("utf-8")


# sequencias UTF-8 lidas como Latin-1: byte inicial (C2-F4) + bytes de continuacao (80-BF)
MOJI_SEQ = re.compile(r"[\u00c2-\u00df][\u0080-\u00bf]|[\u00e0-\u00ef][\u0080-\u00bf]{2}|[\u00f0-\u00f4][\u0080-\u00bf]{3}")


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


BIG = 10**9
TECH_COLS = {"id", "id_pesquisador", "id_atuacao", "arquivo_id", "ordem_xml", "dados_xml"}
YEAR_COLS = {"ano", "ano_inicio", "ano_fim", "ano_realizacao"}
MIN_NODES = 30          # minimo de nos na amostra para comparar taxas
RATE_TOL = 0.10         # diferenca maxima aceita entre taxa na amostra e no inventario


# --------------------------------------------------------------------------- leitura de insumos
def load_inventory(path: Path) -> dict[str, tuple[int, int, int]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {
            r["caminho_xml"].removeprefix("/CURRICULO-VITAE/"): (
                int(r["ocorrencias_total"]), int(r["arquivos_com_ocorrencia"]), int(r["total_arquivos_analisados"]))
            for r in csv.DictReader(f)
        }


def load_ddl(path: Path) -> dict[str, dict[str, int | None]]:
    """tabela -> {coluna: limite VARCHAR ou None}."""
    txt = path.read_text(encoding="utf-8")
    out: dict[str, dict[str, int | None]] = {}
    for m in re.finditer(r"CREATE TABLE IF NOT EXISTS\s+(stg\.\w+)\s*\((.*?)\n\)\s*;", txt, re.S | re.I):
        cols: dict[str, int | None] = {}
        for line in m.group(2).splitlines():
            mm = re.match(r"\s{4}(\w+)\s+(\w+)(?:\((\d+)\))?", line)
            if not mm or mm.group(1).upper() in {"CONSTRAINT", "PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "REFERENCES"}:
                continue
            cols[mm.group(1)] = int(mm.group(3)) if mm.group(2).upper() in {"VARCHAR", "CHAR"} and mm.group(3) else None
        out[m.group(1)] = cols
    return out


def field_xpath_inventory_key(mapping: dict, spec: dict) -> str | None:
    base = mapping["source"]["path"]
    xp = spec.get("xpath", "").lstrip("./")
    if not xp:
        return None
    return (base + "/" if base != "." else "") + xp


# --------------------------------------------------------------------------- extracao (dry-run)
def get_val(node, xp: str):
    if xp.startswith("@"):
        return node.get(xp[1:])
    r = node.xpath("./" + xp)
    return str(r[0]) if r else None


def authors_value(node, spec: dict, acc: dict):
    a = spec["authors"]
    items = []
    for i, au in enumerate(node.xpath("./" + a["nodes_xpath"])):
        name = repair((au.get(a["name_attribute"]) or "").strip())[0]
        order = (au.get(a["order_attribute"]) or "").strip()
        if order and not order.isdigit():
            acc["order_nonnumeric"] += 1
        items.append((int(order) if order.isdigit() else BIG, i, name))
    items.sort(key=lambda t: (t[0], t[1]))
    names = [n for _, _, n in items if n]
    acc["names"] += len(names)
    return "; ".join(names) if names else None


def raw_snapshot(node) -> dict:
    snap = {"@": {k: v[:100] for k, v in node.attrib.items()}}
    for ch in node:
        if ch.tag != "AUTORES" and len(ch.attrib):
            snap[ch.tag] = {k: v[:100] for k, v in ch.attrib.items()}
    snap["AUTORES"] = [(a.get("ORDEM-DE-AUTORIA"), a.get("NOME-COMPLETO-DO-AUTOR")) for a in node.xpath("./AUTORES")][:6]
    return snap


class Collector:
    def __init__(self, config: dict, ddl: dict):
        self.config, self.ddl = config, ddl
        self.col = defaultdict(lambda: {"nodes": 0, "present": 0, "nonempty": 0, "maxlen": 0, "over": 0,
                                        "over_ex": [], "bad_year": 0, "year_ex": [], "names": 0,
                                        "order_nonnumeric": 0, "values": Counter()})
        self.tab = defaultdict(lambda: {"files_with": 0, "rows": 0})
        self.examples: dict[str, list] = defaultdict(list)
        self.files = 0
        self.errors: list[tuple[str, str]] = []
        self.repaired = 0     # textos reparados (dupla codificacao residual)
        self.residual = 0     # textos que ainda tem padrao de mojibake apos o reparo
        self.residual_ex: list[dict] = []   # onde ocorrem (para diagnostico)
        self.flag_raw = Counter()
        self.flag_unexpected = 0

    def process(self, path: Path, rel: str):
        try:
            root = etree.parse(str(path), PARSER).getroot()
        except (OSError, etree.XMLSyntaxError) as exc:
            self.errors.append((rel, f"parse: {exc}"))
            return
        if etree.QName(root).localname != self.config["source"]["root_element"]:
            self.errors.append((rel, f"raiz inesperada: {root.tag}"))
            return
        self.files += 1
        rid = root.get("NUMERO-IDENTIFICADOR")
        atuacoes = []
        for m in self.config["mappings"]:
            table, src = m["table"], m["source"]["path"]
            nodes = [root] if src == "." else root.xpath("./" + src)
            if nodes:
                self.tab[table]["files_with"] += 1
            self.tab[table]["rows"] += len(nodes)
            for idx, node in enumerate(nodes, 1):
                row = {}
                for col, spec in m["fields"].items():
                    key = (table, col)
                    st = self.col[key]
                    if "xpath" in spec:
                        raw = get_val(node, spec["xpath"])
                        if raw is not None:
                            raw, changed = repair(raw)
                            self.repaired += changed
                            mres = MOJI.search(raw)
                            self.residual += bool(mres)
                            if mres and len(self.residual_ex) < 200:
                                self.residual_ex.append({"tabela": table, "coluna": col, "arquivo": rel,
                                                         "trecho": raw[max(0, mres.start() - 40): mres.start() + 40],
                                                         "trecho_repr": repr(raw[max(0, mres.start() - 40): mres.start() + 40])})
                        st["nodes"] += 1
                        val = None
                        if raw is not None:
                            st["present"] += 1
                            val = raw.strip() or None
                        if val is not None:
                            st["nonempty"] += 1
                            st["maxlen"] = max(st["maxlen"], len(val))
                            lim = self.ddl.get(table, {}).get(col)
                            if lim and len(val) > lim:
                                st["over"] += 1
                                if len(st["over_ex"]) < 3:
                                    st["over_ex"].append((path.name, len(val)))
                            if col in YEAR_COLS and not re.fullmatch(r"\d{4}", val):
                                st["bad_year"] += 1
                                if len(st["year_ex"]) < 3:
                                    st["year_ex"].append(val[:20])
                            if "transform" in spec:
                                self.flag_raw[val.upper()] += 1
                                if val.upper() not in {"SIM", "NAO", "NÃO"}:
                                    self.flag_unexpected += 1
                            if len(st["values"]) < 50 and col in {"natureza", "situacao", "idioma", "meio_divulgacao", "classificacao_evento"}:
                                st["values"][val] += 1
                        row[col] = val
                    elif "authors" in spec:
                        st = self.col[key]
                        st["nodes"] += 1
                        v = authors_value(node, spec, st)
                        if v:
                            st["present"] += 1
                            st["nonempty"] += 1
                        row[col] = v
                    elif spec.get("derived") == "root @NUMERO-IDENTIFICADOR":
                        row[col] = rid
                    elif col == "ordem_xml":
                        row[col] = idx
                if table == "stg.atuacao_profissional":
                    seq = row.get("sequencia_importancia")
                    atuacoes.append((int(seq) if seq and seq.isdigit() else BIG, idx, row.get("nome_instituicao")))
                if idx == 1 and len(self.examples[table]) < 3:
                    self.examples[table].append((rel, row, raw_snapshot(node) if src != "." else {"@": {"NUMERO-IDENTIFICADOR": rid}}))
        # regra da atuacao principal (apenas para conferencia no dry-run)
        if atuacoes:
            self.col[("stg.pesquisador", "atuacao_profissional")]["nodes"] += 1
            if min(atuacoes)[2]:
                self.col[("stg.pesquisador", "atuacao_profissional")]["present"] += 1
                self.col[("stg.pesquisador", "atuacao_profissional")]["nonempty"] += 1


# --------------------------------------------------------------------------- amostragem
def build_sample(files: list[Path], root_dir: Path, config: dict, size: int, seed: int, pool_n: int) -> list[Path]:
    rng = random.Random(seed)
    pool = rng.sample(files, min(pool_n, len(files)))
    xpaths = {m["table"]: etree.XPath("count(./" + m["source"]["path"] + ")")
              for m in config["mappings"] if m["source"]["path"] != "."}
    feats: dict[Path, set[str]] = {}
    for p in pool:
        try:
            root = etree.parse(str(p), PARSER).getroot()
        except (OSError, etree.XMLSyntaxError):
            continue
        f = set()
        if not root.get("NUMERO-IDENTIFICADOR"):
            f.add("sem_id")
        for t, xp in xpaths.items():
            f.add(("tem:" if xp(root) > 0 else "nao_tem:") + t)
        feats[p] = f
    chosen: list[Path] = []
    seen = set()
    buckets = ["sem_id"] + [f"tem:{t}" for t in xpaths] + [f"nao_tem:{t}" for t in xpaths]
    for b in buckets:
        quota = 15 if b != "sem_id" and not b.startswith("nao_tem") else 8
        cand = [p for p, f in feats.items() if b in f and p not in seen]
        for p in cand[:quota]:
            chosen.append(p)
            seen.add(p)
    rest = [p for p in feats if p not in seen]
    chosen += rest[: max(0, size - len(chosen))]
    return sorted(chosen[:size] if len(chosen) > size else chosen)


# --------------------------------------------------------------------------- relatorios
def write_csv(path: Path, rows: list[dict], fields: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    global PARSER
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xml-dir", type=Path, required=True)
    ap.add_argument("--config", type=Path, default=Path("config/mapeamento.yaml"))
    ap.add_argument("--tags", type=Path, default=Path("data/inventarios/tags_xml.csv"))
    ap.add_argument("--attributes", type=Path, default=Path("data/inventarios/atributos_xml.csv"))
    ap.add_argument("--ddl", type=Path, default=Path("sql/01_stg.sql"))
    ap.add_argument("--sample-size", type=int, default=500)
    ap.add_argument("--pool", type=int, default=1500, help="arquivos lidos para escolher a amostra estratificada")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--sample-file", type=Path, default=Path("data/amostra_fase4.txt"))
    ap.add_argument("--out-dir", type=Path, default=Path("reports"))
    ap.add_argument("--encoding", default="utf-8", help="utf-8 (padrao) ou auto (honra o cabecalho do XML)")
    args = ap.parse_args()

    PARSER = make_parser(args.encoding)
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    tags, attrs = load_inventory(args.tags), load_inventory(args.attributes)
    ddl = load_ddl(args.ddl)
    total_files = config["source"]["expected_files"]

    # 1) inventario do mapeamento ------------------------------------------------------------
    inv_rows, flags = [], []
    for m in config["mappings"]:
        t = m["table"]
        fields = m["fields"]
        mapped = [c for c, s in fields.items() if "xpath" in s or "authors" in s]
        fixed_null = [c for c, s in fields.items() if str(s.get("derived", "")).startswith("NULL")]
        missing = [c for c in ddl.get(t, {}) if c not in fields and c not in TECH_COLS]
        if fixed_null:
            flags.append(f"{t}: colunas fixas em NULL no mapeamento ({', '.join(fixed_null)}) - REVISAR se o ramo do XML esta correto")
        inv_rows.append({"mapeamento": t, "caminho_raiz": m["source"]["path"], "colunas_com_xpath": len(mapped),
                         "colunas_fixas_null": ";".join(fixed_null), "colunas_ddl_sem_mapeamento": ";".join(missing),
                         "linhas_esperadas_inventario": m["source"]["expected_counts"]["occurrences_total"]})
    write_csv(args.out_dir / "fase4_mapeamento_inventario.csv", inv_rows,
              ["mapeamento", "caminho_raiz", "colunas_com_xpath", "colunas_fixas_null",
               "colunas_ddl_sem_mapeamento", "linhas_esperadas_inventario"])

    # 2) amostra --------------------------------------------------------------------------------
    files = sorted(args.xml_dir.rglob("*.xml"))
    if not files:
        print(f"ERRO: nenhum .xml encontrado em {args.xml_dir}", file=sys.stderr)
        return 2
    if args.sample_file.exists():
        sample = [args.xml_dir / ln.strip() for ln in args.sample_file.read_text(encoding="utf-8").splitlines()
                  if ln.strip() and not ln.startswith("#")]
        print(f"Amostra reutilizada de {args.sample_file} ({len(sample)} arquivos)")
    else:
        sample = build_sample(files, args.xml_dir, config, args.sample_size, args.seed, args.pool)
        args.sample_file.parent.mkdir(parents=True, exist_ok=True)
        args.sample_file.write_text(
            f"# seed={args.seed} pool={args.pool} tamanho={len(sample)} (arquivos relativos a --xml-dir)\n" +
            "\n".join(p.relative_to(args.xml_dir).as_posix() for p in sample) + "\n", encoding="utf-8")
        print(f"Amostra criada: {len(sample)} arquivos de {len(files)} -> {args.sample_file}")

    # 3) dry-run de extracao (em memoria) -------------------------------------------------------------
    col = Collector(config, ddl)
    for p in sample:
        col.process(p, p.relative_to(args.xml_dir).as_posix() if p.is_relative_to(args.xml_dir) else p.name)

    # 4) cobertura contra o inventario ----------------------------------------------------------------
    cov, suspects = [], []
    for m in config["mappings"]:
        t, src = m["table"], m["source"]["path"]
        parent_occ = m["source"]["expected_counts"]["occurrences_total"]
        for c, spec in m["fields"].items():
            st = col.col.get((t, c))
            if st is None or ("xpath" not in spec and "authors" not in spec):
                continue
            if "authors" in spec:
                a = spec["authors"]
                exp_attr = a["expected_name_counts"]["occurrences_total"]
                xp_full = (src + "/" if src != "." else "") + a["nodes_xpath"] + "/@" + a["name_attribute"]
                rate_i = exp_attr / parent_occ if parent_occ else 0           # media de autores por no
                rate_s = st["names"] / st["nodes"] if st["nodes"] else 0
                # media de autores varia muito entre amostras: so sinaliza caminho claramente errado (0 ou fora de 0,4x-2,5x)
                ok = rate_i == 0 or 0.4 * rate_i <= rate_s <= 2.5 * rate_i
                status = "AMOSTRA_INSUFICIENTE" if st["nodes"] < MIN_NODES else ("OK" if ok else "SUSPEITO")
                kind = "media_autores_por_no"
            else:
                key = field_xpath_inventory_key(m, spec)
                exp_attr = spec.get("expected_counts", {}).get("occurrences_total", attrs.get(key, (0,))[0])
                xp_full = key
                rate_i = exp_attr / parent_occ if parent_occ else 0           # presenca do atributo por no
                rate_s = st["present"] / st["nodes"] if st["nodes"] else 0
                status = "AMOSTRA_INSUFICIENTE" if st["nodes"] < MIN_NODES else ("OK" if abs(rate_s - rate_i) <= RATE_TOL else "SUSPEITO")
                kind = "presenca_por_no"
            vazio = (1 - st["nonempty"] / st["present"]) if st["present"] else None
            row = {"tabela": t, "coluna": c, "xpath": xp_full, "tipo_taxa": kind, "nos_na_amostra": st["nodes"],
                   "taxa_amostra": round(rate_s, 4), "taxa_inventario": round(rate_i, 4),
                   "diferenca": round(rate_s - rate_i, 4), "pct_vazio_quando_presente": None if vazio is None else round(vazio, 4),
                   "status": status}
            cov.append(row)
            if status == "SUSPEITO":
                suspects.append(row)
    write_csv(args.out_dir / "fase4_cobertura.csv", cov,
              ["tabela", "coluna", "xpath", "tipo_taxa", "nos_na_amostra", "taxa_amostra", "taxa_inventario",
               "diferenca", "pct_vazio_quando_presente", "status"])

    # 5) cobertura de secoes (substitui os 'avisos de no ausente') ---------------------------------------
    sec = []
    for m in config["mappings"]:
        t = m["table"]
        occ, fw, tot = m["source"]["expected_counts"]["occurrences_total"], m["source"]["expected_counts"]["files_with_occurrence"], total_files
        p_i = fw / tot
        p_s = col.tab[t]["files_with"] / col.files if col.files else 0
        # amostra estratificada: so sinaliza o caso extremo (caminho que nao acha nada ou acha demais)
        if col.tab[t]["files_with"] == 0:
            status = "SUSPEITO" if p_i >= 0.05 else "AUSENTE_NA_AMOSTRA"
        else:
            status = "SUSPEITO" if abs(p_s - p_i) > 0.5 else "OK"
        fw_s = col.tab[t]["files_with"]
        sec.append({"tabela": t, "caminho_raiz": m["source"]["path"], "pct_arquivos_amostra": round(p_s, 4),
                    "pct_arquivos_inventario": round(p_i, 4), "linhas_por_arquivo_com_secao_amostra":
                    round(col.tab[t]["rows"] / fw_s, 2) if fw_s else None,
                    "linhas_por_arquivo_com_secao_inventario": round(occ / fw, 2) if fw else None, "status": status})
        if status == "SUSPEITO":
            suspects.append({"tabela": t, "coluna": "(secao)", "xpath": m["source"]["path"], "status": status})
    write_csv(args.out_dir / "fase4_secoes.csv", sec,
              ["tabela", "caminho_raiz", "pct_arquivos_amostra", "pct_arquivos_inventario",
               "linhas_por_arquivo_com_secao_amostra", "linhas_por_arquivo_com_secao_inventario", "status"])

    # 6) perfil de valores (limites VARCHAR, anos, flags) ------------------------------------------------------
    prof = []
    for (t, c), st in sorted(col.col.items()):
        lim = ddl.get(t, {}).get(c)
        if not st["nonempty"]:
            continue
        prof.append({"tabela": t, "coluna": c, "limite_varchar": lim, "comprimento_max_amostra": st["maxlen"],
                     "valores_acima_do_limite": st["over"], "exemplos_acima_do_limite": " | ".join(f"{f}:{n}" for f, n in st["over_ex"]),
                     "anos_fora_de_AAAA": st["bad_year"] if c in YEAR_COLS else "", "exemplos_ano": " | ".join(st["year_ex"]),
                     "autores_ordem_nao_numerica": st["order_nonnumeric"] if c == "autores" else "",
                     "valores_distintos_top": "; ".join(f"{v}={n}" for v, n in st["values"].most_common(8))})
    write_csv(args.out_dir / "fase4_perfil_valores.csv", prof,
              ["tabela", "coluna", "limite_varchar", "comprimento_max_amostra", "valores_acima_do_limite",
               "exemplos_acima_do_limite", "anos_fora_de_AAAA", "exemplos_ano", "autores_ordem_nao_numerica",
               "valores_distintos_top"])
    over = [r for r in prof if r["valores_acima_do_limite"]]

    # 7) exemplos lado a lado ----------------------------------------------------------------------------------------
    md = ["# Fase 4 - exemplos extraidos x XML de origem (amostra)\n"]
    for t, items in col.examples.items():
        md.append(f"\n## {t}\n")
        for rel, row, snap in items:
            md.append(f"**Arquivo:** `{rel}`\n\n*Extraido:*\n```json\n{row}\n```\n*XML (atributos do no e filhos diretos):*\n```json\n{snap}\n```\n")
    (args.out_dir / "fase4_exemplos.md").write_text("\n".join(md), encoding="utf-8")

    if col.residual_ex:
        write_csv(args.out_dir / "fase4_mojibake_residual.csv", col.residual_ex,
                  ["tabela", "coluna", "arquivo", "trecho", "trecho_repr"])
    if col.errors:
        write_csv(args.out_dir / "fase4_erros_leitura.csv", [{"arquivo": a, "erro": b} for a, b in col.errors], ["arquivo", "erro"])

    # 8) resumo automatico ------------------------------------------------------------------------------------------------
    lines = ["# Fase 4 - resumo automatico (rascunho; revisar antes de fechar)\n",
             f"- XMLs na amostra lidos com sucesso: **{col.files}** (erros de leitura: {len(col.errors)})",
             f"- Mapeamentos: {len(config['mappings'])}; colunas comparadas: {len(cov)}",
             f"- SUSPEITO: **{len(suspects)}**; colunas com valores acima do limite VARCHAR: **{len(over)}**",
             f"- Codificacao do parser: {args.encoding}; textos reparados por string: **{col.repaired}**; "
             f"textos ainda com padrao de mojibake apos reparo: **{col.residual}**",
             f"- Flag de linha ativa - valores brutos: {dict(col.flag_raw)}; inesperados: {col.flag_unexpected}", "",
             "## Pontos de revisao"]
    lines += [f"- {f}" for f in flags] or ["- (nenhuma coluna fixa em NULL)"]
    for s in suspects:
        lines.append(f"- SUSPEITO: {s['tabela']}.{s['coluna']} -> {s['xpath']}")
    for r in over:
        lines.append(f"- LIMITE: {r['tabela']}.{r['coluna']} VARCHAR({r['limite_varchar']}) mas max na amostra = {r['comprimento_max_amostra']} ({r['exemplos_acima_do_limite']})")
    if col.residual_ex:
        top = Counter((r["tabela"], r["coluna"]) for r in col.residual_ex).most_common(10)
        lines.append("- MOJIBAKE RESIDUAL por coluna (detalhe em fase4_mojibake_residual.csv): " +
                     "; ".join(f"{t}.{c}={n}" for (t, c), n in top))
    (args.out_dir / "fase4_resumo_auto.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n".join(lines))
    print(f"\nRelatorios em {args.out_dir}/ (nada foi gravado no banco).")
    return 1 if suspects or over or col.residual else 0


if __name__ == "__main__":
    raise SystemExit(main())
