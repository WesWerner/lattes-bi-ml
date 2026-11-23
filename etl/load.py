"""CLI e carga em lotes da staging. Apenas um processo escreve no PostgreSQL."""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


from .extractor import extract_file, load_config, load_ddl_limits, make_parser

_WORKER_CONFIG: dict | None = None
_WORKER_LIMITS: dict | None = None


def _init_worker(config: dict, limits: dict) -> None:
    global _WORKER_CONFIG, _WORKER_LIMITS
    _WORKER_CONFIG, _WORKER_LIMITS = config, limits


def _extract_task(task: tuple[str, str]) -> dict:
    if _WORKER_CONFIG is None or _WORKER_LIMITS is None:
        raise RuntimeError("Worker de extração não inicializado")
    path, relative = task
    return extract_file(path, relative, _WORKER_CONFIG, _WORKER_LIMITS)


def _read_tasks(xml_dir: Path, sample_file: Path | None, limit: int | None) -> list[tuple[str, str]]:
    from .text_utils import repair
    if not xml_dir.is_dir():
        raise FileNotFoundError(f"Diretório XML não encontrado: {xml_dir}")
    tasks: list[tuple[str, str]] = []
    if sample_file:
        lines = sample_file.read_text(encoding="utf-8-sig").splitlines()
        for line in lines:
            item = line.strip("\r\n")
            if not item or item.lstrip().startswith("#"):
                continue
            p = xml_dir / item
            if not p.is_file():
                # A lista da amostra pode ter sido salva com nome corrompido; a identidade
                # persistida continua sendo sempre o caminho real do arquivo encontrado.
                alternate = xml_dir / repair(item)[0]
                if alternate.is_file():
                    p = alternate
                else:
                    raise FileNotFoundError(f"Arquivo listado na amostra não encontrado: {item}")
            relative = str(p.relative_to(xml_dir))
            tasks.append((str(p), relative))
    else:
        for p in sorted(xml_dir.rglob("*.xml"), key=lambda x: str(x)):
            tasks.append((str(p), str(p.relative_to(xml_dir))))
    if limit is not None:
        tasks = tasks[:limit]
    if not tasks:
        raise ValueError("Nenhum XML foi selecionado para processamento.")
    return tasks


def _ordered_mappings(config: dict) -> list[dict]:
    by_table = {m["table"]: m for m in config["mappings"] if m["table"] != "stg.curriculo_origem"}
    order = ["stg.pesquisador", "stg.atuacao_profissional"] + [
        m["table"] for m in config["mappings"]
        if m["table"] not in {"stg.curriculo_origem", "stg.pesquisador", "stg.atuacao_profissional"}
    ]
    return [by_table[t] for t in order if t in by_table]


def _table_columns(mapping: dict) -> list[str]:
    return ["arquivo_id", *mapping["fields"].keys()]


def _copy_rows(cur, mapping: dict, arquivo_id: int, rows: list[dict]) -> int:
    from psycopg import sql
    from psycopg.types.json import Jsonb
    if not rows:
        return 0
    table_parts = mapping["table"].split(".")
    columns = _table_columns(mapping)
    statement = sql.SQL("COPY {}.{} ({}) FROM STDIN").format(
        sql.Identifier(table_parts[0]), sql.Identifier(table_parts[1]),
        sql.SQL(", ").join(sql.Identifier(c) for c in columns),
    )
    written = 0
    with cur.copy(statement) as copy:
        for row in rows:
            values = []
            for column in columns:
                value = arquivo_id if column == "arquivo_id" else row.get(column)
                if isinstance(value, dict):
                    value = Jsonb(value)
                values.append(value)
            copy.write_row(values)
            written += 1
    return written


def _ddl_status(statuses: set[str], expected_label: str) -> str:
    match = next((value for value in statuses if value.upper() == expected_label), None)
    if match is None:
        raise RuntimeError(f"O DDL não define o estado de processamento esperado: {expected_label}.")
    return match


