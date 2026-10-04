from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.template import Context, Template
from django.test import SimpleTestCase, override_settings

from .templatetags import theme_assets


@override_settings(STATIC_URL='/assets-test/')
class ThemeAssetTests(SimpleTestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.theme_root = Path(self.directory.name)
        for folder in ('css', 'js'):
            (self.theme_root / folder).mkdir()
        self.css = self.theme_root / 'css/app.css'
        self.js = self.theme_root / 'js/app.js'
        self.css.write_bytes(b':root { --brand: #245bdf; }')
        self.js.write_bytes(b'const sidebarEnabled = true;')
        root_patch = patch.object(theme_assets, 'THEME_ROOT', self.theme_root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        theme_assets._cached_digest.cache_clear()
        self.template = Template(
            "{% load theme_assets %}{% theme_asset 'css/app.css' %}\n"
            "{% theme_asset 'js/app.js' %}"
        )

    def tearDown(self):
        theme_assets._cached_digest.cache_clear()
        super().tearDown()

    def render_urls(self):
        return self.template.render(Context()).splitlines()

    @override_settings(DEBUG=True)
    def test_template_uses_static_url_and_independent_content_fingerprints(self):
        urls = self.render_urls()
        css_digest = sha256(self.css.read_bytes()).hexdigest()[:12]
        js_digest = sha256(self.js.read_bytes()).hexdigest()[:12]

        self.assertEqual(urls, [
            f'/assets-test/mediata/css/app.css?v={css_digest}',
            f'/assets-test/mediata/js/app.js?v={js_digest}',
        ])
        self.assertNotEqual(css_digest, js_digest)

    @override_settings(DEBUG=True)
    def test_development_updates_url_when_asset_content_changes(self):
        original_urls = self.render_urls()
        self.css.write_bytes(b':root { --brand: #1748bc; }')

        updated_urls = self.render_urls()

        self.assertNotEqual(updated_urls[0], original_urls[0])
        self.assertEqual(updated_urls[1], original_urls[1])
        self.assertEqual(
            updated_urls[0],
            '/assets-test/mediata/css/app.css?v='
            + sha256(self.css.read_bytes()).hexdigest()[:12],
        )

    @override_settings(DEBUG=False)
    def test_production_keeps_cached_urls_without_repeated_file_reads(self):
        read_bytes = Path.read_bytes
        with patch.object(Path, 'read_bytes', autospec=True, side_effect=read_bytes) as reads:
            original_urls = self.render_urls()
            self.assertEqual(reads.call_count, 2)
            self.css.write_bytes(b':root { --brand: #1748bc; }')
            self.js.write_bytes(b'const sidebarEnabled = false;')

            self.assertEqual(self.render_urls(), original_urls)
            self.assertEqual(self.render_urls(), original_urls)
            self.assertEqual(reads.call_count, 2)
