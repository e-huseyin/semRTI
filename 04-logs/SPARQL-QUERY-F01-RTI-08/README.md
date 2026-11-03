# Rupe Magna: SPARQL queries and results

Query files for *From RTI Acquisition to Semantic Documentation: A FAIR-Oriented Workflow at Rupe Magna*.

The queries were reconstructed against the graph analysed in the article. They are not presented as the original archived query strings.

## Contents

- `Q1_acquisition_settings.sparql`: documented figure and acquisition measurements; 4 result rows.
- `Q2_processing_chain.sparql`: source-image observations joined to RAW-development and RTI-fitting activities; 48 result rows.
- `Q3_distributions_licences.sparql`: distribution records, formats and recorded licences; 3 result rows.
- `Q4_processing_parameters_optional.sparql`: the additional processing/export-parameter check; 7 result rows.
- `*_results.csv`: the corresponding query results.
- `run_rti08_queries.py`: a runner for all four queries.

Q1–Q3 correspond to the three retrieval questions in the article. Q4 supports the additional processing/export-parameter check in the evaluation.

## Running the queries

Python 3 and `rdflib` are required. The input RDF graph is not included in this folder; use the graph analysed in the article. Results from a different graph may differ.

Run:

```sh
python3 run_rti08_queries.py "/path/to/rupe-magna-knowledge-graph.ttl"
```

The runner reads the graph and creates or replaces the result CSV files in its own folder. It does not modify the input graph.

## Interpretation

The Q2 results link 48 observations to a shared collection-level processing chain; they do not independently verify 48 individual RAW-to-JPG conversions. The queries retrieve relationships and values asserted in the graph. Their results alone do not independently establish that every recorded processing activity occurred or that the published files satisfy all recorded properties.