def _check_database(conn, config: dict, ddl_limits: dict, statuses: set[str], status_length: int,
                    expected_db: str = "dw_lattes_dev") -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database()")
        dbname = cur.fetchone()[0]
        if dbname != expected_db:
            raise RuntimeError(
                f"Carga bloqueada: banco conectado é {dbname!r}, mas --confirmar-banco é {expected_db!r}. "
                f"Para carregar em outro banco, passe --confirmar-banco com o nome exato dele.")
        cur.execute("""
            SELECT table_name, column_name, data_type, character_maximum_length
            FROM information_schema.columns WHERE table_schema = 'stg'
        """)
        actual = {(t, c): (typ, length) for t, c, typ, length in cur.fetchall()}
        expected_tables = {m["table"].split(".")[1]: m for m in config["mappings"]}
        for table, mapping in expected_tables.items():
            if (table, "arquivo_id") not in actual and table != "curriculo_origem":
                raise RuntimeError(f"Tabela stg.{table} não encontrada ou sem coluna arquivo_id; nenhuma estrutura será criada.")
            if table == "curriculo_origem":
                required = {"arquivo_id", "nome_arquivo", "caminho_relativo", "hash_sha256", "id_lattes_original",
                            "chave_pesquisador", "status_processamento", "tipo_erro", "data_processamento"}
            else:
                required = set(mapping["fields"]) | {"arquivo_id"}
            missing = [c for c in required if (table, c) not in actual]
            if missing:
                raise RuntimeError(f"Colunas ausentes em stg.{table}: {', '.join(sorted(missing))}. Nenhuma estrutura será criada.")
        actual_status = actual.get(("curriculo_origem", "status_processamento"))
        if not actual_status or actual_status[1] != status_length:
            raise RuntimeError("Tamanho de status_processamento no banco diverge do DDL local aprovado.")
        cur.execute("""
            SELECT pg_get_constraintdef(c.oid)
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname='stg' AND t.relname='curriculo_origem' AND c.contype='c'
        """)
        constraint_text = " ".join(row[0] for row in cur.fetchall())
        missing_statuses = [s for s in statuses if f"'{s}'" not in constraint_text]
        if missing_statuses:
            raise RuntimeError("CHECK de status_processamento no banco diverge do DDL local aprovado.")
        for table, cols in ddl_limits.items():
            short = table.split(".")[1]
            for col, limit in cols.items():
                if limit is None:
                    continue
                got = actual.get((short, col))
                if got and got[1] != limit:
                    raise RuntimeError(f"Limite divergente em stg.{short}.{col}: DDL={limit}, banco={got[1]}.")


def _db_kwargs() -> dict:
    required = ["PGDATABASE", "PGUSER", "PGPASSWORD"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError("Configure as variáveis de ambiente: " + ", ".join(missing))
    kwargs = {"dbname": os.environ["PGDATABASE"], "user": os.environ["PGUSER"],
              "password": os.environ["PGPASSWORD"], "host": os.getenv("PGHOST", "localhost")}
    if os.getenv("PGPORT"):
        kwargs["port"] = int(os.environ["PGPORT"])
    return kwargs


def _write_error_log(entries: list[dict], log_path: Path) -> None:
    if not entries:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not log_path.exists() or log_path.stat().st_size == 0
    with log_path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["arquivo_id", "caminho_relativo", "tipo_erro", "detalhe"])
        if new_file:
            writer.writeheader()
        writer.writerows(entries)


