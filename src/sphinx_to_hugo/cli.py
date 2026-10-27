"""Run isolated upstream and Hugo-adapter builds, retaining reproducible evidence."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit


def write_hugo_support(root):
    files = {
        'hugo.toml': '''baseURL = "https://example.invalid/"
title = "Migration pilot"
disableKinds = ["taxonomy", "term", "RSS", "sitemap"]
[markup.goldmark.extensions.passthrough]
enable = true
[markup.goldmark.extensions.passthrough.delimiters]
block = [['$$', '$$']]
inline = [['$', '$']]
[markup.tableOfContents]
startLevel = 2
endLevel = 4
''',
        'layouts/_default/baseof.html': '''<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ .Title }} · Migration pilot</title>
<style>body{font:17px/1.7 Arial,sans-serif;color:#242a32;background:white;max-width:1050px;margin:40px auto;padding:0 24px}a{color:#163f73}h1,h2,h3{line-height:1.3}main{max-width:760px}pre{background:#f4f7fa;padding:18px;overflow:auto}table{border-collapse:collapse}th,td{border:1px solid #dce2e8;padding:8px 12px}.callout{border-left:3px solid #163f73;padding:12px 20px;margin:24px 0}.callout-warning{border-color:#813d3d}.math{overflow:auto}img{max-width:100%}nav{border-bottom:1px solid #dce2e8;padding-bottom:16px}</style>
<script>window.MathJax={tex:{inlineMath:[['$','$']],displayMath:[['$$','$$']]}};</script>
<script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
</head><body><header><a href="/">Migration pilot</a></header><main>
{{ block "main" . }}{{ end }}</main></body></html>''',
        'layouts/_default/single.html': '''{{ define "main" }}<h1>{{ .Title }}</h1>
{{ if .Params.toc }}<aside aria-label="On this page">{{ .TableOfContents }}</aside>{{ end }}
{{ .Content }}{{ end }}''',
        'layouts/_default/list.html': '''{{ define "main" }}<h1>{{ .Title }}</h1>
{{ if .Params.toc }}<aside aria-label="On this page">{{ .TableOfContents }}</aside>{{ end }}
{{ .Content }}{{ end }}''',
        'layouts/shortcodes/anchor.html': '<span id="{{ .Get 0 }}"></span>',
        'layouts/shortcodes/html-table.html': '<div class="table-scroll">{{ .Inner | safeHTML }}</div>',
        'layouts/shortcodes/image.html': '''<figure class="migration-image align-{{ .Get "align" }}"><img src="{{ .Get "src" }}" alt="{{ .Get "alt" }}"{{ with .Get "width" }} style="width:{{ . | safeCSS }};max-width:100%;height:auto"{{ end }}{{ with .Get "height" }} height="{{ . }}"{{ end }} loading="lazy"></figure>''',
        'layouts/shortcodes/callout.html': '''<aside class="callout callout-{{ .Get "type" }}" aria-label="{{ .Get "type" }}">
<strong>{{ .Get "type" | humanize }}</strong><div>{{ .Page.RenderString (dict "display" "block") .Inner }}</div></aside>''',
    }
    for name, content in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)


def build(source, output, builder, root_doc, prefix, extra_extensions, config_dir=None):
    output.mkdir(parents=True)
    conf = output / '_config'
    conf.mkdir()
    extensions = ['sphinx.ext.graphviz', 'sphinx_to_hugo.extension', *extra_extensions]
    values = dict(project='Conversion pilot', extensions=extensions, root_doc=root_doc,
                  source_suffix={'.rst': 'restructuredtext'}, exclude_patterns=['_build', 'conf.py'],
                  markdown_flavor='github', markdown_anchor_sections=True,
                  markdown_anchor_signatures=True, markdown_uri_doc_suffix='.md',
                  hugo_url_prefix=prefix, nitpicky=True, graphviz_output_format='svg')
    config_text = '\n'.join(f'{key} = {value!r}' for key, value in values.items())
    if config_dir:
        # The supplied configuration is trusted Python, just like a normal Sphinx build.
        config_text = ('import runpy\n'
                       f'globals().update(runpy.run_path({str(config_dir / "conf.py")!r}))\n'
                       f'_original_config_dir = {str(config_dir)!r}\n'
                       'from pathlib import Path\n'
                       'for _path_setting in ("templates_path", "html_static_path", "html_extra_path"):\n'
                       '    if _path_setting in globals():\n'
                       '        globals()[_path_setting] = [str(Path(_original_config_dir) / p) for p in globals()[_path_setting]]\n'
                       'extensions = list(dict.fromkeys(extensions + '
                       f'{extensions!r}))\n'
                       f'root_doc = {root_doc!r}\n'
                       f'hugo_url_prefix = {prefix!r}\n'
                       'markdown_flavor = "github"\n'
                       'markdown_anchor_sections = True\n'
                       'markdown_anchor_signatures = True\n'
                       'markdown_uri_doc_suffix = ".md"\n'
                       'nitpicky = True\n'
                       'graphviz_output_format = "svg"\n')
    (conf / 'conf.py').write_text(config_text)
    environment = os.environ.copy()
    src_package = str(Path(__file__).resolve().parents[1])
    environment['PYTHONPATH'] = src_package + os.pathsep + environment.get('PYTHONPATH', '')
    command = [sys.executable, '-m', 'sphinx', '-b', builder, '-E', '-a', '-n', '-W', '--keep-going',
               '-c', str(conf), '-d', str(output / '_doctrees'), str(source), str(output)]
    result = subprocess.run(command, capture_output=True, text=True, env=environment)
    log = result.stdout + '\n' + result.stderr
    (output / 'sphinx.log').write_text(log)
    return dict(builder=builder, exit_code=result.returncode, log=str(output / 'sphinx.log'),
                warnings=[line for line in log.splitlines() if 'WARNING:' in line or 'ERROR:' in line])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['pilot', 'convert'])
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--root', default='index')
    parser.add_argument('--prefix', default='/')
    parser.add_argument('--extension', action='append', default=[])
    parser.add_argument('--config-dir', type=Path, help='Load a trusted project conf.py before migration overrides.')
    args = parser.parse_args(argv)
    prefix = urlsplit(args.prefix)
    if prefix.scheme or prefix.netloc or prefix.query or prefix.fragment or any(
            part in ('.', '..') for part in prefix.path.split('/')):
        parser.error('Prefix must be a plain URL path, for example /teaching/.')
    source, output = args.source.resolve(), args.out.resolve()
    config_dir = args.config_dir.resolve() if args.config_dir else None
    if config_dir and not (config_dir / 'conf.py').is_file():
        parser.error('Config directory must contain conf.py.')
    if not source.is_dir() or not (source / (args.root + '.rst')).is_file():
        parser.error('Source must contain the root .rst document.')
    if output.is_relative_to(source) or source.is_relative_to(output):
        parser.error('Output and input must be separate, non-overlapping directories.')
    if output.exists():
        parser.error('Output already exists. Choose a fresh directory to prevent stale or overwritten results.')
    output.mkdir(parents=True)
    results = {}
    if args.command == 'pilot':
        results['upstream'] = build(source, output / 'upstream', 'markdown', args.root, args.prefix, args.extension, config_dir)
    results['hugo'] = build(source, output / 'hugo', 'hugo_markdown', args.root, args.prefix, args.extension, config_dir)
    write_hugo_support(output / 'hugo')
    manifest_path = output / 'hugo' / 'migration.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    results['pages'] = len(manifest.get('pages', {}))
    results['findings'] = manifest.get('findings', [])
    results['scope'] = ('Trusted project configuration loaded with migration overrides.' if config_dir else
                        'Minimal isolated Sphinx config; original conf.py is not loaded. Supply additional extensions explicitly.')
    (output / 'pilot.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    return int(any(value.get('exit_code', 0) for value in (results.get('upstream', {}), results['hugo'])) or
               any(item['severity'] == 'error' for item in results['findings']))


if __name__ == '__main__':
    raise SystemExit(main())
