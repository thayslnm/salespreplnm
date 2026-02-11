# Sales Call Prep Tool (No API Keys Required)

This project gives you two ways to use the sales-prep analyzer:

1. **A browser interface (recommended)**
2. **A command-line tool**

Both use only public website data (the same kind of checks you'd do manually).

## What it does

For any prospect website URL, it provides:

- **SEO snapshot**
  - Title/meta description length
  - H1/H2 counts
  - Word count
  - Image alt-text coverage
  - Internal vs external links
  - Structured data blocks
  - `robots.txt` and `sitemap.xml` checks
- **Google Ads footprint (heuristic)**
  - Looks for `AW-` IDs, conversion events, ad-related domains, `gclid`, etc.
- **Copy and messaging review**
  - Readability score
  - CTA/trust/local phrase detection
  - Recommended talking points for your sales call

---

## Option 1: Browser interface (easiest)

Start the local web app:

```bash
python3 web_interface.py
```

Then open:

```text
http://127.0.0.1:8000
```

Paste a URL and click **Analyze Site**.

### Optional host/port

```bash
python3 web_interface.py --host 0.0.0.0 --port 8080
```

---

## Option 2: Command line

```bash
python3 prospect_research.py https://example.com
```

JSON output:

```bash
python3 prospect_research.py https://example.com --json
```

---

## Requirements

No third-party Python packages are needed.

- Python 3.10+
- Internet access from your machine/network

> If your environment blocks outbound web requests, live site analysis will fail.