def _record_origin(cur, result: dict, statuses: set[str], status_length: int) -> int:
    from psycopg import sql
    pending = _ddl_status(statuses, "PENDENTE")
    if len(pending) > status_length:
        raise RuntimeError("O estado PENDENTE excede o tamanho definido no DDL.")
    cur.execute("SELECT arquivo_id, status_processamento, hash_sha256 FROM stg.curriculo_origem WHERE caminho_relativo=%s",
                (result["caminho_relativo"],))
    old = cur.fetchone()
    if old and old[1] == _ddl_status(statuses, "PROCESSADO") and old[2] == result["hash_sha256"]:
        return old[0]
    if old:
        arquivo_id = old[0]
        # Exclusão restrita ao arquivo_id atual, dentro da transação do lote.
        for mapping in _ordered_mappings_from_current:
            table = mapping["table"].split(".")[1]
            cur.execute(sql.SQL("DELETE FROM stg.{} WHERE arquivo_id=%s").format(sql.Identifier(table)), (arquivo_id,))
        cur.execute("""
            UPDATE stg.curriculo_origem
            SET nome_arquivo=%s, hash_sha256=%s, id_lattes_original=%s, chave_pesquisador=%s,
                status_processamento=%s, tipo_erro=NULL, data_processamento=NULL
            WHERE arquivo_id=%s
        """, (result["nome_arquivo"], result["hash_sha256"], result["id_lattes_original"],
              result["chave_pesquisador"], pending, arquivo_id))
        return arquivo_id
    cur.execute("""
        INSERT INTO stg.curriculo_origem
            (nome_arquivo, caminho_relativo, hash_sha256, id_lattes_original, chave_pesquisador, status_processamento)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING arquivo_id
    """, (result["nome_arquivo"], result["caminho_relativo"], result["hash_sha256"],
          result["id_lattes_original"], result["chave_pesquisador"], pending))
    return cur.fetchone()[0]


_ordered_mappings_from_current: list[dict] = []


