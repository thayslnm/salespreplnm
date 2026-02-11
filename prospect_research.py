#!/usr/bin/env python3
"""Prospect research helper for sales prep without paid APIs or external packages."""

from __future__ import annotations

import argparse
import json
import re
import statistics
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Iterable

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)
TIMEOUT_SECONDS = 15


@dataclass
class SEOReport:
    final_url: str
    status_code: int
    title: str | None
    title_length: int
    meta_description: str | None
    meta_description_length: int
    h1_count: int
    h2_count: int
    word_count: int
    images_total: int
    images_missing_alt: int
    internal_links: int
    external_links: int
    schema_count: int
    robots_txt_found: bool
    sitemap_found: bool


@dataclass
class AdsSignals:
    is_likely_running_google_ads: bool
    confidence: str
    evidence: list[str]


@dataclass
class CopyReview:
    readability_score: float
    cta_phrases_found: list[str]
    trust_signals_found: list[str]
    local_terms_found: list[str]
    recommendations: list[str]


@dataclass
class Page:
    requested_url: str
    final_url: str
    status_code: int
    text: str


class SimpleHTMLAnalyzer(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_title = False
        self.title_parts: list[str] = []
        self.meta_description: str | None = None
        self.h1_count = 0
        self.h2_count = 0
        self.images_total = 0
        self.images_missing_alt = 0
        self.links: list[str] = []
        self.schema_count = 0
        self.visible_text_parts: list[str] = []
        self.script_srcs: list[str] = []
        self._skip_text_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        t = tag.lower()
        if t in {"script", "style", "noscript", "svg"}:
            self._skip_text_depth += 1

        if t == "title":
            self.in_title = True
        elif t == "meta":
            name = (attrs_dict.get("name") or "").lower()
            if name == "description" and self.meta_description is None:
                self.meta_description = (attrs_dict.get("content") or "").strip() or None
        elif t == "h1":
            self.h1_count += 1
        elif t == "h2":
            self.h2_count += 1
        elif t == "img":
            self.images_total += 1
            if not (attrs_dict.get("alt") or "").strip():
                self.images_missing_alt += 1
        elif t == "a":
            href = (attrs_dict.get("href") or "").strip()
            if href:
                self.links.append(href)
        elif t == "script":
            if (attrs_dict.get("type") or "").strip().lower() == "application/ld+json":
                self.schema_count += 1
            src = (attrs_dict.get("src") or "").strip()
            if src:
                self.script_srcs.append(src)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t == "title":
            self.in_title = False
        if t in {"script", "style", "noscript", "svg"} and self._skip_text_depth > 0:
            self._skip_text_depth -= 1

    def handle_data(self, data: str) -> None:
        cleaned = re.sub(r"\s+", " ", data).strip()
        if not cleaned:
            return
        if self.in_title:
            self.title_parts.append(cleaned)
        if self._skip_text_depth == 0:
            self.visible_text_parts.append(cleaned)


def normalize_url(raw_url: str) -> str:
    parsed = urllib.parse.urlparse(raw_url)
    if not parsed.scheme:
        return f"https://{raw_url}"
    return raw_url


def fetch_page(url: str) -> Page:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        content = response.read().decode("utf-8", errors="replace")
        status = getattr(response, "status", 200) or 200
        final_url = response.geturl()
        return Page(requested_url=url, final_url=final_url, status_code=status, text=content)


def quick_get_exists(url: str) -> bool:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            return getattr(response, "status", 500) < 400
    except urllib.error.URLError:
        return False


def count_internal_external_links(links: list[str], base_url: str) -> tuple[int, int]:
    base_domain = urllib.parse.urlparse(base_url).netloc.replace("www.", "")
    internal = 0
    external = 0
    for href in links:
        if href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        absolute = urllib.parse.urljoin(base_url, href)
        domain = urllib.parse.urlparse(absolute).netloc.replace("www.", "")
        if not domain or domain == base_domain:
            internal += 1
        else:
            external += 1
    return internal, external


def analyze_page(page: Page) -> tuple[SEOReport, AdsSignals, CopyReview]:
    parser = SimpleHTMLAnalyzer()
    parser.feed(page.text)

    title = " ".join(parser.title_parts).strip() or None
    visible_text = " ".join(parser.visible_text_parts)
    words = re.findall(r"\b\w+\b", visible_text)
    internal_links, external_links = count_internal_external_links(parser.links, page.final_url)

    base = urllib.parse.urlparse(page.final_url)
    root = f"{base.scheme}://{base.netloc}"

    seo = SEOReport(
        final_url=page.final_url,
        status_code=page.status_code,
        title=title,
        title_length=len(title or ""),
        meta_description=parser.meta_description,
        meta_description_length=len(parser.meta_description or ""),
        h1_count=parser.h1_count,
        h2_count=parser.h2_count,
        word_count=len(words),
        images_total=parser.images_total,
        images_missing_alt=parser.images_missing_alt,
        internal_links=internal_links,
        external_links=external_links,
        schema_count=parser.schema_count,
        robots_txt_found=quick_get_exists(urllib.parse.urljoin(root, "/robots.txt")),
        sitemap_found=quick_get_exists(urllib.parse.urljoin(root, "/sitemap.xml")),
    )

    ads = detect_google_ads_signals(page.text, parser.script_srcs)
    copy = build_copy_review(visible_text)
    return seo, ads, copy


def detect_google_ads_signals(html_text: str, script_srcs: list[str]) -> AdsSignals:
    evidence: list[str] = []
    haystack = html_text.lower()

    patterns = {
        "google ads conversion ID (AW-)": r"aw-\d{4,}",
        "googleadservices script": r"googleadservices\.com",
        "doubleclick domain": r"doubleclick\.net",
        "googlesyndication domain": r"googlesyndication\.com",
        "gtag conversion event": r"gtag\s*\(\s*['\"]event['\"]\s*,\s*['\"]conversion['\"]",
        "gclid tracking parameter": r"[?&]gclid=",
    }

    for label, pattern in patterns.items():
        if re.search(pattern, haystack, re.I):
            evidence.append(label)

    for src in script_srcs:
        if "googletagmanager.com" in src and "gtag/js" in src:
            evidence.append("gtag.js loaded")
            break

    unique_evidence = sorted(set(evidence))
    score = len(unique_evidence)
    confidence = "none"
    if score >= 3:
        confidence = "high"
    elif score == 2:
        confidence = "medium"
    elif score == 1:
        confidence = "low"

    return AdsSignals(
        is_likely_running_google_ads=score >= 2,
        confidence=confidence,
        evidence=unique_evidence,
    )


def count_syllables(word: str) -> int:
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return 0
    groups = re.findall(r"[aeiouy]+", word)
    syllables = len(groups)
    if word.endswith("e") and syllables > 1:
        syllables -= 1
    return max(syllables, 1)


def flesch_reading_ease(text: str) -> float:
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    words = re.findall(r"\b[a-zA-Z']+\b", text)
    if not sentences or not words:
        return 0.0
    syllable_count = sum(count_syllables(word) for word in words)
    words_per_sentence = len(words) / len(sentences)
    syllables_per_word = syllable_count / len(words)
    score = 206.835 - 1.015 * words_per_sentence - 84.6 * syllables_per_word
    return round(score, 2)


def find_matching_phrases(text: str, candidates: Iterable[str]) -> list[str]:
    lowered = text.lower()
    return [phrase for phrase in candidates if phrase.lower() in lowered]


def build_copy_review(text: str) -> CopyReview:
    cta_candidates = [
        "call now",
        "book now",
        "schedule",
        "get quote",
        "request estimate",
        "contact us",
        "free inspection",
    ]
    trust_candidates = [
        "reviews",
        "testimonials",
        "warranty",
        "ase certified",
        "family owned",
        "guarantee",
        "years of experience",
    ]
    local_candidates = ["near me", "serving", "local"]

    readability = flesch_reading_ease(text)
    ctas = find_matching_phrases(text, cta_candidates)
    trust = find_matching_phrases(text, trust_candidates)
    local_terms = find_matching_phrases(text, local_candidates)

    recommendations: list[str] = []
    if readability < 50:
        recommendations.append("Simplify sentence structure so content is easier to skim quickly.")
    if not ctas:
        recommendations.append("Add a stronger call-to-action above the fold (ex: 'Call now' or 'Request estimate').")
    if len(trust) < 2:
        recommendations.append("Add trust proof like review count, certifications, warranties, or guarantees.")
    if not local_terms:
        recommendations.append("Use location-based language to improve local relevance (city/service area mentions).")

    word_lengths = [len(w) for w in re.findall(r"\b\w+\b", text)]
    if word_lengths and statistics.mean(word_lengths) > 6:
        recommendations.append("Reduce jargon and long words so owners can understand value quickly.")

    if not recommendations:
        recommendations.append("Copy is generally solid; focus on conversion testing (CTA placement, social proof order, offer framing).")

    return CopyReview(
        readability_score=readability,
        cta_phrases_found=ctas,
        trust_signals_found=trust,
        local_terms_found=local_terms,
        recommendations=recommendations,
    )


def format_report(url: str, seo: SEOReport, ads: AdsSignals, copy: CopyReview) -> str:
    lines: list[str] = [
        f"Prospect URL: {url}",
        f"Final URL after redirects: {seo.final_url} (HTTP {seo.status_code})",
        "",
        "== SEO Snapshot ==",
        f"Title length: {seo.title_length} | Meta description length: {seo.meta_description_length}",
        f"H1: {seo.h1_count} | H2: {seo.h2_count} | Word count: {seo.word_count}",
        (
            f"Images: {seo.images_total} total ({seo.images_missing_alt} missing alt text) | "
            f"Links: {seo.internal_links} internal, {seo.external_links} external"
        ),
        f"Schema blocks: {seo.schema_count} | robots.txt: {seo.robots_txt_found} | sitemap.xml: {seo.sitemap_found}",
        "",
        "== Google Ads Signals ==",
        f"Likely running Google Ads: {ads.is_likely_running_google_ads} (confidence: {ads.confidence})",
        (
            "Evidence found: " + ", ".join(ads.evidence)
            if ads.evidence
            else "No direct Google Ads footprint found in page source."
        ),
        "",
        "== Copy & Messaging Review ==",
        f"Readability score (Flesch): {copy.readability_score}",
        f"CTA phrases found: {', '.join(copy.cta_phrases_found) if copy.cta_phrases_found else 'none'}",
        f"Trust signals found: {', '.join(copy.trust_signals_found) if copy.trust_signals_found else 'none'}",
        f"Local-language terms found: {', '.join(copy.local_terms_found) if copy.local_terms_found else 'none'}",
        "",
        "Recommended talking points for your sales call:",
    ]
    for rec in copy.recommendations:
        lines.append(f"- {rec}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sales call prep tool using only publicly available website data."
    )
    parser.add_argument("url", help="Prospect website URL (with or without https://)")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of a formatted report.")
    args = parser.parse_args()

    url = normalize_url(args.url)
    try:
        page = fetch_page(url)
    except urllib.error.URLError as exc:
        raise SystemExit(f"Could not fetch {url}: {exc}")

    seo, ads, copy = analyze_page(page)

    if args.json:
        print(
            json.dumps(
                {
                    "url": url,
                    "seo": seo.__dict__,
                    "ads": ads.__dict__,
                    "copy": copy.__dict__,
                },
                indent=2,
            )
        )
        return

    print(format_report(url, seo, ads, copy))


if __name__ == "__main__":
    main()
