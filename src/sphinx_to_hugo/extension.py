"""A narrow Hugo adapter over sphinx-markdown-builder's resolved doctrees.

The upstream translator is an installed dependency, not vendored source.
This pilot deliberately relies on its private context API; versions are pinned.
"""
from __future__ import annotations

import hashlib
import html
import json
import posixpath
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote, urlsplit

from docutils import nodes
from sphinx import addnodes
from sphinx.util import logging
from sphinx_markdown_builder.builder import MarkdownBuilder
from sphinx_markdown_builder.contexts import SubContext, SubContextParams, TitleContext, WrappedContext
from sphinx_markdown_builder.escape import escape_markdown_chars
from sphinx_markdown_builder.translator import MarkdownTranslator, pushing_context, pushing_status

from sphinx_to_hugo import __version__

logger = logging.getLogger(__name__)


class HugoHeading(TitleContext):
    def __init__(self, level, anchor):
        super().__init__(level)
        self.anchor = anchor

    def make(self):
        return super().make() + (f" {{#{self.anchor}}}" if self.anchor else "")


class HugoDefinition(SubContext):
    def make(self):
        lines = super().make().strip().splitlines()
        if not lines:
            return ''
        return ': ' + lines[0] + ''.join('\n' + ('    ' + line if line else '') for line in lines[1:])


