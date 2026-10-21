"""Offline checks for the reader's navigation paths; no product imports or disk writes."""

import re
import unittest
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS = PROJECT_ROOT / "docs"
CHAPTERS = (
    "01-architecture.html",
    "02-domain-algorithms.html",
    "03-pyside6-framework.html",
    "04-qt-ui.html",
    "05-concurrency.html",
    "06-data-quality.html",
    "07-engineering.html",
    "08-technical-stack-report.html",
    "09-review-and-troubleshooting.html",
    "10-packaging.html",
)


class HtmlPage(HTMLParser):
    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: Counter[str] = Counter()
        self.references: list[str] = []
        self.links: list[str] = []
        self.feed(source)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        # An old-style named anchor and its matching id identify the same element.
        anchors = {attributes.get("id")}
        if tag == "a":
            anchors.add(attributes.get("name"))
        self.anchors.update(anchor for anchor in anchors if anchor)
        for attribute in ("href", "src", "poster"):
            value = attributes.get(attribute)
            if value is not None:
                self.references.append(value)
                if tag == "a" and attribute == "href":
                    self.links.append(value)


def local_target(source: Path, reference: str) -> tuple[Path, str] | None:
    url = urlsplit(reference.strip())
    if url.scheme or url.netloc:
        return None  # External URLs are deliberately never fetched.
    target = (source.parent / unquote(url.path)).resolve() if url.path else source
    return target, unquote(url.fragment)


def navigation_errors(pages: dict[Path, HtmlPage], files: set[Path], root: Path) -> list[str]:
    errors: list[str] = []
    for source, page in pages.items():
        for anchor, count in page.anchors.items():
            if count > 1:
                errors.append(f"{source.name}: duplicate anchor #{anchor}")
        for reference in page.references:
            resolved = local_target(source, reference)
            if resolved is None:
                continue
            target, fragment = resolved
            if not target.is_relative_to(root):
                errors.append(f"{source.name}: outside repository: {reference}")
            elif target not in files:
                errors.append(f"{source.name}: missing file: {reference}")
            elif fragment and target.suffix.lower() in {".html", ".htm"}:
                if target not in pages or fragment not in pages[target].anchors:
                    errors.append(f"{source.name}: missing anchor: {reference}")
    return errors


class DocsNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pages = {
            path.resolve(): HtmlPage(path.read_text(encoding="utf-8"))
            for path in DOCS.rglob("*.html")
        }

    def test_local_links_images_stylesheets_and_html_anchors_resolve(self) -> None:
        targets = {
            resolved[0]
            for source, page in self.pages.items()
            for reference in page.references
            if (resolved := local_target(source, reference)) is not None
        }
        existing = {path for path in targets if path.is_file()}
        self.assertEqual(navigation_errors(self.pages, existing, PROJECT_ROOT), [])

    def test_home_links_to_every_chapter_and_chapters_link_back(self) -> None:
        home = DOCS / "index.html"
        self.assertIn(home, self.pages)
        destinations = {
            resolved[0]
            for reference in self.pages[home].links
            if (resolved := local_target(home, reference)) is not None
        }
        for name in CHAPTERS:
            chapter = DOCS / name
            with self.subTest(chapter=name):
                self.assertIn(chapter, self.pages)
                self.assertIn(chapter, destinations)
                backlinks = {
                    resolved[0]
                    for reference in self.pages[chapter].links
                    if (resolved := local_target(chapter, reference)) is not None
                }
                self.assertIn(home, backlinks)

    def test_readme_has_clickable_learning_and_review_entries(self) -> None:
        readme = PROJECT_ROOT / "README.md"
        links = re.findall(
            r"(?<!!)\[[^\]\n]+\]\(<?([^\s)>]+)>?\)", readme.read_text(encoding="utf-8")
        )
        destinations = {
            resolved[0]
            for reference in links
            if (resolved := local_target(readme, reference)) is not None
        }
        self.assertTrue(
            {DOCS / "index.html", DOCS / CHAPTERS[-1]} <= destinations,
            "README must link to the knowledge index and reader review guide",
        )


class NavigationCheckerTests(unittest.TestCase):
    def test_decodes_local_paths_and_fragments_without_fetching_external_links(self) -> None:
        home = DOCS / "index.html"
        chapter = DOCS / "a b.html"
        pages = {
            home: HtmlPage(
                '<a href="a%20b.html?view=1&amp;mode=read#%E7%BB%83%E4%B9%A0">Go</a>'
                '<a href="https://example.invalid/missing#anchor">External</a>'
                '<a href="//example.invalid/path">External</a><a href="mailto:a@b.invalid">Mail</a>'
            ),
            chapter: HtmlPage('<h2 id="练习">Practice</h2><a href="#练习">Again</a>'),
        }
        self.assertEqual(navigation_errors(pages, set(pages), PROJECT_ROOT), [])

    def test_missing_resources_fragments_duplicate_ids_and_escaping_paths_fail(self) -> None:
        home = DOCS / "index.html"
        page = HtmlPage(
            '<link href="missing.css" rel="stylesheet"><img src="missing.png">'
            '<a href="#absent">Broken</a><h2 id="twice">A</h2><p id="twice">B</p>'
            '<a href="../../outside.html">Outside</a>'
        )
        errors = navigation_errors({home: page}, {home}, PROJECT_ROOT)
        self.assertEqual(len(errors), 5)
        for expected in ("missing.css", "missing.png", "#absent", "#twice", "outside repository"):
            self.assertTrue(any(expected in error for error in errors), expected)

    def test_named_and_self_closing_anchors_are_supported(self) -> None:
        home = DOCS / "index.html"
        page = HtmlPage('<a name="legacy" id="legacy"/><a href="#legacy">Read</a>')
        self.assertEqual(navigation_errors({home: page}, {home}, PROJECT_ROOT), [])


if __name__ == "__main__":
    unittest.main()
