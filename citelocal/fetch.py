"""HTTP fetching for audits.

Everything an audit needs from the network goes through here so that timeouts,
user-agent, and per-run caching are consistent. Fetches never raise: callers
get a `Fetched` with `ok=False` and an `error` string, because a single dead
URL should degrade one check rather than abort the whole audit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests

# Identify honestly. Some sites serve different markup to unknown agents, and
# pretending to be a browser would make the audit lie about what bots see.
USER_AGENT = "CiteLocalAudit/1.0 (+AI visibility audit; respects robots.txt)"

DEFAULT_TIMEOUT = 12
MAX_BYTES = 3_000_000  # plenty for markup; avoids swallowing huge media


@dataclass
class Fetched:
    url: str
    ok: bool
    status_code: int | None = None
    text: str = ""
    error: str | None = None
    final_url: str = ""
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def is_html(self) -> bool:
        return "html" in self.headers.get("content-type", "").lower()


def normalize_url(raw: str) -> str:
    """Accept 'example.com', 'https://example.com/', etc. and return a URL."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    return raw


def root_of(url: str) -> str:
    parsed = urlparse(normalize_url(url))
    if not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def domain_of(url: str) -> str:
    netloc = urlparse(normalize_url(url)).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


class Fetcher:
    """Session-backed fetcher with a per-instance cache.

    One `Fetcher` is created per audit, so repeated requests for the same URL
    across checks cost a single round trip.
    """

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self._cache: dict[str, Fetched] = {}
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})

    def get(self, url: str) -> Fetched:
        url = normalize_url(url)
        if not url:
            return Fetched(url=url, ok=False, error="empty URL")
        if url in self._cache:
            return self._cache[url]

        try:
            response = self._session.get(
                url, timeout=self.timeout, allow_redirects=True, stream=True
            )
            # Read a bounded amount so a huge response can't exhaust memory.
            body = response.raw.read(MAX_BYTES, decode_content=True) or b""
            encoding = response.encoding or "utf-8"
            result = Fetched(
                url=url,
                ok=response.ok,
                status_code=response.status_code,
                text=body.decode(encoding, errors="replace"),
                final_url=response.url,
                headers={k.lower(): v for k, v in response.headers.items()},
                error=None if response.ok else f"HTTP {response.status_code}",
            )
        except requests.RequestException as exc:
            result = Fetched(url=url, ok=False, error=_short_error(exc))
        finally:
            pass

        self._cache[url] = result
        return result

    def get_path(self, base_url: str, path: str) -> Fetched:
        """Fetch `path` relative to the site root of `base_url`."""
        root = root_of(base_url)
        if not root:
            return Fetched(url=path, ok=False, error="invalid base URL")
        return self.get(urljoin(root + "/", path.lstrip("/")))

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> Fetcher:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def _short_error(exc: Exception) -> str:
    """requests exceptions stringify into paragraphs; keep reports readable."""
    name = type(exc).__name__
    if isinstance(exc, requests.Timeout):
        return "request timed out"
    if isinstance(exc, requests.ConnectionError):
        return "could not connect (DNS, TLS, or refused)"
    text = str(exc).split("\n", 1)[0]
    return f"{name}: {text[:160]}" if text else name
