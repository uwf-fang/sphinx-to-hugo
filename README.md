# Sphinx to Hugo

Convert Sphinx documentation into Hugo Markdown while retaining resolved references, navigation data, assets, and a report of conversion findings. The converter uses Sphinx's document trees and extends `sphinx-markdown-builder`.

This is an early release for a documented subset of Sphinx content. It has been used to migrate a 236-document teaching site. Unsupported constructs and unresolved references produce diagnostics for review. Inspect the generated site before publishing it.

## Install

Requires Python 3.10 or newer. Graphviz (`dot`) is needed to render Graphviz diagrams. Hugo is needed to build and inspect the generated site.

Clone the repository and install the package in a virtual environment

```sh
git clone https://github.com/uwf-fang/sphinx-to-hugo.git
cd sphinx-to-hugo
python3 -m venv .venv
.venv/bin/python -m pip install '.[project-migration]'
.venv/bin/sphinx-to-hugo --version
```

The `project-migration` extra installs MyST Parser for Markdown sources. The direct Sphinx and Markdown-builder dependencies are pinned because the adapter uses translator context APIs from the upstream writer. `requirements-lock.txt` records the original development environment. Installation from `pyproject.toml` lets pip select transitive dependencies compatible with the active Python version.

## Convert a project

```sh
.venv/bin/sphinx-to-hugo convert \
  --source /path/to/docs/source \
  --config-dir /path/to/docs/source \
  --out /path/to/new-conversion \
  --prefix /teaching/
```

`--config-dir` loads the project's `conf.py`, including configured extensions, exclusions, and substitutions. Configuration and extensions execute Python code, as in a regular Sphinx build. Convert only projects whose configuration and extensions you trust.

Choose a fresh output directory outside the input tree. Existing output directories are rejected. Source files are preserved. Failed conversions retain partial output and logs for inspection.

The default root document is `index`. Use `--root guide` for `guide.rst` or a configured `guide.md`. Both reStructuredText and MyST Markdown roots are supported. Install any additional extensions required by the source project in the conversion environment.

Without `--config-dir`, the converter uses a minimal Sphinx configuration. Additional extensions can be supplied with repeated `--extension` arguments. For example, a Markdown-only source can use `--extension myst_parser` after installing the extra.

## Inspect the output

Each conversion creates this structure

```text
new-conversion/
  hugo/
    content/                    # Markdown and Hugo front matter
    data/sphinx_navigation.json # Sphinx toctree relationships
    static/                     # Preserved assets and downloads
    layouts/                    # Verification templates and shortcodes
    hugo.toml                   # Verification configuration
    migration.json              # Page mappings and adapter findings
    sphinx.log                  # Builder diagnostics
  pilot.json                    # Build status and findings summary
```

The summary filename `pilot.json` is retained for compatibility with earlier local versions. When `--prefix /teaching/` is used, generated content, diagrams, and downloads live under the teaching namespace.

Build and preview the generated Hugo site

```sh
hugo --source /path/to/new-conversion/hugo \
  --cacheDir /tmp/sphinx-to-hugo-cache --panicOnWarning

hugo server --source /path/to/new-conversion/hugo \
  --bind 127.0.0.1 --port 1315 --cacheDir /tmp/sphinx-to-hugo-cache
```

Open the HTTP address printed by Hugo, using `/teaching/` if that was the requested prefix. The supplied templates provide a small verification site. A production design can reuse the generated content, navigation manifest, and shortcodes. Math uses preserved LaTeX and MathJax loaded from a CDN.

Sphinx warnings and adapter error findings produce a nonzero exit status. Review both `pilot.json` and `hugo/sphinx.log`. A successful build still requires content and visual review.

## Supported content

| Source construct | Output |
| --- | --- |
| Titles, sections, and labels | Front matter, heading IDs, and anchor shortcodes |
| `doc`, `ref`, and `term` links | Resolved page routes and anchors |
| Visible and hidden `toctree` entries | Resolved links and a separate navigation manifest |
| `contents` | Hugo page table of contents |
| Notes and warnings | Included callout shortcode |
| Inline and display math | LaTeX and Hugo passthrough settings |
| Code, includes, and literalinclude selections | Code fences and expanded source content |
| Simple tables | Markdown tables |
| Merged table cells | HTML-table shortcode |
| Glossaries and definitions | Definition lists with term anchors |
| Footnotes | Markdown footnotes |
| Images, figures, and downloads | Copied assets, captions, and updated paths |
| Graphviz | Rendered SVG and preserved DOT source |
| Raw content and unknown nodes | Explicit review findings |

The navigation manifest keeps toctrees separate from a page's heading table of contents. It does not supply a production sidebar. Weights use first-occurrence ordering, and complex navigation may need a site-specific policy.

## Conversion limits

- Numbered equations, numbered references, local-only TOCs, and unsupported extension nodes need review. Advanced tables, citations, and autodoc/API documentation have limited coverage.
- Embedded TOC position and depth are normalized to the verification layout's TOC settings.
- Generated pages use directory-style URLs. Legacy `.html` redirects need to be prepared as part of deployment.
- Content containing Hugo shortcode delimiters, complex embedded HTML, or multiline table cells needs additional review.
- A project's installed extensions can affect parsing and output. The generated templates do not reproduce its original Sphinx theme.
- Browser-side math rendering, CDN availability, and every possible Sphinx extension are outside the automated fixture checks.

## Compare with the upstream builder

The repository includes generic fixtures for testing conversion. To produce separate upstream Markdown and Hugo-adapter outputs

```sh
.venv/bin/sphinx-to-hugo pilot \
  --source examples/typical \
  --out /tmp/sphinx-hugo-comparison
```

The comparison may return nonzero because the upstream Markdown builder warns about unsupported figure captions and Graphviz. `pilot.json` records the status of each builder separately.

## Development and packaging

```sh
.venv/bin/python -m pip install '.[project-migration,dev]'
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*
```

The integration suite checks resolved links and anchors, rendered Hugo output, code and math, includes, asset and download integrity, unchanged inputs, project configuration, Markdown roots, output boundaries, and route collisions. Install Hugo and Graphviz to run the rendering test. CI runs the suite and distribution checks across Python 3.10, 3.12, and 3.14, including a wheel-installed conversion outside the checkout.

Source distributions include the generic fixtures and tests. Local experiments belong in ignored `.work/`. Report reproducible conversion problems through the repository's issue tracker. Include the tool version, relevant diagnostics, and a small example you can share.

## License

MIT, copyright 2026 Xingang (Ian) Fang. See [LICENSE](LICENSE).

Sphinx, `sphinx-markdown-builder`, and other dependencies are installed separately and retain their own licenses. Converted input documents retain their existing ownership and licensing.
