"""Polite HTTP fetching.

Three properties matter here, and two of them are self-interest rather than
manners:

1. We obey robots.txt and rate-limit per host. Behaving like a scraper is the
   fastest way to get an IP nullrouted, which ends the campaign.
2. We identify ourselves honestly in the User-Agent, with a contact URL. A
   sysadmin who can tell what hit them files it under "audit tool"; one who
   can't files it under "attack".
3. We cap bytes and time. A single pathological host must not stall a batch of
   several hundred scans.

No API keys, no headless browser. Everything here is measurable from the
response itself, which keeps the whole engine to one dependency.
"""
from __future__ import annotations

import re
import threading
import time
import urllib.robotparser
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse, urlunparse

import requests

DEFAULT_UA = (
    "MillionsAudit/1.0 (+https://github.com/kazakholigarch/millions; "
    "site-health auditor; respects robots.txt)"
)

# A homepage that needs more than this is itself the finding.
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_TIMEOUT = 15.0
DEFAULT_MIN_DELAY = 1.0  # seconds between requests to the same host


@dataclass
class FetchResult:
    """One HTTP response, plus the timings we care about."""

    url: str
    final_url: str = ""
    status: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    text: str = ""
    # Time from request sent to response headers received. This is the number
    # that correlates with "the site feels slow" — server think time, not
    # download time.
    ttfb_ms: float | None = None
    total_ms: float | None = None
    redirect_chain: list[tuple[int, str]] = field(default_factory=list)
    error: str | None = None
    truncated: bool = False
    blocked_by_robots: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None and self.status is not None and 200 <= self.status < 400

    @property
    def bytes_len(self) -> int:
        return len(self.body)

    def header(self, name: str) -> str | None:
        """Case-insensitive header lookup."""
        lowered = name.lower()
        for key, value in self.headers.items():
            if key.lower() == lowered:
                return value
        return None


class RobotsPolicy:
    """robots.txt for one origin. Fails *open* on fetch errors.

    Failing open is deliberate: a 500 on /robots.txt is the site being broken,
    not the site saying no. A missing robots.txt has always meant "allowed".
    An explicit Disallow is what we honour.
    """

    def __init__(self, origin: str, body: str | None, status: int | None):
        self.origin = origin
        self.status = status
        self.present = status is not None and 200 <= status < 300 and bool(body)
        self._parser = urllib.robotparser.RobotFileParser()
        if self.present and body is not None:
            self._parser.parse(body.splitlines())
        else:
            self._parser.parse([])
        self.sitemaps: list[str] = []
        if self.present and body:
            for line in body.splitlines():
                if line.strip().lower().startswith("sitemap:"):
                    self.sitemaps.append(line.split(":", 1)[1].strip())

    def allows(self, url: str, user_agent: str = "*") -> bool:
        if not self.present:
            return True
        try:
            return self._parser.can_fetch(user_agent, url)
        except Exception:
            return True


