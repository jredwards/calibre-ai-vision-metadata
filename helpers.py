# __license__   = 'GPL v3'
# __copyright__ = '2026, RelUnrelated <dan@relunrelated.com>'
"""
Pure-Python helper functions with no Qt or Calibre dependencies.
Imported by main.py at runtime and by the test suite without a Calibre environment.
"""

import re
import json
import time
import urllib.request
import urllib.parse
import urllib.error
from difflib import SequenceMatcher

# ---------------------------------------------------------------------------
# Field registry
# ---------------------------------------------------------------------------

# Ordered list of (pref_key, display_label) for every field the plugin can write.
# This drives both the config checkboxes and the review dialog.
ALL_FIELDS = [
    ('title',        'Title'),
    ('authors',      'Author(s)'),
    ('languages',    'Languages'),
    ('publisher',    'Publisher'),
    ('pubdate',      'Published Date'),
    ('identifiers',  'Identifiers (ISBN)'),
]

# Groups shown in the configuration page, ordered by data source.
# Each entry: (section_label, [field_keys])
FIELD_GROUPS = [
    (
        'From AI scan (read from cover image, verified against Google Books)',
        ['title', 'authors', 'languages', 'publisher'],
    ),
    (
        'From Google Books (populated when book is verified; publisher above used as fallback if not on cover)',
        ['pubdate', 'identifiers'],
    ),
]
ALL_FIELD_KEYS = [k for k, _ in ALL_FIELDS]

# ---------------------------------------------------------------------------
# Null detection
# ---------------------------------------------------------------------------

def is_null_value(v):
    """Return True if v represents a missing / empty AI value.

    JSON null → Python None; the AI also sometimes returns the string "null".
    Lists (tags, languages) are null when empty.
    """
    if isinstance(v, list):
        return len(v) == 0
    return v in (None, 'null', 'None', '')


def strip_null_values(metadata):
    """Remove keys whose value is null/empty from a raw AI metadata dict."""
    return {k: v for k, v in metadata.items() if not is_null_value(v)}

# ---------------------------------------------------------------------------
# Title cleanup
# ---------------------------------------------------------------------------

_LOWERCASE_WORDS = frozenset({
    'a', 'an', 'the', 'and', 'but', 'or', 'nor', 'for', 'yet', 'so',
    'at', 'by', 'in', 'of', 'on', 'to', 'up', 'as', 'vs', 'via',
})

def clean_title(title):
    """Correct title capitalisation only when the AI returned ALL CAPS or all lowercase.

    Leaves already-mixed titles (correct or intentional) untouched.
    Applies standard title-case rules: articles/prepositions stay lowercase unless
    they are the first or last word.
    """
    if not isinstance(title, str):
        return title
    alpha_chars = [c for c in title if c.isalpha()]
    if not alpha_chars:
        return title
    # Only intervene when every alpha character is the same case
    if not (all(c.isupper() for c in alpha_chars) or all(c.islower() for c in alpha_chars)):
        return title
    words = title.split()
    result = []
    for i, word in enumerate(words):
        bare_lower = word.lower().strip('.,;:!?"\'-()[]{}')
        if i == 0 or i == len(words) - 1 or bare_lower not in _LOWERCASE_WORDS:
            result.append(word.capitalize())
        else:
            result.append(word.lower())
    return ' '.join(result)

# ---------------------------------------------------------------------------
# Author name cleanup
# ---------------------------------------------------------------------------

