#!/usr/bin/env python3
"""Minimal local web interface for the sales call prep tool."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from prospect_research import analyze_page, fetch_page, normalize_url

HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Sales Call Prep</title>
  <style>
    :root { color-scheme: light dark; }
    body { font-family: Arial, sans-serif; margin: 0; background: #f7f7f9; color: #111; }
    .wrap { max-width: 980px; margin: 0 auto; padding: 24px; }
    .card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,.08); margin-bottom: 16px; }
    h1 { margin: 0 0 8px; }
    p { margin-top: 0; }
    .row { display: flex; gap: 12px; flex-wrap: wrap; }
    input[type=url] { flex: 1; min-width: 320px; padding: 10px; border-radius: 8px; border: 1px solid #c9ccd3; }
    button { padding: 10px 16px; border: 0; border-radius: 8px; background: #0a66ff; color: white; font-weight: 700; cursor: pointer; }
    button[disabled] { opacity: .7; cursor: wait; }
    .muted { color: #666; font-size: .95rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px; }
    .metric { border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px; background: #fafafa; }
    .metric strong { display: block; font-size: .86rem; color: #444; margin-bottom: 4px; }
    ul { margin-top: 8px; }
    .hidden { display: none; }
    .error { color: #b00020; font-weight: 700; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Sales Call Prep Interface</h1>
      <p>Paste a prospect website and get SEO, Google Ads footprint, and messaging insights in one place.</p>
      <form id="analyze-form" class="row">
        <input id="url" type="url" name="url" placeholder="https://example.com" required />
        <button id="submit" type="submit">Analyze Site</button>
      </form>
      <p class="muted">Tip: You can paste URL without <code>https://</code>; it will be added automatically.</p>
      <p id="status" class="muted"></p>
      <p id="error" class="error hidden"></p>
    </div>

    <div id="results" class="hidden">
      <div class="card">
        <h2>SEO Snapshot</h2>
        <div id="seo-grid" class="grid"></div>
      </div>
      <div class="card">
        <h2>Google Ads Signals</h2>
        <div id="ads"></div>
      </div>
      <div class="card">
        <h2>Copy & Messaging Review</h2>
        <div id="copy"></div>
      </div>
    </div>
  </div>

  <script>
    const form = document.getElementById('analyze-form');
    const statusNode = document.getElementById('status');
    const errorNode = document.getElementById('error');
    const submitBtn = document.getElementById('submit');
    const results = document.getElementById('results');

    const seoGrid = document.getElementById('seo-grid');
    const adsNode = document.getElementById('ads');
    const copyNode = document.getElementById('copy');

    function metric(label, value) {
      return `<div class="metric"><strong>${label}</strong>${value}</div>`;
    }

    function listOrNone(items) {
      if (!items || !items.length) return 'none';
      return `<ul>${items.map(i => `<li>${i}</li>`).join('')}</ul>`;
    }

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      errorNode.classList.add('hidden');
      results.classList.add('hidden');
      statusNode.textContent = 'Analyzing... this can take a few seconds.';
      submitBtn.disabled = true;

      const url = document.getElementById('url').value;
      const body = new URLSearchParams({ url });

      try {
        const response = await fetch('/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body,
        });

        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || 'Analysis failed');
        }

        const { seo, ads, copy } = payload;

        seoGrid.innerHTML = [
          metric('Final URL', seo.final_url),
          metric('HTTP Status', seo.status_code),
          metric('Title Length', seo.title_length),
          metric('Meta Description Length', seo.meta_description_length),
          metric('H1 / H2', `${seo.h1_count} / ${seo.h2_count}`),
          metric('Word Count', seo.word_count),
          metric('Images Missing Alt', `${seo.images_missing_alt} of ${seo.images_total}`),
          metric('Links (Internal / External)', `${seo.internal_links} / ${seo.external_links}`),
          metric('Schema Blocks', seo.schema_count),
          metric('robots.txt', seo.robots_txt_found),
          metric('sitemap.xml', seo.sitemap_found),
        ].join('');

        adsNode.innerHTML = `
          <p><strong>Likely running Google Ads:</strong> ${ads.is_likely_running_google_ads} (${ads.confidence} confidence)</p>
          <p><strong>Evidence:</strong> ${ads.evidence.length ? ads.evidence.join(', ') : 'none found'}</p>
        `;

        copyNode.innerHTML = `
          <p><strong>Readability score:</strong> ${copy.readability_score}</p>
          <p><strong>CTA phrases found:</strong> ${copy.cta_phrases_found.join(', ') || 'none'}</p>
          <p><strong>Trust signals found:</strong> ${copy.trust_signals_found.join(', ') || 'none'}</p>
          <p><strong>Local terms found:</strong> ${copy.local_terms_found.join(', ') || 'none'}</p>
          <p><strong>Recommended talking points:</strong></p>
          ${listOrNone(copy.recommendations)}
        `;

        results.classList.remove('hidden');
        statusNode.textContent = 'Done.';
      } catch (err) {
        errorNode.textContent = err.message;
        errorNode.classList.remove('hidden');
        statusNode.textContent = '';
      } finally {
        submitBtn.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, html: str) -> None:
        data = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            self._send_html(HTML_PAGE)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/analyze":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        form = parse_qs(body)
        raw_url = (form.get("url") or [""])[0].strip()

        if not raw_url:
            self._send_json({"error": "Please provide a URL."}, status=400)
            return

        url = normalize_url(raw_url)

        try:
            page = fetch_page(url)
            seo, ads, copy = analyze_page(page)
        except Exception as exc:  # broad to return helpful API error to UI
            self._send_json({"error": f"Could not analyze URL: {exc}"}, status=400)
            return

        self._send_json(
            {
                "url": url,
                "seo": asdict(seo),
                "ads": asdict(ads),
                "copy": asdict(copy),
            }
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local web interface for sales call prep.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Open http://{args.host}:{args.port} in your browser")
    server.serve_forever()


if __name__ == "__main__":
    main()