def _load_batch(conn, batch: list[dict], config: dict, statuses: set[str], status_length: int,
                log_path: Path) -> tuple[Counter, Counter, Counter, list[dict]]:
    global _ordered_mappings_from_current
    from psycopg import sql
    mappings = _ordered_mappings(config)
    _ordered_mappings_from_current = mappings
    pending_status = _ddl_status(statuses, "PENDENTE")
    processed_status = _ddl_status(statuses, "PROCESSADO")
    error_status = _ddl_status(statuses, "ERRO")
    extracted = Counter()
    loaded = Counter()
    file_statuses = Counter()
    errors_to_log: list[dict] = []
    comparisons: list[tuple[int, dict, bool]] = []  # arquivo_id, extraction result, was skipped
    for result in batch:
        if result["status"] == "OK":
            for table, rows in result["rows"].items():
                extracted[table] += len(rows)
    with conn.transaction():
        with conn.cursor() as cur:
            for ix, result in enumerate(batch):
                savepoint = f"file_{ix}"
                cur.execute(sql.SQL("SAVEPOINT {}").format(sql.Identifier(savepoint)))
                try:
                    cur.execute("SELECT arquivo_id, status_processamento, hash_sha256 FROM stg.curriculo_origem WHERE caminho_relativo=%s",
                                (result["caminho_relativo"],))
                    old = cur.fetchone()
                    if old and old[1] == _ddl_status(statuses, "PROCESSADO") and old[2] == result["hash_sha256"]:
                        arquivo_id = old[0]
                        comparisons.append((arquivo_id, result, True))
                        file_statuses["PULADO"] += 1
                        cur.execute(sql.SQL("RELEASE SAVEPOINT {}").format(sql.Identifier(savepoint)))
                        continue
                    arquivo_id = _record_origin(cur, result, statuses, status_length)
                    if result["status"] == "ERRO":
                        cur.execute("UPDATE stg.curriculo_origem SET status_processamento=%s, tipo_erro=%s, data_processamento=%s WHERE arquivo_id=%s",
                                    (error_status, result["error"], datetime.now(timezone.utc), arquivo_id))
                        comparisons.append((arquivo_id, {**result, "rows": {}}, False))
                        file_statuses["ERRO"] += 1
                        errors_to_log.append({"arquivo_id": arquivo_id, "caminho_relativo": result["caminho_relativo"],
                                              "tipo_erro": result["error"], "detalhe": result["error"]})
                        cur.execute(sql.SQL("RELEASE SAVEPOINT {}").format(sql.Identifier(savepoint)))
                        continue
                    insert_sp = f"insert_{ix}"
                    cur.execute(sql.SQL("SAVEPOINT {}").format(sql.Identifier(insert_sp)))
                    try:
                        file_written = Counter()
                        for mapping in mappings:
                            rows = result["rows"].get(mapping["table"], [])
                            written = _copy_rows(cur, mapping, arquivo_id, rows)
                            file_written[mapping["table"]] += written
                        cur.execute("UPDATE stg.curriculo_origem SET status_processamento=%s, tipo_erro=NULL, data_processamento=%s WHERE arquivo_id=%s",
                                    (processed_status, datetime.now(timezone.utc), arquivo_id))
                        cur.execute(sql.SQL("RELEASE SAVEPOINT {}").format(sql.Identifier(insert_sp)))
                        loaded.update(file_written)
                        comparisons.append((arquivo_id, result, False))
                        file_statuses["PROCESSADO"] += 1
                        for warning in result["warnings"]:
                            # Avisos sem valores de XML para não expor dados pessoais.
                            errors_to_log.append({"arquivo_id": arquivo_id, "caminho_relativo": result["caminho_relativo"],
                                                  "tipo_erro": "AVISO", "detalhe": warning})
                    except Exception as exc:
                        cur.execute(sql.SQL("ROLLBACK TO SAVEPOINT {}").format(sql.Identifier(insert_sp)))
                        cur.execute(sql.SQL("RELEASE SAVEPOINT {}").format(sql.Identifier(insert_sp)))
                        safe_error = f"ERRO_CARGA:{type(exc).__name__}"
                        cur.execute("UPDATE stg.curriculo_origem SET status_processamento=%s, tipo_erro=%s, data_processamento=%s WHERE arquivo_id=%s",
                                    (error_status, safe_error, datetime.now(timezone.utc), arquivo_id))
                        comparisons.append((arquivo_id, {**result, "rows": {}}, False))
                        file_statuses["ERRO"] += 1
                        errors_to_log.append({"arquivo_id": arquivo_id, "caminho_relativo": result["caminho_relativo"],
                                              "tipo_erro": safe_error, "detalhe": safe_error})
                    cur.execute(sql.SQL("RELEASE SAVEPOINT {}").format(sql.Identifier(savepoint)))
                except Exception:
                    cur.execute(sql.SQL("ROLLBACK TO SAVEPOINT {}").format(sql.Identifier(savepoint)))
                    cur.execute(sql.SQL("RELEASE SAVEPOINT {}").format(sql.Identifier(savepoint)))
                    raise
            # Conferência física da origem (uma linha por XML) e das filhas por arquivo.
            ids = [arquivo_id for arquivo_id, _result, _skipped in comparisons]
            cur.execute("SELECT arquivo_id, count(*) FROM stg.curriculo_origem WHERE arquivo_id = ANY(%s) GROUP BY arquivo_id", (ids,))
            origin_counts = dict(cur.fetchall())
            for arquivo_id, _result, _skipped in comparisons:
                if origin_counts.get(arquivo_id, 0) != 1:
                    raise RuntimeError(f"Contagem divergente em stg.curriculo_origem, arquivo_id={arquivo_id}: esperado=1, banco={origin_counts.get(arquivo_id, 0)}.")
            for mapping in mappings:
                table = mapping["table"].split(".")[1]
                cur.execute(sql.SQL("SELECT arquivo_id, count(*) FROM stg.{} WHERE arquivo_id = ANY(%s) GROUP BY arquivo_id").format(sql.Identifier(table)), (ids,))
                actual_counts = dict(cur.fetchall())
                for arquivo_id, result, skipped in comparisons:
                    expected_count = len(result.get("rows", {}).get(mapping["table"], [])) if result["status"] == "OK" else 0
                    actual_count = actual_counts.get(arquivo_id, 0)
                    if actual_count != expected_count:
                        raise RuntimeError(f"Contagem divergente em stg.{table}, arquivo_id={arquivo_id}: esperado={expected_count}, banco={actual_count}.")
    _write_error_log(errors_to_log, log_path)
    return extracted, loaded, file_statuses, errors_to_log


