"""HTML extraction on the standard library.

Deliberately no BeautifulSoup and no lxml. The engine's whole install story is
`pip install requests`, which matters when you want it running on a VPS, in a
cron job, and on a laptop on day one without debugging a C extension build.

`html.parser` is lenient with malformed markup, which is what real sites serve.
We only need attributes and shallow structure — not a full DOM — so the trade is
cheap.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse


@dataclass
class Image:
    src: str
    alt: str | None  # None = attribute absent; "" = present but empty
    width: str | None
    height: str | None
    lazy: bool

    @property
    def has_dimensions(self) -> bool:
        return bool(self.width) and bool(self.height)


@dataclass
class Script:
    src: str | None
    is_async: bool
    defer: bool
    in_head: bool
    inline_bytes: int
    script_type: str | None = None

    @property
    def render_blocking(self) -> bool:
        """A head script with a src and neither async nor defer stalls parsing.

        Inline head scripts also block, but they're usually small config
        snippets and flagging them produces noise, so we only count external.
        `type="module"` is deferred by spec; JSON-LD isn't executable at all.
        """
        if not self.in_head or not self.src:
            return False
        if self.script_type and self.script_type.lower() in {
            "module",
            "application/ld+json",
            "application/json",
        }:
            return False
        return not (self.is_async or self.defer)


@dataclass
class Form:
    action: str | None
    method: str
    input_types: list[str] = field(default_factory=list)

    @property
    def looks_like_lead_capture(self) -> bool:
        return any(t in {"email", "tel"} for t in self.input_types)


@dataclass
class PageDoc:
    """Everything we pull out of one HTML page."""

    base_url: str
    title: str | None = None
    meta_description: str | None = None
    meta_robots: str | None = None
    viewport: str | None = None
    canonical: str | None = None
    charset: str | None = None
    lang: str | None = None

    h1s: list[str] = field(default_factory=list)
    h2s: list[str] = field(default_factory=list)

    images: list[Image] = field(default_factory=list)
    scripts: list[Script] = field(default_factory=list)
    stylesheets: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    forms: list[Form] = field(default_factory=list)

    og: dict[str, str] = field(default_factory=dict)
    twitter: dict[str, str] = field(default_factory=dict)
    jsonld_types: list[str] = field(default_factory=list)

    has_favicon: bool = False
    text: str = ""

    # -- derived views -----------------------------------------------------

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def internal_links(self) -> list[str]:
        host = urlparse(self.base_url).netloc
        return [u for u in self.links if urlparse(u).netloc == host]

    @property
    def external_links(self) -> list[str]:
        host = urlparse(self.base_url).netloc
        return [u for u in self.links if urlparse(u).netloc and urlparse(u).netloc != host]

    @property
    def images_missing_alt(self) -> list[Image]:
        return [i for i in self.images if i.alt is None or not i.alt.strip()]

    @property
    def images_missing_dimensions(self) -> list[Image]:
        return [i for i in self.images if not i.has_dimensions]

    @property
    def render_blocking_scripts(self) -> list[Script]:
        return [s for s in self.scripts if s.render_blocking]

    @property
    def insecure_resources(self) -> list[str]:
        """http:// subresources — mixed content when the page itself is https."""
        if not self.base_url.startswith("https://"):
            return []
        candidates = (
            [i.src for i in self.images]
            + [s.src for s in self.scripts if s.src]
            + list(self.stylesheets)
        )
        return [u for u in candidates if u and u.startswith("http://")]

    @property
    def emails(self) -> list[str]:
        return _unique(EMAIL_RE.findall(self.text))

    @property
    def phones(self) -> list[str]:
        return _unique(m.strip() for m in PHONE_RE.findall(self.text))

    @property
    def has_contact_path(self) -> bool:
        return any("contact" in u.lower() or "quote" in u.lower() for u in self.internal_links)


# Deliberately conservative patterns — a false "they have a phone number" is
# worse than a miss, because it suppresses a finding we'd otherwise sell on.
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]{2,}")
PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)|\d{2,4})[\s.-]?\d{3,4}[\s.-]?\d{3,4}"
)

