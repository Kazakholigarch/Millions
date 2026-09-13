"""Minimal HTML extraction built on the standard library.

We only need script blocks, headings, visible text, meta tags and link rels.
Using `html.parser` keeps the install to `requests` + `flask`, which matters
for a tool agencies will run on a laptop or a cheap VPS.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

# Tags whose contents are never user-visible prose.
_NON_TEXT_TAGS = {"script", "style", "noscript", "template", "svg"}

# Closing these should insert a space, or collapsing whitespace fuses the last
# word of one block onto the first word of the next ("60 minutes.About us").
_BLOCK_TAGS = {
    "p", "div", "li", "ul", "ol", "section", "article", "header", "footer",
    "nav", "aside", "main", "table", "tr", "td", "th", "br", "hr", "a",
    "blockquote", "figure", "figcaption", "dd", "dt", "dl", "form", "label",
    "span", "button", "h1", "h2", "h3", "h4", "h5", "h6",
}


@dataclass
class Page:
    title: str = ""
    meta: dict[str, str] = field(default_factory=dict)
    json_ld: list[object] = field(default_factory=list)
    json_ld_errors: list[str] = field(default_factory=list)
    microdata_types: list[str] = field(default_factory=list)
    headings: list[tuple[int, str]] = field(default_factory=list)
    text: str = ""
    links: list[tuple[str, str]] = field(default_factory=list)  # (href, anchor text)
    scripts: int = 0

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    def headings_of(self, level: int) -> list[str]:
        return [text for lvl, text in self.headings if lvl == level]

    def question_headings(self) -> list[str]:
        """Headings phrased as questions — the shape AI answers extract from."""
        out = []
        for _, text in self.headings:
            stripped = text.strip()
            if stripped.endswith("?") or re.match(
                r"^(how|what|why|when|where|who|which|can|do|does|is|are|should)\b",
                stripped,
                re.IGNORECASE,
            ):
                out.append(stripped)
        return out


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.page = Page()
        self._suppress_depth = 0
        self._capture: str | None = None  # active script/heading/title buffer name
        self._buffer: list[str] = []
        self._heading_level = 0
        self._text_parts: list[str] = []
        self._current_href: str | None = None
        self._anchor_parts: list[str] = []
        self._script_is_ld = False

    # -- tag handling -----------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr = {k.lower(): (v or "") for k, v in attrs}

        if tag == "script":
            self.page.scripts += 1
            self._script_is_ld = "ld+json" in attr.get("type", "").lower()
            if self._script_is_ld:
                self._capture = "script"
                self._buffer = []

        if tag in _NON_TEXT_TAGS:
            self._suppress_depth += 1
            return

        if tag == "title":
            self._capture = "title"
            self._buffer = []
        elif tag == "meta":
            key = attr.get("name") or attr.get("property") or attr.get("itemprop")
            if key and "content" in attr:
                self.page.meta[key.lower()] = attr["content"]
        elif tag == "link":
            rel = attr.get("rel", "").lower()
            if rel and attr.get("href"):
                self.page.links.append((attr["href"], f"rel={rel}"))
        elif tag in ("h1", "h2", "h3", "h4"):
            self._capture = "heading"
            self._heading_level = int(tag[1])
            self._buffer = []
        elif tag == "a" and attr.get("href"):
            self._current_href = attr["href"]
            self._anchor_parts = []

        # Microdata is an older but still-parsed alternative to JSON-LD.
        if "itemtype" in attr:
            item_type = attr["itemtype"].rstrip("/").rsplit("/", 1)[-1]
            if item_type:
                self.page.microdata_types.append(item_type)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if tag in _NON_TEXT_TAGS:
            self._suppress_depth = max(0, self._suppress_depth - 1)

        if tag in _BLOCK_TAGS and not self._suppress_depth:
            self._text_parts.append(" ")

        if tag == "script":
            if self._capture == "script":
                self._store_json_ld("".join(self._buffer))
                self._capture = None
                self._buffer = []
            self._script_is_ld = False
            return

        if tag == "title" and self._capture == "title":
            self.page.title = "".join(self._buffer).strip()
            self._capture = None
            self._buffer = []
        elif tag in ("h1", "h2", "h3", "h4") and self._capture == "heading":
            text = re.sub(r"\s+", " ", "".join(self._buffer)).strip()
            if text:
                self.page.headings.append((self._heading_level, text))
            self._capture = None
            self._buffer = []
        elif tag == "a" and self._current_href is not None:
            anchor = re.sub(r"\s+", " ", "".join(self._anchor_parts)).strip()
            self.page.links.append((self._current_href, anchor))
            self._current_href = None
            self._anchor_parts = []

    def handle_data(self, data: str) -> None:
        if self._capture in ("script", "title", "heading"):
            self._buffer.append(data)
            # Headings are visible prose, so they belong in the text body. The
            # <title> is not part of the page body and would double-count.
            if self._capture == "heading":
                self._text_parts.append(data)
        elif not self._suppress_depth:
            self._text_parts.append(data)
            if self._current_href is not None:
                self._anchor_parts.append(data)

    # -- JSON-LD ----------------------------------------------------------
    def _store_json_ld(self, raw: str) -> None:
        raw = raw.strip()
        if not raw:
            return
        try:
            self.page.json_ld.append(json.loads(raw))
            return
        except json.JSONDecodeError as exc:
            # Real sites ship JSON-LD with trailing commas or embedded comments.
            # Try one conservative repair before reporting it as broken, since a
            # block we can't parse is also a block search engines may reject.
            repaired = re.sub(r",\s*([}\]])", r"\1", raw)
            try:
                self.page.json_ld.append(json.loads(repaired))
                self.page.json_ld_errors.append(
                    f"JSON-LD block had invalid syntax ({exc.msg}) but parsed after "
                    "removing trailing commas — fix the source, validators will reject it."
                )
            except json.JSONDecodeError:
                self.page.json_ld_errors.append(f"Unparseable JSON-LD block: {exc.msg}")

    def finish(self) -> Page:
        self.page.text = re.sub(r"\s+", " ", "".join(self._text_parts)).strip()
        return self.page


def parse(html: str) -> Page:
    parser = _Parser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # noqa: BLE001 - malformed markup must not abort an audit
        pass
    return parser.finish()


def flatten_json_ld(blocks: list[object]) -> list[dict]:
    """Flatten JSON-LD into a list of node dicts.

    Handles the three shapes real sites use: a bare object, an array of
    objects, and an @graph wrapper. Nested nodes are included so a
    LocalBusiness inside a WebSite graph is still found.
    """
    nodes: list[dict] = []

    def walk(value: object, depth: int = 0) -> None:
        if depth > 8:
            return
        if isinstance(value, dict):
            if "@graph" in value and isinstance(value["@graph"], list):
                for item in value["@graph"]:
                    walk(item, depth + 1)
            if any(key in value for key in ("@type", "@id", "name")):
                nodes.append(value)
            for key, nested in value.items():
                if key == "@graph":
                    continue
                if isinstance(nested, (dict, list)):
                    walk(nested, depth + 1)
        elif isinstance(value, list):
            for item in value:
                walk(item, depth + 1)

    for block in blocks:
        walk(block)
    return nodes


def types_of(node: dict) -> list[str]:
    """Normalize @type, which may be a string or a list."""
    raw = node.get("@type", "")
    values = raw if isinstance(raw, list) else [raw]
    out = []
    for value in values:
        if isinstance(value, str) and value:
            out.append(value.rstrip("/").rsplit("/", 1)[-1])
    return out
