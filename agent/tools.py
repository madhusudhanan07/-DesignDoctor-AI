"""DesignDoctor AI tools: website UI/UX audit tools.

Each tool fetches and analyses a real web page; no data is fabricated.
The one-line docstring is used by ToolSelector as the option description for Strands Decider 2B.
"""

from __future__ import annotations

import ipaddress
import json
import math
import re
import socket
import urllib.parse
import urllib.request
from typing import Any

from strands import tool

# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------

_BLOCKED_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _is_safe_url(url: str) -> tuple[bool, str]:
    """Return (True, "") for public HTTP/HTTPS URLs; (False, reason) otherwise."""
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False, "could not parse URL"
    if parsed.scheme not in ("http", "https"):
        return False, f"only http/https URLs are supported, got scheme '{parsed.scheme}'"
    host = parsed.hostname
    if not host:
        return False, "no hostname in URL"
    if host.lower() in ("localhost", "0.0.0.0"):
        return False, "private/localhost addresses are blocked"
    try:
        addrs = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False, f"could not resolve hostname '{host}'"
    for info in addrs:
        try:
            addr = ipaddress.ip_address(info[4][0])
            for net in _BLOCKED_NETS:
                if addr in net:
                    return False, f"private/internal IP address blocked: {addr}"
        except ValueError:
            pass
    return True, ""


# ---------------------------------------------------------------------------
# HTML fetch helper (shared by all tools)
# ---------------------------------------------------------------------------

_HTML_CACHE: dict[str, dict[str, Any]] = {}


def _fetch_page(url: str) -> dict[str, Any]:
    """Fetch a URL and extract structured page data. Cached per URL for one session."""
    if url in _HTML_CACHE:
        return _HTML_CACHE[url]

    safe, reason = _is_safe_url(url)
    if not safe:
        return {"error": reason, "url": url}

    # Try httpx first (fast, available in venv), fall back to urllib
    html = ""
    fetch_error = ""
    try:
        import httpx  # type: ignore[import]
        r = httpx.get(url, follow_redirects=True, timeout=15,
                      headers={"User-Agent": "DesignDoctorBot/1.0 (+https://github.com/designdoctor)"})
        r.raise_for_status()
        html = r.text
    except ImportError:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "DesignDoctorBot/1.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            fetch_error = str(e)
    except Exception as e:
        fetch_error = str(e)

    if not html and fetch_error:
        return {"error": f"could not fetch {url}: {fetch_error}", "url": url}

    result = _parse_html(url, html)
    _HTML_CACHE[url] = result
    return result


