from pathlib import Path
import csv, re

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'config' / 'mapeamento.yaml'
DDL = ROOT / 'sql' / '01_stg.sql'


def inventory_paths(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return {r['caminho_xml'].removeprefix('/CURRICULO-VITAE/') for r in csv.DictReader(f)}


def test_mapping_sources_exist_in_tag_inventory():
    cfg = yaml.safe_load(CONFIG.read_text(encoding='utf-8'))
    inventario = ROOT / 'data' / 'inventarios' / 'tags_xml.csv'
    if not inventario.exists():
        pytest.skip('Inventário de tags não incluído no repositório (data/inventarios/tags_xml.csv).')
    tags = inventory_paths(inventario)
    for m in cfg['mappings']:
        source = m['source']['path']
        assert source == '.' or source in tags, (m['table'], source)


def test_mapping_tables_and_columns_exist_in_staging_ddl():
    cfg = yaml.safe_load(CONFIG.read_text(encoding='utf-8'))
    ddl = DDL.read_text(encoding='utf-8')
    tables = {}
    for match in re.finditer(r'CREATE TABLE IF NOT EXISTS\s+(stg\.[a-z_]+)\s*\((.*?)\n\);', ddl, re.S | re.I):
        table, body = match.groups()
        cols = set()
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith('--') or line.upper().startswith(('CONSTRAINT ', 'PRIMARY KEY', 'UNIQUE ', 'FOREIGN KEY', 'CHECK ')):
                continue
            m = re.match(r'([a-z_][a-z0-9_]*)\s+', line, re.I)
            if m: cols.add(m.group(1))
        tables[table] = cols
    for mapping in cfg['mappings']:
        table = mapping['table']
        assert table in tables, f'missing DDL table {table}'
        for col in mapping['fields']:
            assert col in tables[table], f'missing DDL column {table}.{col}'


def test_author_mappings_sort_by_order_of_authorship():
    cfg = yaml.safe_load(CONFIG.read_text(encoding='utf-8'))
    author_mappings = []
    for mapping in cfg['mappings']:
        for col, spec in mapping.get('fields', {}).items():
            if 'authors' in spec:
                author_mappings.append(spec['authors'])
    assert author_mappings
    assert all(a['order_attribute'] == 'ORDEM-DE-AUTORIA' for a in author_mappings)
    assert all(a['separator'] == '; ' for a in author_mappings)
