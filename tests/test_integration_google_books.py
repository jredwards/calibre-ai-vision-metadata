"""
Integration tests for verify_with_google_books — these hit the real Google Books API.

Run with:   python -m pytest tests/test_integration_google_books.py -m integration -v
Skip with:  python -m pytest tests/  (default run omits integration tests)

Set GOOGLE_BOOKS_API_KEY in the environment to use an authenticated key and
avoid the 1,000 req/day anonymous quota.
"""
import os
import pytest
from helpers import verify_with_google_books

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# "Of Wings of Blood" → should correct to "On Wings of Blood"
#
# The AI misreads the stylised 'n' in "On" as 'f', returning "Of Wings of Blood".
# ---------------------------------------------------------------------------

def test_ocr_preposition_error_corrected():
    """Single-character OCR error in a preposition ('Of' vs 'On') is corrected."""
    api_key = os.environ.get('GOOGLE_BOOKS_API_KEY')
    result = verify_with_google_books(
        title='Of Wings of Blood',
        creators=['Briar Boleyn'],
        api_key=api_key,
    )
    assert result['status'] in ('verified', 'corrected', 'title_only'), (
        f"Expected a match, got status={result['status']!r}")
    title_fix = result.get('corrections', {}).get('title')
    assert title_fix is not None, (
        "Expected a title correction but got none. "
        f"Full result: {result}")
    assert 'On Wings of Blood' in title_fix['to'], (
        f"Expected canonical title to contain 'On Wings of Blood', got {title_fix['to']!r}")


# ---------------------------------------------------------------------------
# Canonical lookup — no correction expected
# ---------------------------------------------------------------------------

def test_exact_title_and_author_verified():
    """A well-known title/author pair is verified without any corrections."""
    api_key = os.environ.get('GOOGLE_BOOKS_API_KEY')
    result = verify_with_google_books(
        title='Dune',
        creators=['Frank Herbert'],
        api_key=api_key,
    )
    assert result['status'] in ('verified', 'corrected'), (
        f"Expected verified/corrected, got {result['status']!r}")


# ---------------------------------------------------------------------------
# Author misspelling — should correct
# ---------------------------------------------------------------------------

def test_author_misspelling_corrected_live():
    """A fuzzy author misspelling is corrected against the live API."""
    api_key = os.environ.get('GOOGLE_BOOKS_API_KEY')
    result = verify_with_google_books(
        title="A Midsummer Night's Dream",
        creators=['William Shakesper'],
        api_key=api_key,
    )
    author_fix = result.get('corrections', {}).get('authors')
    assert result['status'] == 'corrected', (
        f"Expected corrected, got {result['status']!r}")
    assert author_fix is not None
    assert 'Shakespeare' in author_fix['to']
