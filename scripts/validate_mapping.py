#!/usr/bin/env python3
"""Validate the Phase 2 mapping against structural inventories and optional real XML samples."""
from __future__ import annotations
import argparse, csv, sys
from pathlib import Path
import yaml
from lxml import etree


def read_inventory(path: Path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    return {r['caminho_xml'].removeprefix('/CURRICULO-VITAE/'): {
        'occurrences_total': int(r['ocorrencias_total']),
        'files_with_occurrence': int(r['arquivos_com_ocorrencia']),
        'total_files_analyzed': int(r['total_arquivos_analisados'])
    } for r in rows}


def expected_attribute_paths(mapping):
    base = mapping['source']['path']
    for col, spec in mapping.get('fields', {}).items():
        if 'xpath' in spec:
            xp = spec['xpath'].lstrip('./')
            if '/@' in xp or xp.startswith('@'):
                yield col, (base + '/' if base != '.' else '') + xp
        if 'authors' in spec:
            a = spec['authors']
            prefix = (base + '/' if base != '.' else '') + a['nodes_xpath'] + '/@'
            yield col + '.author_name', prefix + a['name_attribute']
            yield col + '.author_order', prefix + a['order_attribute']


def validate_inventory(config, tags, attrs):
    errors, warnings = [], []
    expected_files = config['source']['expected_files']
    for m in config['mappings']:
        table = m['table']
        src = m['source']
        path = src['path']
        if path == '.':
            counts = src['expected_counts']
            if counts['total_files_analyzed'] != expected_files:
                errors.append(f'{table}: root total_files_analyzed differs from expected_files')
        elif path not in tags:
            errors.append(f'{table}: source path missing from tags inventory: {path}')
        elif tags[path] != src['expected_counts']:
            errors.append(f'{table}: expected_counts do not match tags inventory for {path}')
        for col, apath in expected_attribute_paths(m):
            if apath not in attrs:
                errors.append(f'{table}.{col}: attribute path missing from attributes inventory: {apath}')
            else:
                # Compare recorded per-attribute baselines when they are embedded in the YAML.
                field_name = col.split('.')[0]
                spec = m.get('fields', {}).get(field_name, {})
                recorded = spec.get('expected_counts')
                if col.endswith('.author_name'):
                    recorded = spec.get('authors', {}).get('expected_name_counts')
                elif col.endswith('.author_order'):
                    recorded = spec.get('authors', {}).get('expected_order_counts')
                if recorded is not None and recorded != attrs[apath]:
                    errors.append(f'{table}.{col}: expected_counts do not match attributes inventory for {apath}')
    for path, counts in tags.items():
        if counts['total_files_analyzed'] != expected_files:
            errors.append(f'tags inventory has unexpected total_files_analyzed for {path}')
            break
    for path, counts in attrs.items():
        if counts['total_files_analyzed'] != expected_files:
            errors.append(f'attributes inventory has unexpected total_files_analyzed for {path}')
            break
    return errors, warnings


def validate_xml_samples(config, xml_paths):
    errors, warnings = [], []
    if len(xml_paths) < 2:
        warnings.append('XML sample validation skipped: provide at least 2 real XML files (3 recommended).')
        return errors, warnings
    for path in xml_paths:
        try:
            parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True, recover=False)
            tree = etree.parse(str(path), parser)
            root = tree.getroot()
            if etree.QName(root).localname != config['source']['root_element']:
                errors.append(f'{path}: root is {etree.QName(root).localname}, expected {config["source"]["root_element"]}')
                continue
            for m in config['mappings']:
                src = m['source']['path']
                if src == '.':
                    nodes = [root]
                else:
                    try:
                        nodes = root.xpath('./' + src)
                    except etree.XPathError as exc:
                        errors.append(f'{path}: invalid source XPath for {m["table"]}: {exc}')
                        continue
                if not nodes:
                    warnings.append(f'{path}: no nodes for {m["table"]} source path {src} (may be valid for sparse sections)')
                    continue
                # Test each mapped field XPath against at least one record node; optional absent values are allowed.
                for col, spec in m.get('fields', {}).items():
                    if 'xpath' in spec:
                        xp = spec['xpath']
                        try:
                            for node in nodes[:5]:
                                node.xpath('./' + xp if not xp.startswith('@') else xp)
                        except etree.XPathError as exc:
                            errors.append(f'{path}: invalid field XPath {m["table"]}.{col}={xp}: {exc}')
                    if 'authors' in spec:
                        a = spec['authors']
                        try:
                            for node in nodes[:5]:
                                authors = node.xpath('./' + a['nodes_xpath'])
                                for author in authors[:5]:
                                    author.get(a['name_attribute'])
                                    author.get(a['order_attribute'])
                        except (etree.XPathError, TypeError) as exc:
                            errors.append(f'{path}: invalid author mapping {m["table"]}.{col}: {exc}')
        except (OSError, etree.XMLSyntaxError) as exc:
            errors.append(f'{path}: could not parse XML: {exc}')
    return errors, warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', type=Path, default=Path('config/mapeamento.yaml'))
    ap.add_argument('--tags', type=Path, default=Path('data/inventarios/tags_xml.csv'))
    ap.add_argument('--attributes', type=Path, default=Path('data/inventarios/atributos_xml.csv'))
    ap.add_argument('--xml-sample', type=Path, action='append', default=[])
    args = ap.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding='utf-8'))
    for required in [args.tags, args.attributes]:
        if not required.exists():
            print(f'ERROR: inventory file not found: {required}', file=sys.stderr)
            return 2
    tags, attrs = read_inventory(args.tags), read_inventory(args.attributes)
    errors, warnings = validate_inventory(config, tags, attrs)
    xml_errors, xml_warnings = validate_xml_samples(config, args.xml_sample)
    errors.extend(xml_errors); warnings.extend(xml_warnings)
    print(f'Mappings: {len(config["mappings"])}')
    print(f'Expected source files: {config["source"]["expected_files"]:,}')
    print(f'Inventory paths: tags={len(tags):,}, attributes={len(attrs):,}')
    print(f'XML samples checked: {len(args.xml_sample)}')
    print(f'Errors: {len(errors)}; warnings: {len(warnings)}')
    for msg in errors: print('ERROR:', msg)
    for msg in warnings: print('WARNING:', msg)
    return 1 if errors else 0

if __name__ == '__main__':
    raise SystemExit(main())
