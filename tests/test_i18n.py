import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "app/static/index.html"
APP = ROOT / "app/static/app.js"


class I18nInterfaceTests(unittest.TestCase):
    def test_language_buttons_are_present(self):
        html = INDEX.read_text(encoding="utf-8")
        self.assertIn('data-lang="fr"', html)
        self.assertIn('data-lang="en"', html)
        self.assertIn('data-i18n="header.subtitle"', html)

    def test_french_and_english_catalogs_are_present(self):
        js = APP.read_text(encoding="utf-8")
        self.assertIn("const I18N = {", js)
        self.assertIn("fr: {", js)
        self.assertIn("en: {", js)
        self.assertIn("localStorage.setItem('eif-language'", js)
        self.assertIn("navigator.languages", js)

    def test_dynamic_backend_messages_can_be_translated(self):
        js = APP.read_text(encoding="utf-8")
        self.assertIn("function backendText", js)
        self.assertIn("Low detection confidence", js)
        self.assertIn("DRY-RUN: create blank disk", js)


if __name__ == "__main__":
    unittest.main()