def _parse_html(url: str, html: str) -> dict[str, Any]:
    """Extract structured data from raw HTML without external dependencies."""
    try:
        from html.parser import HTMLParser

        class _P(HTMLParser):
            def __init__(self):
                super().__init__()
                self.title = ""
                self.meta_desc = ""
                self.headings: list[dict] = []
                self.images: list[dict] = []
                self.links: list[dict] = []
                self.lang = ""
                self.viewport = ""
                self.charset = ""
                self._in: list[str] = []
                self._text_buf: list[str] = []
                self.inline_styles: list[str] = []
                self.aria_labels: list[str] = []
                self.buttons: list[dict] = []
                self.inputs: list[dict] = []

            def handle_starttag(self, tag, attrs):
                a = dict(attrs)
                self._in.append(tag)
                if tag == "html":
                    self.lang = a.get("lang", "")
                if tag == "meta":
                    name = a.get("name", "").lower()
                    prop = a.get("property", "").lower()
                    if name == "description" or prop == "og:description":
                        self.meta_desc = a.get("content", "")
                    if name == "viewport":
                        self.viewport = a.get("content", "")
                    if a.get("charset"):
                        self.charset = a["charset"]
                if tag == "img":
                    self.images.append({
                        "src": a.get("src", ""),
                        "alt": a.get("alt"),
                        "width": a.get("width"),
                        "height": a.get("height"),
                        "loading": a.get("loading", ""),
                    })
                if tag == "a":
                    self.links.append({
                        "href": a.get("href", ""),
                        "aria_label": a.get("aria-label", ""),
                        "text": "",  # filled in handle_data
                    })
                if tag in ("button", "input") and "style" in a:
                    self.inline_styles.append(a["style"])
                if tag == "button":
                    self.buttons.append({
                        "text": "",
                        "aria_label": a.get("aria-label", ""),
                        "type": a.get("type", "button"),
                    })
                if tag == "input":
                    self.inputs.append({
                        "type": a.get("type", "text"),
                        "aria_label": a.get("aria-label", ""),
                        "placeholder": a.get("placeholder", ""),
                        "id": a.get("id", ""),
                    })
                if "aria-label" in a:
                    self.aria_labels.append(a["aria-label"])
                if "style" in a:
                    self.inline_styles.append(a["style"])

            def handle_endtag(self, tag):
                if self._in and self._in[-1] == tag:
                    self._in.pop()

            def handle_data(self, data):
                cur = self._in[-1] if self._in else ""
                if cur == "title" and not self.title:
                    self.title = data.strip()
                if cur in ("h1", "h2", "h3", "h4", "h5", "h6"):
                    self.headings.append({"level": int(cur[1]), "text": data.strip()})
                if self.links and not self.links[-1]["text"]:
                    self.links[-1]["text"] = data.strip()
                if self.buttons and not self.buttons[-1]["text"]:
                    self.buttons[-1]["text"] = data.strip()

        p = _P()
        p.feed(html)

        # Extract <style> blocks
        style_blocks = re.findall(r"<style[^>]*>(.*?)</style>", html, re.DOTALL | re.I)
        css_text = "\n".join(style_blocks)

        # Extract font-size values from inline styles + style blocks
        font_sizes = re.findall(r"font-size\s*:\s*([^;\"']+)", css_text + " " + " ".join(p.inline_styles), re.I)

        # Count link-with-no-text or no-aria
        empty_links = sum(1 for lk in p.links if not lk["text"].strip() and not lk["aria_label"])
        images_missing_alt = sum(1 for im in p.images if im["alt"] is None)
        images_empty_alt = sum(1 for im in p.images if im["alt"] == "")
        images_without_dimensions = sum(1 for im in p.images if not im["width"] or not im["height"])
        lazy_images = sum(1 for im in p.images if im.get("loading") == "lazy")

        # Heading hierarchy check
        levels = [h["level"] for h in p.headings]
        h1_count = levels.count(1)
        heading_skip = False
        for i in range(1, len(levels)):
            if levels[i] - levels[i - 1] > 1:
                heading_skip = True
                break

        # Colour contrast — extract background/color pairs from inline styles
        contrast_pairs = _extract_contrast_pairs(p.inline_styles + [css_text])

        # External resources (rough render-blocking detection)
        blocking_scripts = len(re.findall(r"<script(?![^>]*\b(?:defer|async)\b)[^>]*src=", html, re.I))
        blocking_css = len(re.findall(r"<link[^>]*rel=[\"']stylesheet[\"'][^>]*>", html, re.I))

        return {
            "url": url,
            "title": p.title,
            "lang": p.lang,
            "viewport": p.viewport,
            "charset": p.charset,
            "meta_description": p.meta_desc,
            "headings": p.headings[:40],
            "h1_count": h1_count,
            "heading_skip": heading_skip,
            "images_total": len(p.images),
            "images_missing_alt": images_missing_alt,
            "images_empty_alt": images_empty_alt,
            "images_without_dimensions": images_without_dimensions,
            "lazy_images": lazy_images,
            "links_total": len(p.links),
            "links_empty": empty_links,
            "buttons_total": len(p.buttons),
            "inputs_total": len(p.inputs),
            "inputs": p.inputs[:20],
            "font_sizes_found": font_sizes[:20],
            "inline_style_count": len(p.inline_styles),
            "blocking_scripts": blocking_scripts,
            "blocking_css": blocking_css,
            "contrast_pairs": contrast_pairs[:10],
            "css_text_sample": css_text[:2000],
            "html_length": len(html),
        }
    except Exception as e:
        return {"url": url, "parse_error": str(e), "html_length": len(html)}


def _hex_to_rgb(h: str) -> tuple[int, int, int] | None:
    h = h.strip().lstrip("#")
    try:
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        pass
    return None


