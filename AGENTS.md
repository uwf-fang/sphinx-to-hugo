# Implementation instructions

This is a migration research pilot, with its own local Git repository.

- Reuse Sphinx parsing and reference resolution. Do not write a regex-based RST parser.
- Keep the upstream Markdown builder baseline distinct from the Hugo adapter.
- Treat toctree navigation and a page's heading table of contents as different features.
- Preserve source content and report unsupported nodes, missing assets, warnings, and errors explicitly.
- Never overwrite an input project. Write generated artifacts into a separate output directory.
- Keep author-specific source and machine-specific outputs in ignored `.work/`; keep reusable fixtures generic.
- Source conversion requires trusted Sphinx configuration: `conf.py` and extensions execute Python.
- Document the supported subset, dependency versions, and limitations. Do not claim lossless or complete migration.
- Keep planning and research conclusions in the parent planning repository.
- Do not add a license on the user's behalf, create a remote, publish, or commit without their request.