def _print_pilot_examples(conn, xml_root: Path, tasks: list[tuple[str, str]], config: dict,
                         ddl_limits: dict[str, dict[str, int | None]]) -> None:
    """Compara até cinco artigos e cinco projetos gravados com o XML original; saída só no console."""
    import io
    from lxml import etree
    from psycopg import sql

    rel_paths = [rel for _path, rel in tasks]
    cache: dict[str, dict] = {}
    print("\nComparação de amostra com XML de origem (até 5 registros por tabela; não é gravada em arquivo):")
    for table_name in ("stg.artigos", "stg.projetos_pesquisa"):
        mapping = next((m for m in config["mappings"] if m["table"] == table_name), None)
        if not mapping:
            continue
        table = table_name.split(".")[1]
        columns = list(mapping["fields"])
        query = sql.SQL("SELECT c.caminho_relativo, t.arquivo_id, {} FROM stg.{} AS t "
                        "JOIN stg.curriculo_origem AS c USING (arquivo_id) "
                        "WHERE c.caminho_relativo = ANY(%s) "
                        "ORDER BY c.caminho_relativo, t.ordem_xml LIMIT 5").format(
            sql.SQL(", ").join(sql.SQL("t.{}").format(sql.Identifier(c)) for c in columns),
            sql.Identifier(table),
        )
        with conn.cursor() as cur:
            cur.execute(query, (rel_paths,))
            records = cur.fetchall()
        if not records:
            print(f"  {table_name}: nenhum registro encontrado entre os arquivos selecionados.")
            continue
        print(f"  {table_name}:")
        for record in records:
            relative = record[0]
            values = dict(zip(columns, record[2:]))
            if relative not in cache:
                cache[relative] = extract_file(xml_root / relative, relative, config, ddl_limits)
            extracted = cache[relative]
            rows = extracted.get("rows", {}).get(table_name, [])
            order = values.get("ordem_xml")
            expected = next((r for r in rows if r.get("ordem_xml") == order), None)
            if expected is None:
                mismatches = ["registro não localizado na extração do XML"]
            else:
                mismatches = [c for c in columns if values.get(c) != expected.get(c)]
            print(f"    arquivo={relative!r}, arquivo_id={record[1]}, ordem_xml={order}, "
                  f"comparação={'OK' if not mismatches else 'DIVERGENTE'}" +
                  (f", diferenças={mismatches}" if mismatches else ""))
            try:
                raw = (xml_root / relative).read_bytes()
                root = etree.parse(io.BytesIO(raw), make_parser()).getroot()
                source_path = mapping["source"]["path"]
                nodes = [root] if source_path == "." else root.xpath("./" + source_path)
                if order and 1 <= order <= len(nodes):
                    snippet = etree.tostring(nodes[order - 1], encoding="unicode", with_tail=False)
                    print(f"      XML: {snippet[:500]}")
            except (OSError, etree.XMLSyntaxError, IndexError) as exc:
                print(f"      XML: não foi possível gerar trecho ({type(exc).__name__}).")