class Fetcher:
    """Rate-limited HTTP client with a per-origin robots.txt cache."""

    def __init__(
        self,
        user_agent: str = DEFAULT_UA,
        timeout: float = DEFAULT_TIMEOUT,
        max_bytes: int = DEFAULT_MAX_BYTES,
        min_delay: float = DEFAULT_MIN_DELAY,
        obey_robots: bool = True,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.min_delay = min_delay
        self.obey_robots = obey_robots

        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": user_agent,
                # Advertise compression so a missing Content-Encoding on the
                # response is real evidence the origin doesn't compress, rather
                # than an artefact of us not asking.
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        self._last_hit: dict[str, float] = {}
        self._robots: dict[str, RobotsPolicy] = {}
        self._lock = threading.Lock()

    # -- rate limiting -----------------------------------------------------

    def _throttle(self, host: str) -> None:
        with self._lock:
            last = self._last_hit.get(host)
            now = time.monotonic()
            if last is not None:
                wait = self.min_delay - (now - last)
                if wait > 0:
                    time.sleep(wait)
                    now = time.monotonic()
            self._last_hit[host] = now

    # -- robots ------------------------------------------------------------

    def robots_for(self, url: str) -> RobotsPolicy:
        origin = origin_of(url)
        cached = self._robots.get(origin)
        if cached is not None:
            return cached

        result = self._raw_get(urljoin(origin, "/robots.txt"), allow_redirects=True)
        policy = RobotsPolicy(origin, result.text if result.ok else None, result.status)
        self._robots[origin] = policy
        return policy

    # -- fetching ----------------------------------------------------------

    def get(self, url: str, allow_redirects: bool = True) -> FetchResult:
        """Fetch a URL, honouring robots.txt."""
        if self.obey_robots:
            policy = self.robots_for(url)
            if not policy.allows(url, self.user_agent) and not policy.allows(url, "*"):
                return FetchResult(
                    url=url,
                    error="disallowed by robots.txt",
                    blocked_by_robots=True,
                )
        return self._raw_get(url, allow_redirects=allow_redirects)

    def _raw_get(self, url: str, allow_redirects: bool = True) -> FetchResult:
        """Fetch without a robots check (used for robots.txt itself)."""
        result = FetchResult(url=url)
        host = urlparse(url).netloc
        self._throttle(host)

        started = time.monotonic()
        try:
            # stream=True returns as soon as headers land, so the elapsed time
            # at that point is time-to-first-byte rather than full download.
            resp = self._session.get(
                url,
                timeout=self.timeout,
                allow_redirects=allow_redirects,
                stream=True,
            )
        except requests.exceptions.SSLError as exc:
            result.error = f"TLS error: {_brief(exc)}"
            return result
        except requests.exceptions.ConnectTimeout:
            result.error = f"connection timed out after {self.timeout:.0f}s"
            return result
        except requests.exceptions.ReadTimeout:
            result.error = f"read timed out after {self.timeout:.0f}s"
            return result
        except requests.exceptions.TooManyRedirects:
            result.error = "too many redirects"
            return result
        except requests.exceptions.RequestException as exc:
            result.error = f"{type(exc).__name__}: {_brief(exc)}"
            return result

        with resp:
            result.status = resp.status_code
            result.final_url = resp.url
            result.headers = dict(resp.headers)
            result.ttfb_ms = resp.elapsed.total_seconds() * 1000
            result.redirect_chain = [(r.status_code, r.url) for r in resp.history]

            chunks: list[bytes] = []
            total = 0
            try:
                for chunk in resp.iter_content(chunk_size=16384):
                    if not chunk:
                        continue
                    chunks.append(chunk)
                    total += len(chunk)
                    if total >= self.max_bytes:
                        result.truncated = True
                        break
            except requests.exceptions.RequestException as exc:
                result.error = f"transfer failed: {_brief(exc)}"

            result.body = b"".join(chunks)
            result.total_ms = (time.monotonic() - started) * 1000
            # resp.encoding comes from the Content-Type header and is safe to
            # read. resp.apparent_encoding is NOT: it reaches for resp.content,
            # which raises once the stream has been consumed by iter_content.
            result.text = _decode(result.body, resp.encoding)

        return result

    def head_status(self, url: str) -> int | None:
        """Cheap liveness probe for link checking. Falls back to GET.

        Plenty of servers mishandle HEAD (405, or a lying 200), so a non-2xx
        HEAD gets confirmed with a real GET before we call a link broken.
        """
        host = urlparse(url).netloc
        self._throttle(host)
        try:
            resp = self._session.head(url, timeout=self.timeout, allow_redirects=True)
            if resp.status_code < 400:
                return resp.status_code
        except requests.exceptions.RequestException:
            pass

        try:
            resp = self._session.get(
                url, timeout=self.timeout, allow_redirects=True, stream=True
            )
            with resp:
                return resp.status_code
        except requests.exceptions.RequestException:
            return None

    def close(self) -> None:
        self._session.close()


# <meta charset="..."> or <meta http-equiv content="...; charset=...">
_CHARSET_RE = re.compile(rb"""charset=["']?\s*([a-zA-Z0-9_\-]+)""", re.IGNORECASE)


def _sniff_charset(body: bytes) -> str | None:
    """Read the charset the document declares about itself.

    Only the head is worth scanning — a charset declaration is required to
    appear in the first 1024 bytes, and scanning a 5 MB body for it would be
    both slow and wrong.
    """
    match = _CHARSET_RE.search(body[:2048])
    return match.group(1).decode("ascii", "ignore") if match else None


def _decode(body: bytes, declared: str | None) -> str:
    """Bytes to text, trying the most trustworthy source of truth first.

    Note that requests defaults `declared` to ISO-8859-1 for text/* responses
    with no explicit charset, per the old HTTP spec. That default is usually
    wrong on the modern web, so a charset the document declares about itself
    beats it, and UTF-8 is tried before falling back to it.
    """
    candidates: list[str] = []
    sniffed = _sniff_charset(body)

    if declared and declared.lower() not in ("iso-8859-1", "latin-1"):
        candidates.append(declared)
    if sniffed:
        candidates.append(sniffed)
    candidates.append("utf-8")
    if declared:
        candidates.append(declared)
    candidates.append("latin-1")  # single-byte, never raises

    for candidate in candidates:
        try:
            return body.decode(candidate)
        except (LookupError, UnicodeDecodeError, ValueError):
            continue
    return body.decode("utf-8", errors="replace")


def _brief(exc: Exception) -> str:
    """Exception text trimmed to something that fits in a report line."""
    text = str(exc).strip().replace("\n", " ")
    return text[:160] if len(text) > 160 else text


# A CDN or managed host in front of a site is a paid product. Its presence is
# one of the few externally observable signals that a business already spends
# money on its web presence — which is the single best available predictor of
# whether it can sign a five-figure engagement.
CDN_SIGNATURES = {
    "Cloudflare": ("cf-ray", "cf-cache-status"),
    "Fastly": ("x-served-by", "x-fastly-request-id"),
    "Akamai": ("x-akamai-transformed", "akamai-grn"),
    "CloudFront": ("x-amz-cf-id", "x-amz-cf-pop"),
    "Vercel": ("x-vercel-id", "x-vercel-cache"),
    "Netlify": ("x-nf-request-id",),
    "Sucuri": ("x-sucuri-id",),
    "BunnyCDN": ("server-timing-bunny", "cdn-pullzone"),
    "KeyCDN": ("x-edge-location",),
}
_CDN_SERVER_TOKENS = {
    "cloudflare": "Cloudflare",
    "akamaighost": "Akamai",
    "vercel": "Vercel",
    "netlify": "Netlify",
    "cloudfront": "CloudFront",
}


def detect_cdn(headers: dict[str, str]) -> str | None:
    """Identify a CDN or managed host from response headers, if present."""
    lowered = {k.lower(): (v or "").lower() for k, v in headers.items()}

    for name, header_names in CDN_SIGNATURES.items():
        if any(h in lowered for h in header_names):
            return name

    for header in ("server", "via", "x-powered-by"):
        value = lowered.get(header, "")
        for token, name in _CDN_SERVER_TOKENS.items():
            if token in value:
                return name
    return None


def origin_of(url: str) -> str:
    parts = urlparse(url)
    return urlunparse((parts.scheme, parts.netloc, "", "", "", ""))


def normalize_url(raw: str) -> str:
    """Turn whatever the user typed into a fetchable URL.

    Accepts `example.com`, `www.example.com/path`, `https://example.com`.
    """
    raw = raw.strip()
    if not raw:
        raise ValueError("empty URL")
    if "://" not in raw:
        raw = "https://" + raw
    parts = urlparse(raw)
    if not parts.netloc:
        raise ValueError(f"could not parse a hostname from {raw!r}")
    return urlunparse((parts.scheme, parts.netloc, parts.path or "/", "", parts.query, ""))


def domain_of(url: str) -> str:
    """The storage key for a site: hostname, without `www.`, keeping any
    non-default port.

    The port matters. Dropping it collapses `host:8080` and `host:9090` onto one
    key, so scanning both leaves you with one record and silently loses the
    first. A default port carries no information, so it is dropped to keep
    `example.com` and `example.com:443` the same prospect.
    """
    parts = urlparse(url)
    host = (parts.hostname or parts.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]

    default_port = {"http": 80, "https": 443}.get(parts.scheme)
    if parts.port and parts.port != default_port:
        return f"{host}:{parts.port}"
    return host
