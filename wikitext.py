#!/usr/bin/env python3
"""
wikitext.py - turn a Wikipedia article into plain, readable text.

Keeps: the title, headings, paragraphs and bullet lists.
Removes: images and captions, infoboxes, tables, citation marks like [1] or
[note 2], and the References / Notes / External links style sections.

Setup (one time, in Command Prompt or PowerShell):
    pip install requests beautifulsoup4

Usage:
    python wikitext.py https://en.wikipedia.org/wiki/Alan_Turing
    python wikitext.py "Alan Turing"
    python wikitext.py page.html            (a saved Wikipedia page)
    python wikitext.py                      (it will ask you for a link)

The result is saved as a .txt file in the current folder.
"""

import os
import re
import sys
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup

# Sections that are dropped completely (heading and everything under it).
SKIP_SECTIONS = {
    "references", "notes", "footnotes", "citations", "further reading",
    "external links", "see also", "bibliography", "sources", "works cited",
    "notes and references", "references and notes",
}

# Elements that are removed before extracting text.
REMOVE_SELECTORS = [
    "style", "script", "figure", "img", "table", "sup", "audio", "video",
    ".thumb", ".thumbinner", ".thumbcaption", ".gallery", ".infobox",
    ".navbox", ".vertical-navbox", ".sidebar", ".hatnote", ".dablink",
    ".mw-editsection", ".reference", ".reflist", ".references",
    ".mw-references-wrap", ".refbegin", ".toc", "#toc", ".metadata",
    ".ambox", ".noprint", ".mw-empty-elt", ".shortdescription",
    ".mbox-small", ".portal", ".navigation-not-searchable", ".mw-cite-backlink",
]

# Leftover citation-style marks, e.g. [1] [12] [a] [note 3] [citation needed]
CITATION_RE = re.compile(
    r"\[\s*(?:\d+|[a-z]|note\s*\d+|nb\s*\d+|citation needed|clarification needed|"
    r"when\?|who\?|according to whom\?|dubious\s*[–-]\s*discuss|"
    r"edit|update|verification needed)\s*\]",
    re.IGNORECASE,
)

HEADERS = {"User-Agent": "wikitext-script/1.0 (personal text-cleaning tool)"}


def fetch_article(source):
    """Return (title, html) for a URL, a page title, or a local .html file."""
    if os.path.isfile(source):
        with open(source, "r", encoding="utf-8", errors="replace") as f:
            html = f.read()
        soup = BeautifulSoup(html, "html.parser")
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else os.path.splitext(os.path.basename(source))[0]
        content = soup.select_one("#mw-content-text") or soup.body or soup
        return title, str(content)

    lang = "en"
    if source.lower().startswith(("http://", "https://")):
        parsed = urlparse(source)
        host = parsed.netloc.split(".")
        if len(host) >= 3 and host[1] == "wikipedia":
            lang = host[0]
        if "/wiki/" in parsed.path:
            page = unquote(parsed.path.split("/wiki/", 1)[1])
        else:
            page = parse_qs_title(parsed.query)
    else:
        page = source

    api = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "parse", "page": page, "prop": "text",
        "format": "json", "formatversion": 2, "redirects": 1,
    }
    r = requests.get(api, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise SystemExit(f"Wikipedia says: {data['error'].get('info', 'unknown error')}")
    return data["parse"]["title"], data["parse"]["text"]


def parse_qs_title(query):
    from urllib.parse import parse_qs
    return parse_qs(query).get("title", [""])[0]


def clean_text(text):
    text = CITATION_RE.sub("", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)  # no space before punctuation
    text = re.sub(r"\(\s*\)", "", text)            # empty parentheses
    return text.strip()


def article_to_text(title, html):
    soup = BeautifulSoup(html, "html.parser")

    for selector in REMOVE_SELECTORS:
        for el in soup.select(selector):
            el.decompose()

    lines = [title, ""]
    skipping = False
    skip_level = 0

    for el in soup.find_all(["h2", "h3", "h4", "h5", "h6", "p", "li", "dd"]):
        if el.name[0] == "h":
            level = int(el.name[1])
            heading = clean_text(el.get_text(" ", strip=True))
            if skipping and level <= skip_level:
                skipping = False
            if not skipping and heading.lower() in SKIP_SECTIONS:
                skipping = True
                skip_level = level
            if skipping or not heading:
                continue
            lines.extend(["", heading, ""])
            continue

        if skipping:
            continue

        # For list items, don't repeat the text of nested lists
        # (the nested items are visited on their own).
        if el.name == "li":
            for nested in el.find_all(["ul", "ol"]):
                nested.extract()

        text = clean_text(el.get_text(" ", strip=True))
        if not text:
            continue

        if el.name == "li":
            lines.append(f"- {text}")
        else:
            lines.extend([text, ""])

    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip() + "\n"


def safe_filename(title):
    name = re.sub(r'[<>:"/\\|?*]', "_", title).strip()
    return (name or "wikipedia_page") + ".txt"


def main():
    interactive = len(sys.argv) < 2
    if interactive:
        source = input("Paste a Wikipedia link, article title, or .html file: ").strip().strip('"')
    else:
        source = " ".join(sys.argv[1:]).strip().strip('"')
    if not source:
        raise SystemExit("Nothing to do.")

    try:
        title, html = fetch_article(source)
    except requests.RequestException as e:
        raise SystemExit(f"Could not download the page: {e}")

    text = article_to_text(title, html)
    filename = safe_filename(title)
    with open(filename, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"Saved: {os.path.abspath(filename)}")
    if interactive:
        input("Press Enter to close...")


if __name__ == "__main__":
    main()
