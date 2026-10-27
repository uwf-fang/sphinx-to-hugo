"""End-to-end preservation checks against real Sphinx and Hugo renderers."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids = []
        self.links = []
        self.text = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'a' and 'href' in attrs:
            self.links.append(attrs['href'])
        if tag == 'img' and 'src' in attrs:
            self.links.append(attrs['src'])

    def handle_data(self, data):
        self.text.append(data)


def validate_links(public):
    """Check every generated local page link, fragment, image, and download."""
    pages = {path: Page(path.read_text()) for path in public.rglob('*.html')}
    errors = []
    checked = 0
    for path, page in pages.items():
        if len(page.ids) != len(set(page.ids)):
            errors.append(f'Duplicate IDs: {path}')
        page_url = '/' + path.relative_to(public).as_posix().removesuffix('index.html')
        for link in page.links:
            uri = urlsplit(urljoin('https://example.invalid' + page_url, link))
            if uri.netloc != 'example.invalid':
                continue
            target = public / unquote(uri.path).lstrip('/')
            if uri.path.endswith('/'):
                target /= 'index.html'
            checked += 1
            if not target.is_file():
                errors.append(f'{page_url}: missing target {link}')
            elif uri.fragment and target in pages and unquote(uri.fragment) not in pages[target].ids:
                errors.append(f'{page_url}: missing anchor {link}')
    return checked, errors


class ConversionContract(unittest.TestCase):
    def run_cli(self, fixture, destination, *extra):
        environment = os.environ.copy()
        environment['PYTHONPATH'] = str(ROOT / 'src')
        return subprocess.run([sys.executable, '-m', 'sphinx_to_hugo', 'convert',
                               '--source', str(fixture), '--out', str(destination), *extra],
                              env=environment, text=True, capture_output=True)

    @unittest.skipUnless(shutil.which('hugo') and shutil.which('dot'), 'Requires Hugo and Graphviz')
    def test_semantic_preservation_and_rendered_links(self):
        fixture = ROOT / 'examples' / 'typical'
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in fixture.rglob('*') if p.is_file()}
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'converted'
            result = self.run_cli(fixture, out, '--prefix', '/teaching/')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((out / 'pilot.json').read_text())
            self.assertEqual(report['pages'], 4)
            self.assertFalse([x for x in report['findings'] if x['severity'] != 'info'])
            site = out / 'hugo'
            page = (site / 'content/teaching/concepts.md').read_text()
            self.assertIn('$\\Theta(n \\log n)$', page)
            self.assertIn('S(n) = \\sum_{i=1}^{n} i', page)
            self.assertIn('This sentence was expanded from an included source file.', page)
            self.assertIn('| Strategy', page)
            nav = json.loads((site / 'data/sphinx_navigation.json').read_text())
            self.assertEqual([entry['source'] for entry in nav['index'][0]['entries']], ['concepts', 'nested/practice'])
            self.assertTrue(nav['index'][1]['hidden'])
            rendered = subprocess.run(['hugo', '--source', str(site), '--destination', 'public',
                                       '--cacheDir', str(Path(directory) / 'cache'), '--panicOnWarning'],
                                      capture_output=True, text=True)
            self.assertEqual(rendered.returncode, 0, rendered.stdout + rendered.stderr)
            html = (site / 'public/teaching/concepts/index.html').read_text()
            self.assertIn('id="TableOfContents"', html)
            self.assertIn('A useful note with', html)
            self.assertIn('&lt;character&gt;', html)
            self.assertIn('Check the precondition', html)
            self.assertNotIn('raw HTML omitted', html)
            self.assertIn('callout-warning', html)
            self.assertIn('A footnote that must remain readable', html)
            self.assertIn('id="labelled-paragraph"', html)
            self.assertIn('The second paragraph must remain', html)
            self.assertNotIn('href="#two-strategies"', html)
            checked, errors = validate_links(site / 'public')
            self.assertGreater(checked, 15)
            self.assertEqual(errors, [])
            self.assertEqual(len(list((site / 'static/teaching/_migration').glob('graph-*.svg'))), 1)
            download = next((site / 'static/teaching/_downloads').rglob('example.py'))
            self.assertEqual(download.read_bytes(), (fixture / 'assets/example.py').read_bytes())
            practice = (site / 'content/teaching/nested/practice.md').read_text()
            self.assertIn('values = [2, 4, 6]', practice)
            self.assertNotIn('Generic literalinclude fixture.', practice)
        after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in fixture.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_content_requiring_review_fails_visibly(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'review'
            result = self.run_cli(ROOT / 'examples/review-required', out)
            self.assertNotEqual(result.returncode, 0)
            report = json.loads((out / 'pilot.json').read_text())
            self.assertTrue(any(x['feature'] == 'raw-content' for x in report['findings']))
            self.assertTrue(any('missing-target' in x for x in report['hugo']['warnings']))
            self.assertIn('Keep this content.', (out / 'hugo/content/_index.md').read_text())

    def test_refuses_output_inside_input(self):
        result = self.run_cli(ROOT / 'examples/typical', ROOT / 'examples/typical/output')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('non-overlapping', result.stderr)
        self.assertFalse((ROOT / 'examples/typical/output').exists())

    def test_project_configuration_preserves_markdown_and_exclusions(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source'
            source.mkdir()
            (source / 'conf.py').write_text('extensions = ["myst_parser"]\nsource_suffix = {".rst": "restructuredtext", ".md": "markdown"}\nexclude_patterns = ["excluded.rst"]\nrst_epilog = ".. |course| replace:: Configured Course"\n')
            (source / 'index.rst').write_text('Home\n====\n\n|course|\n\n.. toctree::\n\n   lesson\n')
            (source / 'lesson.md').write_text('# Markdown lesson\n\nA Markdown source page.\n')
            (source / 'excluded.rst').write_text('.. unknown-directive::\n')
            out = Path(directory) / 'out'
            result = self.run_cli(source, out, '--config-dir', str(source))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((out / 'pilot.json').read_text())
            self.assertEqual(report['pages'], 2)
            self.assertIn('Configured Course', (out / 'hugo/content/_index.md').read_text())
            self.assertIn('migration_source: "lesson.md"', (out / 'hugo/content/lesson.md').read_text())

    def test_route_collisions_are_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source'
            (source / 'topic').mkdir(parents=True)
            (source / 'index.rst').write_text('Home\n====\n\n.. toctree::\n\n   topic\n   topic/index\n')
            (source / 'topic.rst').write_text('Topic\n=====\n')
            (source / 'topic/index.rst').write_text('Another topic\n=============\n')
            out = Path(directory) / 'out'
            result = self.run_cli(source, out)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('route collision', (out / 'hugo/sphinx.log').read_text())


if __name__ == '__main__':
    unittest.main()