def _relative_luminance(r: int, g: int, b: int) -> float:
    def c(v: float) -> float:
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * c(r) + 0.7152 * c(g) + 0.0722 * c(b)


def _contrast_ratio(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    l1 = _relative_luminance(*c1)
    l2 = _relative_luminance(*c2)
    bright, dark = max(l1, l2), min(l1, l2)
    return (bright + 0.05) / (dark + 0.05)


def _extract_contrast_pairs(styles: list[str]) -> list[dict]:
    pairs = []
    color_re = re.compile(r"color\s*:\s*(#[0-9a-fA-F]{3,6})", re.I)
    bg_re = re.compile(r"background(?:-color)?\s*:\s*(#[0-9a-fA-F]{3,6})", re.I)
    for style in styles:
        colors = color_re.findall(style)
        bgs = bg_re.findall(style)
        for fg_hex, bg_hex in zip(colors, bgs):
            fg = _hex_to_rgb(fg_hex)
            bg = _hex_to_rgb(bg_hex)
            if fg and bg:
                ratio = _contrast_ratio(fg, bg)
                pairs.append({
                    "fg": fg_hex, "bg": bg_hex,
                    "ratio": round(ratio, 2),
                    "aa_pass": ratio >= 4.5,
                    "aaa_pass": ratio >= 7.0,
                })
    return pairs


# ---------------------------------------------------------------------------
# Audit tools
# ---------------------------------------------------------------------------

@tool
def audit_accessibility(url: str) -> dict:
    """Audit accessibility: ARIA labels, alt text, colour contrast, form labels, keyboard nav hints."""
    page = _fetch_page(url)
    if "error" in page:
        return page

    issues = []

    # Track what was actually checked vs what could not be verified
    checks_performed = []
    checks_not_performed = [
        "keyboard navigation (requires browser automation)",
        "focus order and focus visibility (requires browser)",
        "screen reader announcements (requires assistive technology)",
        "dynamic content / ARIA live regions (requires JavaScript execution)",
        "colour contrast from external stylesheets (only inline/<style> blocks analysed)",
        "touch target sizes (requires rendered layout)",
    ]

    # ── Images ────────────────────────────────────────────────────────
    missing = page.get("images_missing_alt", 0)
    empty = page.get("images_empty_alt", 0)
    total_img = page.get("images_total", 0)
    checks_performed.append(f"alt attributes on {total_img} <img> element(s)")
    if missing > 0:
        issues.append({
            "severity": "critical",
            "category": "Images",
            "finding": f"{missing} of {total_img} image(s) have no alt attribute at all.",
            "fix": "Add an alt attribute to every <img>. For decorative images use alt=\"\".",
            "wcag": "1.1.1 Non-text Content (Level A)",
        })
    if empty > 0 and total_img > 0:
        pct = round(empty / total_img * 100)
        if pct > 40:
            issues.append({
                "severity": "warning",
                "category": "Images",
                "finding": f"{empty} image(s) ({pct}%) have empty alt text. Confirm these are purely decorative.",
                "fix": "Replace empty alt=\"\" with a meaningful description for any image conveying content.",
                "wcag": "1.1.1 Non-text Content (Level A)",
            })

    # ── Links ─────────────────────────────────────────────────────────
    total_links = page.get("links_total", 0)
    empty_links = page.get("links_empty", 0)
    checks_performed.append(f"link text / aria-label on {total_links} <a> element(s)")
    if empty_links > 0:
        issues.append({
            "severity": "critical",
            "category": "Links",
            "finding": f"{empty_links} link(s) have no visible text and no aria-label.",
            "fix": "Add aria-label or visible text so screen-reader users know where the link goes.",
            "wcag": "2.4.4 Link Purpose (Level A)",
        })

    # ── Language ──────────────────────────────────────────────────────
    checks_performed.append("lang attribute on <html>")
    if not page.get("lang"):
        issues.append({
            "severity": "critical",
            "category": "Language",
            "finding": "The <html> element has no lang attribute.",
            "fix": "Add lang=\"en\" (or the correct language code) to <html>.",
            "wcag": "3.1.1 Language of Page (Level A)",
        })

    # ── Form inputs ───────────────────────────────────────────────────
    inputs = page.get("inputs", [])
    checks_performed.append(f"labels on {len(inputs)} form input(s) found in HTML")
    unlabelled = [
        inp for inp in inputs
        if not inp.get("aria_label") and not inp.get("placeholder")
        and inp.get("type") not in ("hidden", "submit", "button", "image", "reset")
    ]
    if unlabelled:
        issues.append({
            "severity": "warning",
            "category": "Forms",
            "finding": f"{len(unlabelled)} input(s) have no aria-label or placeholder (associated <label> elements not checked — requires DOM linking).",
            "fix": "Associate a <label for='id'> element or add aria-label to every form control.",
            "wcag": "1.3.1 Info and Relationships (Level A)",
        })

    # ── Colour contrast (inline/<style> only) ─────────────────────────
    contrast_pairs = page.get("contrast_pairs", [])
    low_contrast = [p for p in contrast_pairs if not p["aa_pass"]]
    checks_performed.append(
        f"colour contrast on {len(contrast_pairs)} hex colour pair(s) found in inline styles and <style> blocks"
        + (" — external stylesheets were not fetched" if len(contrast_pairs) == 0 else "")
    )
    if low_contrast:
        issues.append({
            "severity": "warning",
            "category": "Colour contrast",
            "finding": (
                f"{len(low_contrast)} text/background colour pair(s) from inline/<style> CSS "
                f"fail WCAG AA (4.5:1). Lowest ratio: {min(p['ratio'] for p in low_contrast):.2f}:1."
            ),
            "fix": "Adjust foreground or background colour to achieve at least 4.5:1 contrast ratio.",
            "wcag": "1.4.3 Contrast Minimum (Level AA)",
        })

    # ── Viewport ──────────────────────────────────────────────────────
    checks_performed.append("viewport meta tag")
    if not page.get("viewport"):
        issues.append({
            "severity": "warning",
            "category": "Mobile / zoom",
            "finding": "No <meta name=\"viewport\"> tag found.",
            "fix": "Add <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">.",
            "wcag": "1.4.4 Resize Text (Level AA)",
        })
    elif "user-scalable=no" in page.get("viewport", "").lower():
        issues.append({
            "severity": "critical",
            "category": "Mobile / zoom",
            "finding": "Viewport disables pinch-to-zoom (user-scalable=no). This blocks users who need to zoom.",
            "fix": "Remove user-scalable=no from the viewport meta tag.",
            "wcag": "1.4.4 Resize Text (Level AA)",
        })

    # ── Evidence-based score ──────────────────────────────────────────
    # Score starts at 0 and gains points only for checks that passed.
    # Categories: images, links, language, forms, contrast, viewport — 6 checks.
    passed = 0
    total_checks = 6
    if missing == 0:
        passed += 1
    if empty_links == 0:
        passed += 1
    if page.get("lang"):
        passed += 1
    if not unlabelled:
        passed += 1
    # Contrast: give credit only if pairs were actually found; if none found, do not award
    if len(contrast_pairs) > 0 and not low_contrast:
        passed += 1
    elif len(contrast_pairs) == 0:
        total_checks -= 1   # can't pass or fail what wasn't checked
    if page.get("viewport") and "user-scalable=no" not in page.get("viewport", "").lower():
        passed += 1

    score = round(passed / total_checks * 100) if total_checks > 0 else 0

    return {
        "url": url,
        "tool": "audit_accessibility",
        "score": score,
        "score_basis": f"{passed}/{total_checks} checks passed from HTML/CSS analysis only",
        "score_caveat": (
            "This score reflects only what static HTML analysis can verify. "
            "Full WCAG compliance requires browser-based testing with axe-core or similar, "
            "plus manual review with assistive technologies."
        ),
        "issues_count": len(issues),
        "issues": issues,
        "checks_performed": checks_performed,
        "checks_not_performed": checks_not_performed,
        "evidence": {
            "images_total": total_img,
            "images_missing_alt": missing,
            "images_empty_alt": empty,
            "links_total": total_links,
            "links_empty": empty_links,
            "lang": page.get("lang", "(none)"),
            "viewport": page.get("viewport", "(none)"),
            "contrast_pairs_checked": len(contrast_pairs),
            "contrast_fails": len(low_contrast),
        },
    }


@tool
def audit_typography(url: str) -> dict:
    """Audit typography: font sizes, heading hierarchy, line-height, readability, and text density."""
    page = _fetch_page(url)
    if "error" in page:
        return page

    issues = []
    checks_performed = []
    checks_not_performed = [
        "actual rendered font sizes (external stylesheets not fetched)",
        "line-height and letter-spacing values (requires computed styles)",
        "font rendering and legibility (requires visual inspection)",
        "reading level / Flesch score (requires full page text extraction)",
    ]

    # ── Heading structure ─────────────────────────────────────────────
    headings = page.get("headings", [])
    h1_count = page.get("h1_count", 0)
    heading_skip = page.get("heading_skip", False)
    checks_performed.append(f"heading hierarchy ({len(headings)} heading(s) found in HTML)")

    if len(headings) == 0:
        issues.append({
            "severity": "warning",
            "category": "Content structure",
            "finding": "No headings (h1–h6) found in HTML. The page may have no scannable structure, or headings may be rendered via JavaScript.",
            "fix": "Add headings (h1–h3) to break content into sections.",
            "wcag": "2.4.6 Headings and Labels (Level AA)",
        })
    elif h1_count == 0:
        issues.append({
            "severity": "critical",
            "category": "Heading structure",
            "finding": "No <h1> found. The page has no primary heading declared in HTML.",
            "fix": "Add a single <h1> that describes the page's main topic.",
            "wcag": "1.3.1 Info and Relationships (Level A)",
        })
    elif h1_count > 1:
        issues.append({
            "severity": "warning",
            "category": "Heading structure",
            "finding": f"{h1_count} <h1> elements found; best practice is exactly one per page.",
            "fix": "Keep one <h1> per page for clear document structure.",
            "wcag": "1.3.1 Info and Relationships (Level A)",
        })

    if heading_skip and len(headings) > 1:
        issues.append({
            "severity": "warning",
            "category": "Heading structure",
            "finding": "Heading levels skip a level (e.g. h2 → h4). Screen readers rely on sequential headings.",
            "fix": "Use heading levels in order: h1 → h2 → h3, never skip a level.",
            "wcag": "1.3.1 Info and Relationships (Level A)",
        })

    # ── Font sizes (inline + <style> blocks only) ─────────────────────
    font_sizes = page.get("font_sizes_found", [])
    checks_performed.append(
        f"font-size values in inline styles and <style> blocks ({len(font_sizes)} value(s) found)"
    )
    small_fonts = []
    for fs in font_sizes:
        m = re.match(r"(\d+(?:\.\d+)?)\s*(px|pt|rem|em|%)?", fs.strip())
        if m:
            val, unit = float(m.group(1)), (m.group(2) or "px").lower()
            px = val if unit == "px" else (val * 16 if unit in ("rem", "em") else (val * 4 / 3 if unit == "pt" else val * 0.16))
            if px < 12:
                small_fonts.append(fs.strip())

    if small_fonts:
        issues.append({
            "severity": "warning",
            "category": "Font size",
            "finding": f"{len(small_fonts)} font-size value(s) in inline/style CSS appear smaller than 12 px: {', '.join(small_fonts[:5])}.",
            "fix": "Body text should be at least 16 px; labels and captions at least 12 px.",
            "wcag": "1.4.4 Resize Text (Level AA)",
        })

    # ── Meta description ──────────────────────────────────────────────
    checks_performed.append("meta description tag")
    if not page.get("meta_description"):
        issues.append({
            "severity": "info",
            "category": "Metadata",
            "finding": "No meta description found in HTML.",
            "fix": "Add <meta name=\"description\" content=\"...\"> summarising the page (120–160 chars).",
            "wcag": "N/A — SEO best practice",
        })

    # ── Evidence-based score ──────────────────────────────────────────
    passed = 0
    total_checks = 3
    if len(headings) > 0 and h1_count == 1 and not heading_skip:
        passed += 1
    if not small_fonts:
        passed += 1
    if page.get("meta_description"):
        passed += 1

    score = round(passed / total_checks * 100)

    return {
        "url": url,
        "tool": "audit_typography",
        "score": score,
        "score_basis": f"{passed}/{total_checks} checks passed from static HTML/CSS analysis",
        "score_caveat": "Actual typography quality (font rendering, readability, visual hierarchy) requires browser-based or visual inspection.",
        "issues_count": len(issues),
        "issues": issues,
        "checks_performed": checks_performed,
        "checks_not_performed": checks_not_performed,
        "evidence": {
            "headings_found": len(headings),
            "h1_count": h1_count,
            "heading_skip": heading_skip,
            "heading_list": [f"h{h['level']}: {h['text'][:50]}" for h in headings[:10]],
            "font_sizes_in_html": font_sizes[:10],
            "small_fonts": small_fonts,
            "meta_description_length": len(page.get("meta_description", "")),
        },
    }


@tool
def audit_layout(url: str) -> dict:
    """Audit layout: responsive design, viewport meta, spacing, overflow, and structural patterns."""
    page = _fetch_page(url)
    if "error" in page:
        return page

    issues = []
    checks_performed = []
    checks_not_performed = [
        "actual rendered layout and spacing (requires browser)",
        "flexbox/grid usage and alignment (requires computed styles)",
        "overflow on scroll (requires browser rendering)",
        "CSS from external stylesheets (only inline/<style> blocks analysed)",
    ]
    css = page.get("css_text_sample", "")

    # ── Viewport ──────────────────────────────────────────────────────
    viewport = page.get("viewport", "")
    checks_performed.append("viewport meta tag")
    if not viewport:
        issues.append({
            "severity": "critical",
            "category": "Responsive design",
            "finding": "No <meta name=\"viewport\"> tag found. The page will not scale on mobile devices.",
            "fix": "Add <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"> to <head>.",
            "wcag": "1.4.4 Resize Text (Level AA)",
        })
    elif "user-scalable=no" in viewport.lower() or "maximum-scale=1" in viewport.lower():
        issues.append({
            "severity": "critical",
            "category": "Responsive design",
            "finding": "Viewport disables pinch-to-zoom (user-scalable=no or maximum-scale=1).",
            "fix": "Remove user-scalable=no and maximum-scale constraints from the viewport meta tag.",
            "wcag": "1.4.4 Resize Text (Level AA)",
        })

    # ── Fixed widths in embedded CSS ─────────────────────────────────
    checks_performed.append("fixed pixel widths in inline/<style> CSS")
    fixed_wide = re.findall(r"width\s*:\s*([89]\d\d|[1-9]\d{3,})px", css, re.I)
    if fixed_wide:
        issues.append({
            "severity": "warning",
            "category": "Fixed widths",
            "finding": f"{len(fixed_wide)} fixed pixel width(s) ≥ 800 px found in embedded CSS "
                       f"({', '.join(sorted(set(fixed_wide[:5])))}px). These may cause horizontal overflow on small screens.",
            "fix": "Replace fixed pixel widths with percentages, max-width, or CSS Grid/Flexbox.",
            "wcag": "1.4.10 Reflow (Level AA)",
        })

    # ── Overflow hidden ───────────────────────────────────────────────
    checks_performed.append("overflow:hidden on body/html in embedded CSS")
    overflow_hidden = re.findall(r"(?:body|html)\s*\{[^}]*overflow\s*:\s*hidden", css, re.I)
    if overflow_hidden:
        issues.append({
            "severity": "warning",
            "category": "Overflow",
            "finding": "overflow:hidden on body or html found in embedded CSS. May clip content on small viewports.",
            "fix": "Use overflow-x:hidden only if intentional, and test at 320 px wide.",
            "wcag": "1.4.10 Reflow (Level AA)",
        })

    # ── Image dimensions ──────────────────────────────────────────────
    no_dim = page.get("images_without_dimensions", 0)
    total_img = page.get("images_total", 0)
    checks_performed.append(f"width/height attributes on {total_img} <img> element(s)")
    if no_dim > 0 and total_img > 0:
        issues.append({
            "severity": "warning",
            "category": "Images",
            "finding": f"{no_dim} of {total_img} image(s) have no width/height attributes. This causes Cumulative Layout Shift (CLS).",
            "fix": "Add explicit width and height attributes to every <img> so the browser reserves space before loading.",
            "wcag": "N/A — Core Web Vitals (CLS)",
        })

    # ── Media queries ─────────────────────────────────────────────────
    mq_count = len(re.findall(r"@media\s*\(", css, re.I))
    checks_performed.append(f"CSS @media queries in embedded styles ({mq_count} found)")
    if mq_count == 0:
        issues.append({
            "severity": "warning",
            "category": "Responsive design",
            "finding": "No @media queries found in embedded stylesheets. External CSS may have them, but could not be verified.",
            "fix": "Add @media breakpoints for mobile (≤ 640 px), tablet (≤ 1024 px), and desktop.",
            "wcag": "1.4.10 Reflow (Level AA)",
        })

    # ── Inline style count ────────────────────────────────────────────
    inline_count = page.get("inline_style_count", 0)
    if inline_count > 30:
        issues.append({
            "severity": "info",
            "category": "Code quality",
            "finding": f"{inline_count} inline style attributes found. Heavy use makes responsive adjustments harder.",
            "fix": "Move repeated styles to CSS classes or a stylesheet.",
            "wcag": "N/A — best practice",
        })

    # ── Evidence-based score ──────────────────────────────────────────
    passed = 0
    total_checks = 4
    if viewport and "user-scalable=no" not in viewport.lower():
        passed += 1
    if not fixed_wide:
        passed += 1
    if no_dim == 0 or total_img == 0:
        passed += 1
    if mq_count > 0:
        passed += 1

    score = round(passed / total_checks * 100)

    return {
        "url": url,
        "tool": "audit_layout",
        "score": score,
        "score_basis": f"{passed}/{total_checks} checks passed from static HTML/CSS analysis",
        "score_caveat": "Actual layout quality requires browser rendering. External stylesheets were not fetched.",
        "issues_count": len(issues),
        "issues": issues,
        "checks_performed": checks_performed,
        "checks_not_performed": checks_not_performed,
        "evidence": {
            "viewport": viewport or "(none)",
            "fixed_wide_widths_found": sorted(set(fixed_wide[:10])),
            "media_queries_in_html": mq_count,
            "inline_style_count": inline_count,
            "images_without_dimensions": no_dim,
            "images_total": total_img,
        },
    }


@tool
def audit_performance_hints(url: str) -> dict:
    """Audit performance hints: render-blocking resources, image lazy-loading, meta tags, and page weight."""
    page = _fetch_page(url)
    if "error" in page:
        return page

    issues = []
    checks_performed = []
    checks_not_performed = [
        "actual page load time (requires browser with network throttling)",
        "Largest Contentful Paint / First Input Delay / CLS (requires browser)",
        "JavaScript bundle sizes (external scripts not fetched)",
        "server response time and TTFB (requires network measurement)",
        "image file sizes (only lazy-loading attribute checked)",
    ]

    # ── Render-blocking scripts ───────────────────────────────────────
    blocking = page.get("blocking_scripts", 0)
    checks_performed.append(f"<script src> tags without async/defer ({blocking} found)")
    if blocking > 0:
        issues.append({
            "severity": "warning" if blocking <= 2 else "critical",
            "category": "Render-blocking scripts",
            "finding": f"{blocking} <script src=...> tag(s) without async or defer block page rendering.",
            "fix": "Add defer to scripts that don't need to run immediately, or async if execution order doesn't matter.",
            "wcag": "N/A — Core Web Vitals (LCP / FID)",
        })

    # ── External stylesheets ──────────────────────────────────────────
    blocking_css = page.get("blocking_css", 0)
    checks_performed.append(f"external stylesheet <link> tags ({blocking_css} found)")
    if blocking_css > 4:
        issues.append({
            "severity": "info",
            "category": "Render-blocking CSS",
            "finding": f"{blocking_css} external stylesheets found. Many external CSS files can delay First Contentful Paint.",
            "fix": "Combine or lazy-load non-critical CSS. Inline critical above-the-fold styles.",
            "wcag": "N/A — Core Web Vitals (FCP)",
        })

    # ── Lazy loading ──────────────────────────────────────────────────
    total_img = page.get("images_total", 0)
    lazy = page.get("lazy_images", 0)
    checks_performed.append(f"loading=\"lazy\" on {total_img} image(s) ({lazy} have it)")
    if total_img > 3 and lazy == 0:
        issues.append({
            "severity": "warning",
            "category": "Image lazy loading",
            "finding": f"Page has {total_img} images; none use loading=\"lazy\". All images load on initial page render.",
            "fix": "Add loading=\"lazy\" to images below the fold.",
            "wcag": "N/A — performance best practice",
        })

    # ── Meta / SEO ────────────────────────────────────────────────────
    meta_desc = page.get("meta_description", "")
    checks_performed.append("meta description tag")
    if not meta_desc:
        issues.append({
            "severity": "info",
            "category": "SEO / Meta",
            "finding": "No meta description tag found.",
            "fix": "Add a concise meta description (120–160 characters) summarising the page.",
            "wcag": "N/A — SEO best practice",
        })
    elif len(meta_desc) > 160:
        issues.append({
            "severity": "info",
            "category": "SEO / Meta",
            "finding": f"Meta description is {len(meta_desc)} chars; Google truncates at ~160.",
            "fix": "Shorten to 120–160 characters.",
            "wcag": "N/A — SEO best practice",
        })

    # ── Title ─────────────────────────────────────────────────────────
    title = page.get("title", "")
    checks_performed.append("page <title> tag")
    if not title:
        issues.append({
            "severity": "warning",
            "category": "SEO / Meta",
            "finding": "No <title> tag found.",
            "fix": "Add a descriptive <title> (50–60 characters) to the <head>.",
            "wcag": "2.4.2 Page Titled (Level A)",
        })
    elif len(title) > 60:
        issues.append({
            "severity": "info",
            "category": "SEO / Meta",
            "finding": f"Page title is {len(title)} chars ('{title[:50]}...'). Search engines show ~60.",
            "fix": "Keep the page title under 60 characters.",
            "wcag": "N/A — SEO best practice",
        })

    # ── Page weight ───────────────────────────────────────────────────
    html_len = page.get("html_length", 0)
    checks_performed.append(f"HTML document size ({round(html_len/1024,1)} KB)")
    if html_len > 500_000:
        issues.append({
            "severity": "warning",
            "category": "Page weight",
            "finding": f"HTML document is {html_len // 1024} KB. Very large HTML slows parsing.",
            "fix": "Move repeated data to APIs, lazy-load sections, and remove unused markup.",
            "wcag": "N/A — performance best practice",
        })

    # ── Charset ───────────────────────────────────────────────────────
    checks_performed.append("charset declaration")
    if not page.get("charset"):
        issues.append({
            "severity": "info",
            "category": "Encoding",
            "finding": "No charset declaration found in HTML.",
            "fix": "Add <meta charset=\"UTF-8\"> as the first tag in <head>.",
            "wcag": "N/A — best practice",
        })

    # ── Evidence-based score ──────────────────────────────────────────
    passed = 0
    total_checks = 5
    if blocking == 0:
        passed += 1
    if total_img <= 3 or lazy > 0:
        passed += 1
    if meta_desc and len(meta_desc) <= 160:
        passed += 1
    if title and len(title) <= 60:
        passed += 1
    if html_len <= 500_000:
        passed += 1

    score = round(passed / total_checks * 100)

    return {
        "url": url,
        "tool": "audit_performance_hints",
        "score": score,
        "score_basis": f"{passed}/{total_checks} checks passed from static HTML analysis",
        "score_caveat": "Real performance metrics (LCP, FID, CLS) require browser-based measurement with Lighthouse or WebPageTest.",
        "issues_count": len(issues),
        "issues": issues,
        "checks_performed": checks_performed,
        "checks_not_performed": checks_not_performed,
        "evidence": {
            "blocking_scripts": blocking,
            "external_stylesheets": blocking_css,
            "images_total": total_img,
            "lazy_images": lazy,
            "meta_description_chars": len(meta_desc),
            "title": title[:60],
            "html_size_kb": round(html_len / 1024, 1),
            "charset": page.get("charset", "(none)"),
        },
    }


TOOLS = [audit_accessibility, audit_typography, audit_layout, audit_performance_hints]