class HugoTranslator(MarkdownTranslator):
    def __init__(self, document, builder):
        super().__init__(document, builder)
        self.anchors = set()
        self.section_ids = {value for section in document.findall(nodes.section)
                            for value in section.get('ids', [])}

    def dispatch_visit(self, node):
        # Sphinx can attach an explicit label to a paragraph, list, or other block.
        if isinstance(node, nodes.Element) and not isinstance(node, (
                nodes.section, nodes.target, nodes.term, nodes.literal_block,
                nodes.math_block, nodes.footnote, nodes.footnote_reference)):
            for anchor in node.get('ids', []):
                self._add_anchor(anchor)
        return super().dispatch_visit(node)

    def _fetch_ref_uri(self, node):
        uri = super()._fetch_ref_uri(node)
        parts = urlsplit(uri)
        if parts.scheme or parts.netloc or not parts.path or node.get('internal'):
            return uri
        source_root = Path(self.builder.srcdir).resolve()
        candidates = [source_root / posixpath.dirname(self.builder.current_doc_name) / parts.path,
                      source_root / parts.path.lstrip('/')]
        source = next((p.resolve() for p in candidates if p.is_file() and p.resolve().is_relative_to(source_root)), None)
        if source and source.suffix not in ('.rst', '.md'):
            relative = source.relative_to(source_root).as_posix()
            target = self.builder.asset_path(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            return self.builder.asset_uri(relative) + ('?' + parts.query if parts.query else '') + ('#' + parts.fragment if parts.fragment else '')
        return uri

    def visit_Text(self, node):
        text = node.astext().replace('\r', '')
        if not self.status.preserve_line_breaks:
            text = text.replace('\n', ' ')
        if self.status.escape_text:
            text = html.escape(escape_markdown_chars(text), quote=False)
            for character in '[]|$#':
                text = text.replace(character, '\\' + character)
        self.add(text)

    def visit_literal(self, node):
        text = node.astext()
        fence = '`' * max(1, 1 + max((len(x) for x in re.findall(r'`+', text)), default=0))
        padding = ' ' if text.startswith('`') or text.endswith('`') else ''
        self.add(fence + padding + text + padding + fence)
        raise nodes.SkipNode

    def visit_literal_block(self, node):
        text = node.astext()
        fence = '`' * max(3, 1 + max((len(x) for x in re.findall(r'`+', text)), default=0))
        language = node.get('language', '')
        for anchor in node.get('ids', []):
            self._add_anchor(anchor)
        self.add(f'{fence}{language}\n{text}\n{fence}', prefix_eol=2, suffix_eol=2)
        raise nodes.SkipNode

    def _add_anchor(self, anchor):
        if anchor and anchor not in self.anchors:
            self.add('{{< anchor ' + json.dumps(anchor) + ' >}}', prefix_eol=2, suffix_eol=2)
            self.anchors.add(anchor)

    @pushing_status
    def visit_section(self, node):
        self.ensure_eol(2)
        self._push_status(section_level=self.status.section_level + 1)

    def visit_title(self, node):
        if isinstance(node.parent, nodes.section):
            ids = node.parent.get('ids', [])
            if node.get('hugo_page_title'):
                for anchor in ids:
                    self._add_anchor(anchor)
                raise nodes.SkipNode
            for anchor in ids[1:]:
                self._add_anchor(anchor)
            self._push_context(HugoHeading(self.status.section_level, ids[0] if ids else ''))
            self.anchors.update(ids)
        else:
            # Table captions and toctree captions are not document headings.
            self._push_context(WrappedContext('**', '**', params=SubContextParams(2, 2)))

    def depart_title(self, node):
        self._pop_context()

    def visit_footnote_reference(self, node):
        self.add('[^' + node['refid'] + ']')
        raise nodes.SkipNode

    def visit_footnote(self, node):
        self._push_context(SubContext())

    def depart_footnote(self, node):
        text = self.ctx.make().strip()
        self._ctx_queue.pop()
        identifier = node['ids'][0]
        self.add('[^' + identifier + ']: ' + text.replace('\n', '\n    '), prefix_eol=2, suffix_eol=2)

    def visit_label(self, node):
        if isinstance(node.parent, nodes.footnote):
            raise nodes.SkipNode
        super().visit_label(node)

    @pushing_context
    def visit_line(self, node):
        self._push_context(WrappedContext('', '  ', params=SubContextParams(1, 1)))

    def depart_line(self, node):
        self._pop_context()

    @pushing_context
    def visit_definition(self, node):
        self._push_context(HugoDefinition(SubContextParams(1, 2)))

    def visit_target(self, node):
        # A refid identifies a target emitted on a section, not another anchor.
        if 'refuri' in node or node.get('refid') in self.section_ids:
            return
        for anchor in node.get('ids', []):
            self._add_anchor(anchor)

    @pushing_context
    def visit_note(self, node):
        kind = node.tagname
        self._push_context(WrappedContext(
            '{{< callout type=' + json.dumps(kind) + ' >}}\n',
            '\n{{< /callout >}}', params=SubContextParams(2, 2)))

    visit_warning = visit_note
    visit_important = visit_note
    visit_tip = visit_note
    visit_caution = visit_note
    visit_attention = visit_note
    visit_danger = visit_note
    visit_error = visit_note
    visit_hint = visit_note
    visit_admonition = visit_note

    @pushing_context
    @pushing_status
    def visit_topic(self, node):
        if 'contents' in node.get('classes', []):
            self.builder.record('info', 'page-toc', 'Replaced embedded contents with Hugo page TOC.', node)
            if 'local' in node.get('classes', []):
                self.builder.record('warning', 'local-toc', 'Local-only TOC scope requires review.', node)
            raise nodes.SkipNode
        super().visit_topic(node)

    @pushing_context
    def visit_download_reference(self, node):
        if 'refuri' in node:
            uri = node['refuri']
        elif 'filename' in node:
            uri = self.builder.asset_uri('_downloads/' + node['filename'])
        else:
            uri = node.get('reftarget', '')
            self.builder.record('error', 'missing-download', f'Unresolved download: {uri}', node)
        self._push_context(WrappedContext('[', f']({uri})'))

    def visit_image(self, node):
        uri = node['uri']
        if not urlsplit(uri).scheme and not uri.startswith('//'):
            uri = self.builder.copy_asset(uri, node)
        if any(node.get(key) for key in ('width', 'height', 'scale', 'align')):
            options = {'src': uri, 'alt': node.get('alt', 'image')}
            options.update({key: str(node[key]) for key in ('width', 'height', 'scale', 'align') if node.get(key)})
            arguments = ' '.join(key + '=' + json.dumps(value) for key, value in options.items())
            self.add('{{< image ' + arguments + ' >}}', prefix_eol=2, suffix_eol=2)
            return
        alt = node.get('alt', 'image').replace('[', '\\[').replace(']', '\\]')
        self.add(f'![{alt}](<{uri}>)', prefix_eol=1, suffix_eol=1)

    @pushing_context
    def visit_caption(self, node):
        self._push_context(WrappedContext('*', '*', params=SubContextParams(1, 2)))

    def visit_math_block(self, node):
        for anchor in node.get('ids', []):
            self._add_anchor(anchor)
        if node.get('number'):
            self.builder.record('warning', 'equation-numbering', 'Equation numbering needs a Hugo policy.', node)
        super().visit_math_block(node)

    def visit_graphviz(self, node):
        code = node['code']
        digest = hashlib.sha256(code.encode()).hexdigest()[:16]
        target = self.builder.asset_path('_migration/' + f'graph-{digest}')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.with_suffix('.dot').write_text(code)
        dot = shutil.which('dot')
        if not dot:
            self.builder.record('error', 'graphviz-missing', 'Install Graphviz to render the preserved DOT source.', node)
            self.add(f'```dot\n{code}\n```', prefix_eol=2, suffix_eol=2)
        else:
            try:
                subprocess.run([dot, '-Tsvg', '-o', str(target.with_suffix('.svg'))],
                               input=code, text=True, check=True, capture_output=True, timeout=30)
                uri = self.builder.asset_uri('_migration/' + target.name + '.svg')
                self.add(f'![Graphviz diagram]({uri})', prefix_eol=2, suffix_eol=2)
            except (subprocess.SubprocessError, OSError) as error:
                self.builder.record('error', 'graphviz-failed', str(error), node)
                self.add(f'```dot\n{code}\n```', prefix_eol=2, suffix_eol=2)
        raise nodes.SkipNode

    def visit_raw(self, node):
        self.builder.record('error', 'raw-content', 'Raw content retained as code for manual review.', node)
        self.add('```text\n' + node.astext() + '\n```', prefix_eol=2, suffix_eol=2)
        raise nodes.SkipNode

    def unknown_visit(self, node):
        self.builder.record('error', 'unsupported-node', f'Unsupported node: {node.tagname}', node)
        self.add('**Migration review required:** `' + node.tagname + '`\n\n' +
                 '```text\n' + node.astext() + '\n```', prefix_eol=2, suffix_eol=2)
        raise nodes.SkipNode

    def unknown_departure(self, node):
        pass

    def visit_table(self, node):
        if not any(cell.get('morerows') or cell.get('morecols') for cell in node.findall(nodes.entry)):
            super().visit_table(node)
            return

        def render(part):
            if isinstance(part, nodes.Text):
                return html.escape(part.astext())
            children = ''.join(render(child) for child in part.children)
            tag = part.tagname
            if tag in ('colspec',):
                return ''
            if tag == 'entry':
                attrs = ''
                if part.get('morerows'):
                    attrs += f' rowspan="{part["morerows"] + 1}"'
                if part.get('morecols'):
                    attrs += f' colspan="{part["morecols"] + 1}"'
                return '<td' + attrs + '>' + children + '</td>'
            if tag == 'reference':
                return '<a href="' + html.escape(self._fetch_ref_uri(part), quote=True) + '">' + children + '</a>'
            if tag == 'math':
                return '$' + html.escape(part.astext()) + '$'
            tags = {'table': 'table', 'thead': 'thead', 'tbody': 'tbody', 'row': 'tr',
                    'paragraph': 'p', 'strong': 'strong', 'emphasis': 'em', 'literal': 'code', 'title': 'caption'}
            if tag in tags:
                return '<' + tags[tag] + '>' + children + '</' + tags[tag] + '>'
            if tag not in ('tgroup',):
                self.builder.record('warning', 'complex-table-node', f'Table node flattened: {tag}', part)
            return children

        self.add('{{< html-table >}}\n' + render(node) + '\n{{< /html-table >}}', prefix_eol=2, suffix_eol=2)
        self.builder.record('info', 'merged-table', 'Preserved merged cells with a Hugo HTML-table shortcode.', node)
        raise nodes.SkipNode

    def depart_table(self, node):
        self._pop_context()


class HugoBuilder(MarkdownBuilder):
    name = 'hugo_markdown'
    default_translator_class = HugoTranslator
    allow_parallel = False
    epilog = 'Hugo migration artifacts are in %(outdir)s.'

    def init(self):
        super().init()
        self.findings = []
        self.navigation = {}
        self.page_manifest = {}
        self.weights = {}

    def record(self, severity, feature, message, node=None):
        finding = dict(severity=severity, feature=feature, message=message,
                       document=self.current_doc_name,
                       line=getattr(node, 'line', None))
        self.findings.append(finding)
        if severity in ('warning', 'error'):
            logger.warning('%s: %s', feature, message, location=node,
                           type='sphinx_to_hugo', subtype=feature)

    def get_target_uri(self, docname, typ=None):
        prefix = '/' + self.config.hugo_url_prefix.strip('/')
        route = docname[:-5] if docname.endswith('index') and (docname == 'index' or docname.endswith('/index')) else docname + '/'
        return (prefix.rstrip('/') + '/' + route).replace('//', '/')

    def prepare_writing(self, docnames):
        seen = {}
        for name in sorted(self.env.found_docs):
            url = self.get_target_uri(name)
            if url in seen:
                raise ValueError(f'Hugo route collision: {name} and {seen[url]} -> {url}')
            seen[url] = name
            trees = []
            for tree in self.env.get_doctree(name).findall(addnodes.toctree):
                entries = []
                for position, (title, ref) in enumerate(tree.get('entries', []), 1):
                    external = bool(urlsplit(ref).scheme or ref.startswith('//'))
                    target = name if ref == 'self' else ref
                    if not external and target in self.env.titles:
                        self.weights.setdefault(target, position * 10)
                        title = title or self.env.titles[target].astext()
                    entries.append(dict(title=title or ref, source=ref,
                                        url=ref if external else self.get_target_uri(target)))
                trees.append(dict(caption=tree.get('caption'), hidden=tree.get('hidden', False),
                                  maxdepth=tree.get('maxdepth'), numbered=tree.get('numbered', 0),
                                  entries=entries))
            self.navigation[name] = trees
        super().prepare_writing(docnames)

    def write_doc(self, docname, doctree):
        self.current_doc_name = docname
        for node in doctree.findall(addnodes.number_reference):
            self.record('error', 'numbered-reference', 'Numbered references require a Hugo policy.', node)
        titles = list(doctree.findall(nodes.title))
        if titles:
            titles[0]['hugo_page_title'] = True
        # The upstream writer owns tree traversal; bypass its physical .md layout.
        self.sec_numbers = self.env.toc_secnumbers.get(docname, {})
        from docutils.io import StringOutput
        self.writer.write(doctree, StringOutput(encoding='utf-8'))
        name = docname + '.md'
        if Path(name).name == 'index.md':
            name = str(Path(name).with_name('_index.md'))
        target = Path(self.outdir) / 'content' / self.config.hugo_url_prefix.strip('/') / name
        target.parent.mkdir(parents=True, exist_ok=True)
        meta = dict(title=self.env.titles[docname].astext(), url=self.get_target_uri(docname),
                    toc=True, weight=self.weights.get(docname, 0),
                    migration_source=Path(self.env.doc2path(docname, base=False)).as_posix())
        frontmatter = '\n'.join(f'{key}: {json.dumps(value, ensure_ascii=False)}' for key, value in meta.items())
        target.write_text('---\n' + frontmatter + '\n---\n\n' + self.writer.output)
        self.page_manifest[docname] = dict(output=target.relative_to(self.outdir).as_posix(), **meta)

    def copy_asset(self, uri, node):
        source_root = Path(self.srcdir).resolve()
        candidates = [source_root / uri.lstrip('/'), source_root / posixpath.dirname(self.current_doc_name) / uri]
        if node.source:
            candidates.append(Path(node.source).parent / uri)
        source = next((path.resolve() for path in candidates if path.is_file() and path.resolve().is_relative_to(source_root)), None)
        if source is None:
            self.record('error', 'missing-asset', f'Cannot locate asset: {uri}', node)
            return uri
        name = hashlib.sha256(source.read_bytes()).hexdigest()[:16] + source.suffix.lower()
        target = self.asset_path('_migration/' + name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return self.asset_uri('_migration/' + quote(name))

    def asset_path(self, relative):
        return Path(self.outdir) / 'static' / self.config.hugo_url_prefix.strip('/') / relative

    def asset_uri(self, relative):
        return '/' + '/'.join(part for part in (self.config.hugo_url_prefix.strip('/'), relative) if part)

    def finish(self):
        # Downloads are copied into Hugo's static directory, preserving upstream hashes.
        for source, (_, target) in self.env.dlfiles.items():
            destination = self.asset_path(self.download_dir + '/' + target)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(self.srcdir) / source, destination)
        out = Path(self.outdir)
        (out / 'data').mkdir(exist_ok=True)
        (out / 'data' / 'sphinx_navigation.json').write_text(json.dumps(self.navigation, indent=2))
        (out / 'migration.json').write_text(json.dumps(dict(pages=self.page_manifest, findings=self.findings), indent=2))


def setup(app):
    app.setup_extension('sphinx_markdown_builder')
    app.add_builder(HugoBuilder)
    app.add_config_value('hugo_url_prefix', '/', 'env', types=[str])
    return dict(version=__version__, parallel_read_safe=True, parallel_write_safe=False)