def clean_author_name(name):
    """Normalise a single author name string.

    Rules applied in order:
    1. "Lastname, Firstname" → "Firstname Lastname"
    2. Reject any name whose *last* token is a lone initial (e.g. "John S." → None)
    3. Format initials:
         "J"      → "J."
         "JK"     → "J.K."    (2 adjacent all-caps letters with no dots)
         "J.K."   → "J.K."    (already dotted, re-normalised for consistency)
         "J.R.R." → "J.R.R."
    4. ALL-CAPS name tokens → Title Case  ("ROWLING" → "Rowling")
    5. Mixed-case tokens left untouched.

    Returns None if the name is rejected.
    """
    if not isinstance(name, str):
        return None
    name = name.strip()
    if not name:
        return None

    # Strip AI placeholder sequences: "Niccol{} Machiavelli" → "Niccol Machiavelli"
    name = re.sub(r'\{[^}]*\}', '', name).strip()
    if not name:
        return None

    # Known suffixes that follow a comma but are NOT "Lastname, Firstname"
    _SUFFIXES = {
        'jr', 'sr', 'ii', 'iii', 'iv', 'v',
        'md', 'phd', 'dds', 'do', 'jd', 'mba', 'ms', 'esq',
    }

    # Rule 1: "Lastname, Firstname" → "Firstname Lastname"
    # But if the part after the comma is a known suffix, drop it instead of reversing.
    if ',' in name:
        parts = name.split(',', 1)
        after = parts[1].strip()
        after_bare = after.replace('.', '').replace(' ', '').lower()
        if after_bare in _SUFFIXES:
            name = parts[0].strip()   # discard the suffix
        else:
            name = after + ' ' + parts[0].strip()

    tokens = name.split()
    if not tokens:
        return None

    # Rule 2: reject trailing initial
    last_bare = tokens[-1].replace('.', '').strip()
    if len(last_bare) == 1 and last_bare.isalpha():
        return None

    normalized = []
    for token in tokens:
        bare = token.replace('.', '').strip()
        if not bare or not bare.isalpha():
            normalized.append(token)
            continue

        # Already dot-formatted initials (e.g. "J.K.", "J.R.R.") → re-normalise
        if '.' in token and bare.isupper() and len(bare) <= 4:
            normalized.append('.'.join(bare) + '.')
            continue

        # Single letter → "J."
        if len(bare) == 1:
            normalized.append(bare.upper() + '.')
            continue

        # Two adjacent all-caps letters with no dots → "J.K."
        if len(bare) == 2 and bare.isupper() and '.' not in token:
            normalized.append(bare[0] + '.' + bare[1] + '.')
            continue

        # Remaining all-caps word → Title Case
        if bare.isupper():
            normalized.append(bare.capitalize())
            continue

        # Mixed or already-correct casing → leave alone
        normalized.append(token)

    return ' '.join(normalized)

# ---------------------------------------------------------------------------
# Google Books verification
# ---------------------------------------------------------------------------

def _default_fetch(url, _retries=3, _backoff=1):
    """Fetch a URL, retrying on 429 with exponential backoff."""
    req = urllib.request.Request(url, headers={'User-Agent': 'CalibreAIVisionPlugin/1.0'})
    for attempt in range(_retries):
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < _retries - 1:
                time.sleep(_backoff * (2 ** attempt))  # 1s, 2s
                continue
            raise


