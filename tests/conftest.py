"""Local HTTP servers serving deliberately broken and deliberately healthy sites.

The engine's whole claim is that it measures real things over a real wire, so
the tests exercise it over a real wire. These are actual HTTP servers on
localhost with real sockets, real headers, real latency and real gzip — not
mocked responses, which would only prove the mocks match the assertions.
"""
from __future__ import annotations

import gzip
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

BROKEN_HTML = """<!doctype html>
<html>
<head>
<title>Acme</title>
<script src="/blocking-1.js"></script>
<script src="/blocking-2.js"></script>
<script src="/blocking-3.js"></script>
<link rel="stylesheet" href="/a.css"><link rel="stylesheet" href="/b.css">
<link rel="stylesheet" href="/c.css"><link rel="stylesheet" href="/d.css">
<link rel="stylesheet" href="/e.css"><link rel="stylesheet" href="/f.css">
</head>
<body>
<h1>Welcome</h1>
<h1>Also Welcome</h1>
<img src="/1.jpg"><img src="/2.jpg"><img src="/3.png"><img src="/4.png">
<img src="/5.jpg"><img src="/6.jpg"><img src="/7.png">
<img src="http://insecure.example.com/tracker.png">
<p>We do things. {padding}</p>
<a href="/about">About</a>
<a href="/missing-one">Broken one</a>
<a href="/missing-two">Broken two</a>
<a href="/missing-three">Broken three</a>
</body>
</html>"""

HEALTHY_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Acme Plumbing — Emergency Repairs in Springfield</title>
<meta name="description" content="Acme Plumbing handles emergency repairs, boiler servicing and bathroom fitting across Springfield. Same-day callouts, fixed quotes, fully insured.">
<link rel="canonical" href="/">
<link rel="icon" href="/favicon.ico">
<meta property="og:title" content="Acme Plumbing">
<meta property="og:description" content="Emergency plumbing in Springfield">
<meta property="og:image" content="/og.png">
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"LocalBusiness","name":"Acme Plumbing"}}</script>
<script src="/app.js" defer></script>
<script src="https://plausible.io/js/script.js" defer></script>
</head>
<body>
<h1>Emergency plumbing in Springfield</h1>
<img src="/hero.webp" alt="An Acme engineer at work" width="800" height="400">
<img src="/team.webp" alt="The Acme team" width="400" height="300" loading="lazy">
<p>Call 555-123-4567 or email hello@acme-plumbing.example. {padding}</p>
<form action="/enquiry" method="post">
<input type="text" name="name"><input type="email" name="email">
<textarea name="message"></textarea>
</form>
<a href="/about">About us</a><a href="/services">Services</a><a href="/contact">Contact</a>
</body>
</html>"""

ROBOTS = "User-agent: *\nAllow: /\nSitemap: {origin}/sitemap.xml\n"
SITEMAP = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    "{entries}</urlset>"
)

SECURE_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cache-Control": "public, max-age=300",
}


def _make_handler(*, healthy: bool, ttfb_delay: float, sitemap_entries: int):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep pytest output readable
            pass

        def _send(self, status, body: bytes, headers: dict[str, str]):
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_HEAD(self):
            self.do_GET(head_only=True)

        def do_GET(self, head_only: bool = False):
            path = self.path.split("?", 1)[0]
            origin = f"http://{self.headers.get('Host', 'localhost')}"

            if path == "/robots.txt":
                self._send(200, ROBOTS.format(origin=origin).encode(), {"Content-Type": "text/plain"})
                return

            if path == "/sitemap.xml":
                if not healthy:
                    self._send(404, b"not found", {"Content-Type": "text/plain"})
                    return
                entries = "".join(
                    f"<url><loc>{origin}/page-{i}</loc></url>" for i in range(sitemap_entries)
                )
                self._send(200, SITEMAP.format(entries=entries).encode(), {"Content-Type": "application/xml"})
                return

            if path == "/":
                if ttfb_delay:
                    time.sleep(ttfb_delay)  # server think time -> measurable TTFB
                template = HEALTHY_HTML if healthy else BROKEN_HTML
                # Pad past the compression floor so "no Content-Encoding" is a
                # real finding rather than an artefact of a tiny response.
                html = template.format(padding="Reliable service since 1994. " * 260)
                raw = html.encode()
                if healthy:
                    body = gzip.compress(raw)
                    headers = {"Content-Type": "text/html; charset=utf-8", "Content-Encoding": "gzip"}
                    headers.update(SECURE_HEADERS)
                else:
                    body = raw
                    headers = {"Content-Type": "text/html", "Server": "nginx/1.14.0", "X-Powered-By": "PHP/7.2.1"}
                self._send(200, body, headers)
                return

            if path in ("/about", "/services", "/contact"):
                self._send(200, b"<html><body>ok</body></html>", {"Content-Type": "text/html"})
                return

            # Unknown path: the broken site soft-404s (returns 200), which is
            # itself one of the findings; the healthy one returns a real 404.
            if healthy:
                self._send(404, b"<html><body>Not found</body></html>", {"Content-Type": "text/html"})
            else:
                self._send(200, b"<html><body>Not found</body></html>", {"Content-Type": "text/html"})

    return Handler


class _QuietServer(ThreadingHTTPServer):
    """Suppress the connection-reset tracebacks that pooled sockets produce.

    requests keeps connections alive and drops them when the session closes;
    the server logging a full traceback for each one buries real failures.
    """

    def handle_error(self, request, client_address):
        pass


class _Server:
    def __init__(self, healthy: bool, ttfb_delay: float = 0.0, sitemap_entries: int = 0):
        handler = _make_handler(healthy=healthy, ttfb_delay=ttfb_delay, sitemap_entries=sitemap_entries)
        self.httpd = _QuietServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture(scope="session")
def broken_site():
    """A site doing nearly everything wrong, with ~1s of server think time."""
    server = _Server(healthy=False, ttfb_delay=1.0)
    yield server
    server.stop()


@pytest.fixture(scope="session")
def healthy_site():
    """A site doing nearly everything right, with a 120-URL sitemap."""
    server = _Server(healthy=True, ttfb_delay=0.0, sitemap_entries=120)
    yield server
    server.stop()


@pytest.fixture
def fast_fetcher():
    """No inter-request delay — politeness is for real hosts, not localhost."""
    from engine.fetch import Fetcher

    fetcher = Fetcher(min_delay=0.0, timeout=10.0)
    yield fetcher
    fetcher.close()