# Detected by script src or inline body. The finding we care about is the
# *absence* of all of these: a business that can't measure its funnel can't
# tell you what a fix was worth, which makes it a harder sale and a worse
# client. Its absence is a genuine, sellable gap.
ANALYTICS_SIGNATURES = {
    "Google Analytics / GTM": ("googletagmanager.com", "google-analytics.com", "gtag(", "dataLayer"),
    "Meta Pixel": ("connect.facebook.net", "fbq("),
    "Plausible": ("plausible.io",),
    "Fathom": ("usefathom.com",),
    "Matomo": ("matomo", "piwik"),
    "Segment": ("cdn.segment.com", "analytics.load("),
    "Hotjar": ("static.hotjar.com", "hj("),
    "Mixpanel": ("cdn.mxpnl.com", "mixpanel."),
    "PostHog": ("posthog.com", "posthog.init"),
    "Cloudflare Insights": ("static.cloudflareinsights.com",),
}

VOID_TAGS = {"img", "link", "meta", "br", "hr", "input", "source", "area", "base", "col"}


class _Extractor(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.doc = PageDoc(base_url=base_url)
        self._in_head = False
        self._in_body = False
        self._capture: str | None = None  # tag whose text we're accumulating
        self._buffer: list[str] = []
        self._text: list[str] = []
        self._skip_text_depth = 0  # inside <script>/<style>
        self._script_open: Script | None = None
        self._script_body: list[str] = []
        self._form_open: Form | None = None
        self._raw_inline_scripts: list[str] = []

    # -- helpers -----------------------------------------------------------

    def _abs(self, url: str | None) -> str | None:
        if not url:
            return None
        url = url.strip()
        if not url or url.startswith(("javascript:", "data:", "#")):
            return None
        try:
            return urljoin(self.doc.base_url, url)
        except ValueError:
            return None

    # -- tag handling ------------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        doc = self.doc

        if tag == "head":
            self._in_head = True
        elif tag == "body":
            self._in_head = False
            self._in_body = True
        elif tag == "html":
            doc.lang = a.get("lang") or doc.lang

        elif tag == "title":
            self._capture, self._buffer = "title", []

        elif tag == "meta":
            self._handle_meta(a)

        elif tag == "link":
            self._handle_link(a)

        elif tag in ("h1", "h2"):
            self._capture, self._buffer = tag, []

        elif tag == "img":
            src = self._abs(a.get("src") or a.get("data-src"))
            if src:
                doc.images.append(
                    Image(
                        src=src,
                        alt=a["alt"] if "alt" in a else None,
                        width=a.get("width") or None,
                        height=a.get("height") or None,
                        lazy=a.get("loading", "").lower() == "lazy",
                    )
                )

        elif tag == "script":
            self._skip_text_depth += 1
            self._script_open = Script(
                src=self._abs(a.get("src")),
                is_async="async" in a,
                defer="defer" in a,
                in_head=self._in_head,
                inline_bytes=0,
                script_type=a.get("type") or None,
            )
            self._script_body = []

        elif tag == "style":
            self._skip_text_depth += 1

        elif tag == "a":
            href = self._abs(a.get("href"))
            if href and href.startswith(("http://", "https://")):
                doc.links.append(href)

        elif tag == "form":
            self._form_open = Form(
                action=self._abs(a.get("action")),
                method=(a.get("method") or "get").lower(),
            )

        elif tag == "input" and self._form_open is not None:
            self._form_open.input_types.append((a.get("type") or "text").lower())

        elif tag in ("textarea", "select") and self._form_open is not None:
            self._form_open.input_types.append(tag)

        # Some pages never close <form>; treat a void tag as non-nesting.
        if tag in VOID_TAGS:
            return

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        doc = self.doc

        if tag == "head":
            self._in_head = False

        elif tag == "title" and self._capture == "title":
            doc.title = "".join(self._buffer).strip() or None
            self._capture = None

        elif tag in ("h1", "h2") and self._capture == tag:
            text = " ".join("".join(self._buffer).split())
            if text:
                (doc.h1s if tag == "h1" else doc.h2s).append(text)
            self._capture = None

        elif tag == "script":
            self._skip_text_depth = max(0, self._skip_text_depth - 1)
            if self._script_open is not None:
                body = "".join(self._script_body)
                self._script_open.inline_bytes = len(body.encode("utf-8", "ignore"))
                if body.strip():
                    self._raw_inline_scripts.append(body)
                stype = (self._script_open.script_type or "").lower()
                if stype == "application/ld+json":
                    self._absorb_jsonld(body)
                doc.scripts.append(self._script_open)
                self._script_open = None
                self._script_body = []

        elif tag == "style":
            self._skip_text_depth = max(0, self._skip_text_depth - 1)

        elif tag == "form" and self._form_open is not None:
            doc.forms.append(self._form_open)
            self._form_open = None

    def handle_data(self, data: str) -> None:
        if self._script_open is not None:
            self._script_body.append(data)
            return
        if self._skip_text_depth > 0:
            return
        if self._capture:
            self._buffer.append(data)
        if self._in_body or not self._in_head:
            stripped = data.strip()
            if stripped:
                self._text.append(stripped)

    # -- specific elements -------------------------------------------------

    def _handle_meta(self, a: dict[str, str]) -> None:
        doc = self.doc
        name = (a.get("name") or "").lower()
        prop = (a.get("property") or "").lower()
        content = a.get("content", "").strip()

        if "charset" in a:
            doc.charset = a["charset"]
        elif name == "description":
            doc.meta_description = content or None
        elif name == "robots":
            doc.meta_robots = content or None
        elif name == "viewport":
            doc.viewport = content or None
        elif name.startswith("twitter:"):
            doc.twitter[name] = content
        elif (a.get("http-equiv") or "").lower() == "content-type" and "charset=" in content:
            doc.charset = content.split("charset=")[-1].strip()

        if prop.startswith("og:"):
            doc.og[prop] = content

    def _handle_link(self, a: dict[str, str]) -> None:
        doc = self.doc
        rels = (a.get("rel") or "").lower().split()
        href = self._abs(a.get("href"))

        if "canonical" in rels and href:
            doc.canonical = href
        if "stylesheet" in rels and href:
            doc.stylesheets.append(href)
        if any(r in {"icon", "shortcut", "apple-touch-icon", "mask-icon"} for r in rels):
            doc.has_favicon = True

    def _absorb_jsonld(self, body: str) -> None:
        try:
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            return
        for node in _iter_jsonld_nodes(data):
            t = node.get("@type")
            if isinstance(t, str):
                self.doc.jsonld_types.append(t)
            elif isinstance(t, list):
                self.doc.jsonld_types.extend(str(x) for x in t)

    # -- finish ------------------------------------------------------------

    def finish(self) -> PageDoc:
        if self._form_open is not None:  # unclosed <form>
            self.doc.forms.append(self._form_open)
            self._form_open = None
        self.doc.text = " ".join(self._text)
        self.doc.links = _unique(self.doc.links)
        self.doc.stylesheets = _unique(self.doc.stylesheets)
        self.doc.jsonld_types = _unique(self.doc.jsonld_types)
        return self.doc

    @property
    def inline_script_text(self) -> str:
        return "\n".join(self._raw_inline_scripts)


def parse(html: str, base_url: str) -> PageDoc:
    """Parse HTML into a PageDoc. Never raises on malformed input."""
    extractor = _Extractor(base_url)
    try:
        extractor.feed(html)
        extractor.close()
    except Exception:
        # A parse blow-up on one weird page must not kill a batch of 200 scans;
        # we keep whatever was extracted before the failure.
        pass
    doc = extractor.finish()
    doc._inline_script_text = extractor.inline_script_text  # type: ignore[attr-defined]
    return doc


def detect_analytics(doc: PageDoc) -> list[str]:
    """Which analytics/attribution tools are present on the page."""
    haystack = " ".join(
        [s.src or "" for s in doc.scripts]
        + [getattr(doc, "_inline_script_text", "")]
        + [u for u in doc.stylesheets]
    ).lower()

    found = []
    for label, signatures in ANALYTICS_SIGNATURES.items():
        if any(sig.lower() in haystack for sig in signatures):
            found.append(label)
    return found


def _iter_jsonld_nodes(data):
    if isinstance(data, dict):
        yield data
        for value in data.values():
            yield from _iter_jsonld_nodes(value)
    elif isinstance(data, list):
        for item in data:
            yield from _iter_jsonld_nodes(item)


def _unique(items) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out