def verify_with_google_books(title, creators, api_key=None, _fetch_fn=None):
    """Query Google Books to verify and correct the title/author combination.

    Two-pass strategy:
      Pass 1 — title + author query.
      Pass 2 — title only, if pass 1 returned nothing.

    Takes Google's top result and validates with a fuzzy title match (>= 0.85).
    _fetch_fn is injectable for testing (default: real HTTP call).

    Returns {'status': 'verified'|'corrected'|'title_only'|'unverified',
             'corrections': {'title': {...}, 'authors': {...}}}
    """
    fetch = _fetch_fn if _fetch_fn is not None else _default_fetch

    _RATE_LIMITED = object()  # sentinel distinct from None (other error) and [] (no results)

    def run_query(q):
        url = f'https://www.googleapis.com/books/v1/volumes?q={q}&maxResults=1'
        if api_key:
            url += f'&key={urllib.parse.quote(api_key)}'
        try:
            return fetch(url).get('items', [])
        except urllib.error.HTTPError as e:
            if e.code == 429:
                return _RATE_LIMITED
            return None
        except Exception:
            return None

    def done(corrections):
        return {'status': 'corrected' if corrections else 'verified', 'corrections': corrections}

    # Primary creator string (first element, or None)
    raw = (creators[0] if isinstance(creators, list) else str(creators)).strip() if creators else ''
    creator_str = raw or None

    # Pass 1: title + author; Pass 2: title only
    inauthor = f'+inauthor:{urllib.parse.quote(creator_str.replace(".", " "))}' if creator_str else ''
    items = run_query(f'intitle:{urllib.parse.quote(title)}{inauthor}')
    if items is _RATE_LIMITED:
        return {'status': 'rate_limited', 'corrections': {}}
    if items is None:
        return {'status': 'unverified', 'corrections': {}}
    if not items:
        items = run_query(f'intitle:{urllib.parse.quote(title)}') or []
        if items is _RATE_LIMITED:
            return {'status': 'rate_limited', 'corrections': {}}
    if not items:
        return {'status': 'unverified', 'corrections': {}}

    volume_info = items[0].get('volumeInfo', {})
    # Strip trailing edition suffixes: "On Wings of Blood (Standard Edition)" → "On Wings of Blood"
    books_title_raw = volume_info.get('title', '')
    books_title = re.sub(r'\s*\([^)]*\)\s*$', '', books_title_raw).strip() or books_title_raw
    books_authors = volume_info.get('authors', [])

    # Title must fuzzy-match at >= 0.85 (case-insensitive)
    if SequenceMatcher(None, title.lower(), books_title.lower()).ratio() < 0.85:
        return {'status': 'unverified', 'corrections': {}}

    corrections = {}
    if title.lower() != books_title.lower():
        corrections['title'] = {'from': title, 'to': books_title}

    # Collect structured enrichment now that we have a confirmed title match
    enrichment = {}
    for id_entry in volume_info.get('industryIdentifiers', []):
        if id_entry.get('type') == 'ISBN_13':
            enrichment['isbn'] = id_entry.get('identifier', '')
            break
    if 'isbn' not in enrichment:
        for id_entry in volume_info.get('industryIdentifiers', []):
            if id_entry.get('type') == 'ISBN_10':
                enrichment['isbn'] = id_entry.get('identifier', '')
                break
    if volume_info.get('publisher'):
        enrichment['publisher'] = volume_info['publisher']
    if volume_info.get('publishedDate'):
        enrichment['pubdate'] = volume_info['publishedDate']
    if volume_info.get('language'):
        enrichment['language'] = volume_info['language']

    def done(corrections):
        result = {'status': 'corrected' if corrections else 'verified', 'corrections': corrections}
        if enrichment:
            result['enrichment'] = enrichment
        return result

    if not books_authors:
        return done(corrections)

    canonical_raw = books_authors[0]
    canonical_cleaned = clean_author_name(canonical_raw)

    if creator_str is None:
        if canonical_cleaned:
            corrections['authors'] = {'from': None, 'to': canonical_cleaned}
        return done(corrections)

    # Author fuzzy-match at >= 0.82 (whole-string, case-insensitive)
    if SequenceMatcher(None, creator_str.lower(), canonical_raw.lower()).ratio() >= 0.82:
        if canonical_cleaned and canonical_cleaned != creator_str:
            corrections['authors'] = {'from': creator_str, 'to': canonical_cleaned}
        return done(corrections)

    return {'status': 'title_only', 'corrections': corrections, 'enrichment': enrichment}

# ---------------------------------------------------------------------------
# Approved-data builder (batch auto-apply path)
# ---------------------------------------------------------------------------

_NULL_VALUES = (None, 'null', 'None', '')

def build_approved_data(metadata, enabled_fields):
    """Convert raw AI metadata into the approved_data dict that apply_metadata() expects.

    Only includes fields that are both enabled in settings and have a non-null value.
    Mirrors the field transformations the review dialog applies (list→CSV, pubdate assembly).
    """
    approved = {}

    if 'title' in enabled_fields:
        val = metadata.get('title')
        if val not in _NULL_VALUES:
            approved['title'] = str(val).strip()

    if 'authors' in enabled_fields:
        raw = metadata.get('creators')
        if not raw:
            raw = metadata.get('editor') or metadata.get('author')
            raw = [raw] if raw else []
        creators_str = ', '.join(str(c) for c in raw if c) if isinstance(raw, list) else str(raw)
        if creators_str.strip():
            approved['authors'] = creators_str.strip()

    if 'languages' in enabled_fields:
        langs = metadata.get('languages')
        if langs:
            approved['languages'] = ', '.join(str(l) for l in langs if l) if isinstance(langs, list) else str(langs)

    if 'publisher' in enabled_fields:
        val = metadata.get('publisher')
        if val not in _NULL_VALUES:
            approved['publisher'] = str(val).strip()

    if 'pubdate' in enabled_fields:
        year_raw = metadata.get('pub_year')
        if year_raw and str(year_raw).strip().isdigit():
            year = str(year_raw).strip()
            month_raw = metadata.get('pub_month')
            month = str(month_raw).strip().zfill(2) if month_raw and str(month_raw).strip().isdigit() else '01'
            day_raw = metadata.get('pub_day')
            day = str(day_raw).strip().zfill(2) if day_raw and str(day_raw).strip().isdigit() else '01'
            approved['pubdate'] = f'{year}-{month}-{day}'

    if 'identifiers' in enabled_fields:
        val = metadata.get('identifiers')
        if val not in _NULL_VALUES:
            approved['identifiers'] = str(val).strip()

    return approved
