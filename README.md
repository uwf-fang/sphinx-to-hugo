# Sphinx to Hugo — migration pilot

A small, local research prototype that uses Sphinx's resolved document trees and `sphinx-markdown-builder` to produce Hugo-oriented Markdown. This is a supported-subset experiment, not a complete migration utility.

## What the pilot established

The upstream builder handles much of the conversion already: code, resolved document and label links, math, tables, glossaries, and expanded includes. In version 0.6.11, the fixture's Graphviz nodes and figure captions were omitted with warnings. Its output is a Markdown export, not a complete Hugo site.

The adapter adds front matter and URL mappings, a separate navigation manifest, native Hugo page TOCs, callout shortcodes, assets and download placement, Graphviz SVG generation, captions, and escaping for plain text that would otherwise be interpreted as HTML. It inherits the upstream writer and pins its dependencies because it uses private translator context APIs.

## Setup

Requires Python 3.10+, Hugo, and Graphviz (`dot`) for the end-to-end experiment.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
```

The lock records the environment evaluated in this pilot; the direct dependency declarations also live in `pyproject.toml`. A public release should define and exercise a broader compatibility matrix.

## Run the reusable fixture

```sh
PYTHONPATH=src .venv/bin/python -m sphinx_to_hugo pilot \
  --source examples/typical \
  --out .work/my-comparison
```

This creates separate `upstream/` and `hugo/` outputs and `pilot.json`. The comparison intentionally returns nonzero when the upstream builder warns about unsupported captions and Graphviz. Check each builder's status separately in the report; this does not mean the Hugo adapter failed.

To run just the adapter, including a section URL prefix:

```sh
PYTHONPATH=src .venv/bin/python -m sphinx_to_hugo convert \
  --source examples/typical \
  --out .work/my-conversion \
  --prefix /teaching/

hugo --source .work/my-conversion/hugo \
  --destination public --cacheDir /tmp/sphinx-to-hugo-cache --panicOnWarning
```

Always choose a fresh output directory. The CLI refuses to overwrite output or to nest output inside input. Original source files remain untouched. Each conversion creates:

```text
hugo/
  content/                    # Markdown, title/URL/weight metadata
  data/sphinx_navigation.json # ordered toctrees, hidden flags, captions
  static/_migration/         # images, rendered Graphviz SVG and DOT source
  static/_downloads/         # referenced downloads
  layouts/                   # minimal Hugo verification templates
  hugo.toml                  # verification configuration
  migration.json             # page mapping and adapter findings
  sphinx.log                 # Sphinx diagnostics
pilot.json                   # combined status and warning summary
```

The helper Hugo layout is for verifying migration output; the approved personal-site design remains in the separate `personal-showcase/` repository. Math is preserved as LaTeX, with passthrough configured and a MathJax CDN script in the verification layout. Static build checks do not verify browser-side typesetting or CDN availability.

The installable CLI entry point is also declared in `pyproject.toml`; the documented `PYTHONPATH` form runs directly from source without editable-package setup.

## Conversion policy

| Source construct | Pilot output |
| --- | --- |
| Document title | Hugo front matter; the layout supplies the page H1 |
| Section headings and labels | Markdown heading IDs and anchor shortcodes |
| `toctree` | Sphinx-resolved visible links plus a separate navigation JSON manifest |
| Hidden toctree | Retained in navigation JSON; not printed in page content |
| `contents` | Replaced with the layout's Hugo `.TableOfContents` |
| `doc`, `ref`, `term` | Resolved links to generated routes and anchors |
| Notes and warnings | A supplied Hugo callout shortcode |
| Inline and display math | Dollar-delimited LaTeX and Hugo passthrough |
| Code, includes, literalinclude selections | Markdown code fences and expanded content |
| Simple list tables | Markdown tables |
| Glossaries | Definition lists and stable term anchors |
| Images, figures, downloads | Copied static assets, captions, and adjusted links |
| Graphviz | Rendered SVG plus preserved DOT source; requires `dot` |
| Raw content or unknown writer nodes | Explicit error finding and preserved review text |

Sphinx parsing and unresolved-reference warnings cause failure through `-W --keep-going`. Conversion may leave partial output on failure for inspection. A successful adapter build alone is not a guarantee of complete content fidelity; render and inspect the results too.

## Important limits

- By default, the CLI supplies a minimal, isolated Sphinx configuration. Use `--config-dir /path/to/trusted/project/source` to load its original `conf.py`, MyST sources, substitutions, extensions, and exclude rules before applying migration overrides. Additional installed extensions can be named with repeatable `--extension` arguments. The optional `project-migration` dependency group installs MyST Parser. Running Sphinx configuration and extensions executes trusted Python code; this is not a sandbox.
- The navigation manifest preserves structure but does not implement a production Hugo sidebar. Page weights are a simple first-occurrence approximation; multiple parents, multiple trees, numbering, and complex ordering require a deliberate navigation policy.
- Embedded TOC placement and per-directive depth are normalized to the verification layout's global TOC policy. Local-only TOCs are flagged for review. Preserve those details in a later policy if needed.
- Equation numbering and numbered references are flagged. Merged cells now use a supplied HTML-table shortcode; image options use a supplied image shortcode. Native Markdown footnotes and multi-paragraph definitions are supported. Advanced tables, citations, autodoc/API documentation, and extension-specific nodes have not received comprehensive fidelity coverage.
- The writer inherits some upstream behavior, including intentional omission of index metadata and transparent container handling. Unsupported source syntax can fail during Sphinx parsing before the adapter sees a node; inspect `sphinx.log` as well as `migration.json`.
- Generated URLs intentionally use a new directory-style policy, optionally under `--prefix`. Legacy `.html` redirects and existing external deep links are not migrated by this pilot.
- Content containing Hugo shortcode delimiters, complex embedded HTML, or multiline table cells needs dedicated review before a general-purpose release. Do not treat the pilot as a lossless converter.

## Checks

```sh
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

The five integration tests cover rendered navigation and link targets, note preservation, code/math/include content, asset and download integrity, prefix routing, unchanged inputs, explicit failure for unresolved/raw content, mixed Markdown/RST project configuration and exclusions, output boundaries, and route-collision detection. The rendering test requires Hugo and Graphviz; it reports a skip when either is absent.

## Repository status

This is an independent local Git repository, initially without commits or a remote. Machine-specific experiments and copied real articles are ignored under `.work/`. Reusable generic fixtures are part of the source. The parent planning repository contains the research findings. No project license has been selected; decide that before a public release. The upstream dependency is MIT-licensed and is installed rather than vendored.

## Full teaching import

The tool was also used to create the separate `../teaching-site/` Hugo repository from 236 active documents. The final full-import stage is `.work/full-06/`; the teaching checkout records source fingerprints, conversion diagnostics, the two known stale-link repairs, and combined-site structural validation. Existing source warnings remain visible rather than suppressed. Prefix-aware outputs place diagrams and downloads inside `static/teaching/` when using `--prefix /teaching/`.