def run(args: argparse.Namespace) -> int:
    root = Path(args.xml_dir).expanduser().resolve()
    config = load_config(Path(args.mapping))
    ddl_limits, statuses, status_length = load_ddl_limits(Path(args.stg_ddl))
    tasks = _read_tasks(root, Path(args.sample_file) if args.sample_file else None, args.limit)
    print(f"Arquivos selecionados: {len(tasks)} | workers={args.workers} | lote={args.lote}")
    print(f"Status lidos do DDL: {', '.join(sorted(statuses))}; VARCHAR({status_length})")
    total_rows = Counter()
    total_loaded = Counter()
    total_status = Counter()
    errors = 0
    conn = None
    if not args.dry_run:
        import psycopg
        conn = psycopg.connect(**_db_kwargs(), autocommit=True)
        _check_database(conn, config, ddl_limits, statuses, status_length, args.confirmar_banco)
        print(f"Verificação do banco aprovada: {args.confirmar_banco}, tabelas/colunas/limites/CHECK existentes; nenhuma estrutura alterada.")
    try:
        with ProcessPoolExecutor(max_workers=args.workers, initializer=_init_worker,
                                 initargs=(config, ddl_limits)) as pool:
            started = time.monotonic()
            for start in range(0, len(tasks), args.lote):
                batch_tasks = tasks[start:start + args.lote]
                results = list(pool.map(_extract_task, batch_tasks))
                if args.dry_run:
                    total_rows["stg.curriculo_origem"] += len(results)
                    for result in results:
                        if result["status"] == "ERRO":
                            errors += 1
                        else:
                            for table, rows in result["rows"].items():
                                total_rows[table] += len(rows)
                            total_status["EXTRAIDO"] += 1
                            total_status["AVISOS"] += len(result["warnings"])
                    elapsed = max(time.monotonic() - started, 0.001)
                    done = min(start + len(results), len(tasks))
                    rate = done / elapsed
                    eta = (len(tasks) - done) / rate if rate else 0
                    print(f"Dry-run: {done}/{len(tasks)} arquivos | {rate:.1f} arquivos/s | ETA {eta:.0f}s")
                    continue
                assert conn is not None
                extracted, loaded, statuses_batch, _ = _load_batch(
                    conn, results, config, statuses, status_length, Path(args.error_log))
                total_rows.update(extracted)
                total_rows["stg.curriculo_origem"] += len(results)
                total_loaded.update(loaded)
                total_loaded["stg.curriculo_origem"] += statuses_batch["PROCESSADO"] + statuses_batch["ERRO"]
                total_status.update(statuses_batch)
                errors += statuses_batch["ERRO"]
                elapsed = max(time.monotonic() - started, 0.001)
                done = min(start + len(results), len(tasks))
                rate = done / elapsed
                eta = (len(tasks) - done) / rate if rate else 0
                print(f"Lote {start // args.lote + 1}: {len(results)} arquivos | "
                      f"processados={statuses_batch['PROCESSADO']} pulados={statuses_batch['PULADO']} "
                      f"erros={statuses_batch['ERRO']} | {rate:.1f} arquivos/s | ETA {eta:.0f}s")
            if conn is not None and args.sample_file and not args.dry_run:
                _print_pilot_examples(conn, root, tasks, config, ddl_limits)
    finally:
        if conn is not None:
            conn.close()
    if args.dry_run:
        print("\nDRY-RUN: nenhuma conexão ou gravação no banco foi realizada.")
    print("\nContagens por tabela:")
    for mapping in config["mappings"]:
        table = mapping["table"]
        if args.dry_run:
            print(f"  {table}: {total_rows[table]}")
        elif table == "stg.curriculo_origem":
            print(f"  {table}: arquivos verificados={total_rows[table]} | registros novos/atualizados={total_loaded[table]}")
        else:
            print(f"  {table}: extraídos={total_rows[table]} | gravados por COPY={total_loaded[table]}")
    print(f"Arquivos: {dict(total_status)} | erros={errors}")
    return 1 if errors else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extrai XMLs Lattes e carrega em stg por lotes.")
    parser.add_argument("--xml-dir", required=True, help="Diretório raiz dos XMLs")
    parser.add_argument("--lote", type=int, default=500, help="Quantidade de arquivos por transação (padrão 500)")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1), help="Processos de leitura/parse")
    parser.add_argument("--sample-file", help="TXT com caminhos relativos dos XMLs a processar")
    parser.add_argument("--limit", type=int, help="Limita o número de arquivos selecionados")
    parser.add_argument("--dry-run", action="store_true", help="Extrai e conta sem conexão/gravação no banco")
    parser.add_argument("--confirmar-banco", default="dw_lattes_dev",
                        help="Nome exato do banco onde a carga é permitida (padrão dw_lattes_dev; use dw_lattes para a carga final)")
    parser.add_argument("--mapping", default="config/mapeamento.yaml")
    parser.add_argument("--stg-ddl", default="sql/01_stg.sql")
    parser.add_argument("--error-log", default="logs/erros_leitura.csv")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.lote < 1 or args.workers < 1 or (args.limit is not None and args.limit < 1):
        print("--lote, --workers e --limit devem ser positivos.", file=sys.stderr)
        return 2
    try:
        return run(args)
    except Exception as exc:
        # Sem imprimir connection string, senha ou conteúdo XML.
        print(f"FALHA: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
