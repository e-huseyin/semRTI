#!/usr/bin/env python3
"""Run three reconstructed research queries on the supplied RDF Turtle snapshot.
Usage: python3 run_rti08_queries.py /path/to/rupe-magna-knowledge-graph.ttl
Requires: python3 -m pip install rdflib
Writes one CSV per SELECT in the same folder as this script.
"""
import csv
import sys
from pathlib import Path
from rdflib import Graph

if len(sys.argv) != 2:
    raise SystemExit('Usage: python3 run_rti08_queries.py /path/to/rupe-magna-knowledge-graph.ttl')
source = Path(sys.argv[1]).expanduser()
if not source.is_file():
    raise SystemExit(f'Graph file not found: {source}')
folder = Path(__file__).resolve().parent
graph = Graph()
print(f'Loading RDF graph: {source}')
graph.parse(str(source), format='turtle')
print(f'{len(graph):,} triples loaded')
for file in sorted(folder.glob('Q*.sparql')):
    result = graph.query(file.read_text(encoding='utf-8'))
    fields = [str(v) for v in result.vars]
    output = folder / f'{file.stem}_results.csv'
    rows = list(result)
    with output.open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(fields)
        for row in rows:
            writer.writerow(['' if value is None else str(value) for value in row])
    print(f'{file.name}: {len(rows)} rows -> {output.name}')
