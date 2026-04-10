"""
Unit tests for helpers.py — runs without Calibre or Qt installed.
Run from the repo root:  python -m pytest tests/
"""
import pytest
from helpers import (
    is_null_value,
    strip_null_values,
    clean_title,
    clean_author_name,
    verify_with_google_books,
    build_approved_data,
    ALL_FIELD_KEYS,
)


# ---------------------------------------------------------------------------
# is_null_value
# ---------------------------------------------------------------------------

class TestIsNullValue:
    def test_none(self):
        assert is_null_value(None)

    def test_string_null(self):
        assert is_null_value('null')

    def test_string_None(self):
        assert is_null_value('None')

    def test_empty_string(self):
        assert is_null_value('')

    def test_empty_list(self):
        assert is_null_value([])

    def test_nonempty_list(self):
        assert not is_null_value(['eng'])

    def test_real_string(self):
        assert not is_null_value('Harry Potter')

    def test_integer(self):
        assert not is_null_value(0)

    def test_zero_string(self):
        assert not is_null_value('0')


# ---------------------------------------------------------------------------
# strip_null_values
# ---------------------------------------------------------------------------

class TestStripNullValues:
    def test_removes_none_values(self):
        result = strip_null_values({'title': 'Dune', 'series': None})
        assert 'series' not in result
        assert result['title'] == 'Dune'

    def test_removes_string_null(self):
        result = strip_null_values({'publisher': 'null', 'title': 'Dune'})
        assert 'publisher' not in result

    def test_removes_empty_list(self):
        result = strip_null_values({'tags': [], 'languages': ['eng']})
        assert 'tags' not in result
        assert result['languages'] == ['eng']

    def test_preserves_nonempty_values(self):
        meta = {'title': 'Dune', 'pub_year': 1965, 'tags': ['sci-fi']}
        assert strip_null_values(meta) == meta

    def test_empty_input(self):
        assert strip_null_values({}) == {}


# ---------------------------------------------------------------------------
# clean_title
# ---------------------------------------------------------------------------

class TestCleanTitle:
    def test_all_caps_corrected(self):
        assert clean_title('THE GREAT GATSBY') == 'The Great Gatsby'

    def test_all_lowercase_corrected(self):
        assert clean_title('the great gatsby') == 'The Great Gatsby'

    def test_mixed_case_untouched(self):
        assert clean_title('The Great Gatsby') == 'The Great Gatsby'

    def test_already_correct_mixed_untouched(self):
        assert clean_title('Of Wings and Blood') == 'Of Wings and Blood'

    def test_article_lowercase_in_middle(self):
        assert clean_title('lord of the rings') == 'Lord of the Rings'

    def test_article_capitalised_at_start(self):
        assert clean_title('the hobbit') == 'The Hobbit'

    def test_article_capitalised_at_end(self):
        # Last word always capitalised even if it's an article
        assert clean_title('BRING IT ON') == 'Bring It On'

    def test_empty_string(self):
        assert clean_title('') == ''

    def test_non_string_passthrough(self):
        assert clean_title(None) is None

    def test_single_word_all_caps(self):
        assert clean_title('DUNE') == 'Dune'

    def test_conjunction_lowercase_in_middle(self):
        assert clean_title('PRIDE AND PREJUDICE') == 'Pride and Prejudice'

    def test_numbers_not_affected(self):
        assert clean_title('catch 22') == 'Catch 22'


# ---------------------------------------------------------------------------
# clean_author_name
# ---------------------------------------------------------------------------

class TestCleanAuthorName:
    # --- Basic passthrough ---
    def test_normal_name_unchanged(self):
        assert clean_author_name('Jane Austen') == 'Jane Austen'

    def test_empty_string_returns_none(self):
        assert clean_author_name('') is None

    def test_non_string_returns_none(self):
        assert clean_author_name(None) is None

    # --- Comma reversal ---
    def test_last_first_reversed(self):
        assert clean_author_name('Austen, Jane') == 'Jane Austen'

    def test_last_first_with_initials(self):
        assert clean_author_name('Rowling, J.K.') == 'J.K. Rowling'

    # --- Trailing initial rejection ---
    def test_trailing_initial_rejected(self):
        assert clean_author_name('John S.') is None

    def test_trailing_bare_initial_rejected(self):
        assert clean_author_name('John S') is None

    def test_trailing_initial_after_comma_rejected(self):
        # "Banks, Ian M." reverses to "Ian M. Banks" — trailing token is "Banks", fine
        assert clean_author_name('Banks, Ian M.') == 'Ian M. Banks'

    # --- Initial formatting ---
    def test_single_letter_gets_period(self):
        assert clean_author_name('J Rowling') == 'J. Rowling'

    def test_two_caps_become_dotted(self):
        assert clean_author_name('JK Rowling') == 'J.K. Rowling'

    def test_already_dotted_renormalized(self):
        assert clean_author_name('J.K. Rowling') == 'J.K. Rowling'

    def test_three_initials_dotted(self):
        assert clean_author_name('J.R.R. Tolkien') == 'J.R.R. Tolkien'

    def test_leading_initial_accepted(self):
        assert clean_author_name('F Scott Fitzgerald') == 'F. Scott Fitzgerald'

    def test_middle_initial_accepted(self):
        assert clean_author_name('Ian M. Banks') == 'Ian M. Banks'

    # --- All-caps normalisation ---
    def test_all_caps_name_title_cased(self):
        assert clean_author_name('GEORGE ORWELL') == 'George Orwell'

    def test_all_caps_with_initial(self):
        assert clean_author_name('J AUSTEN') == 'J. Austen'

    # --- Mixed case left alone ---
    def test_mixed_case_unchanged(self):
        assert clean_author_name('Neil Gaiman') == 'Neil Gaiman'

    def test_lowercase_last_name_unchanged(self):
        # e.g. "bell hooks" — deliberate lowercase, we don't touch mixed-case tokens
        assert clean_author_name('bell hooks') == 'bell hooks'


# ---------------------------------------------------------------------------
# verify_with_google_books  (all tests use injected _fetch_fn — no network)
# ---------------------------------------------------------------------------

def _make_fetch(title, authors):
    """Return a fetch function that simulates a Google Books hit."""
    response = {'items': [{'volumeInfo': {'title': title, 'authors': authors}}]}
    def _fetch(url):
        return response
    return _fetch

def _no_results_fetch(url):
    return {'items': []}

def _error_fetch(url):
    raise ConnectionError('network down')


class TestVerifyWithGoogleBooks:

    # --- Exact match ---
    def test_exact_match_verified(self):
        fetch = _make_fetch('Dune', ['Frank Herbert'])
        result = verify_with_google_books('Dune', ['Frank Herbert'], _fetch_fn=fetch)
        assert result['status'] == 'verified'
        assert result['corrections'] == {}

    # --- Author misspelling corrected ---
    def test_author_misspelling_corrected(self):
        fetch = _make_fetch('A Midsummer Night\'s Dream', ['William Shakespeare'])
        result = verify_with_google_books(
            "A Midsummer Night's Dream", ['William Shakesper'], _fetch_fn=fetch)
        assert result['status'] == 'corrected'
        assert result['corrections']['authors']['from'] == 'William Shakesper'
        assert result['corrections']['authors']['to'] == 'William Shakespeare'

    # --- Fuzzy title correction (OCR single-char error) ---
    def test_fuzzy_title_corrected(self):
        fetch = _make_fetch('On Wings of Blood', ['Briar Boleyn'])
        result = verify_with_google_books(
            'Of Wings of Blood', ['Briar Boleyn'], _fetch_fn=fetch)
        assert result['status'] == 'corrected'
        assert result['corrections']['title']['from'] == 'Of Wings of Blood'
        assert result['corrections']['title']['to'] == 'On Wings of Blood'

    # --- Missing author supplied from Books ---
    def test_missing_author_supplied(self):
        fetch = _make_fetch('On Wings of Blood', ['Briar Boleyn'])
        result = verify_with_google_books('On Wings of Blood', None, _fetch_fn=fetch)
        assert result['status'] == 'corrected'
        assert result['corrections']['authors']['from'] is None
        assert result['corrections']['authors']['to'] == 'Briar Boleyn'

    # --- Truncated author (trailing initial was rejected upstream) ---
    def test_truncated_author_corrected_via_title_only_pass(self):
        call_count = {'n': 0}
        def fetch(url):
            call_count['n'] += 1
            # Pass 1 (title+author) returns nothing; pass 2 (title only) returns hit
            if call_count['n'] == 1:
                return {'items': []}
            return {'items': [{'volumeInfo': {
                'title': 'The Hydrogen Sonata', 'authors': ['Iain M. Banks']
            }}]}
        result = verify_with_google_books(
            'The Hydrogen Sonata', None, _fetch_fn=fetch)
        assert result['status'] == 'corrected'
        assert result['corrections']['authors']['to'] == 'Iain M. Banks'

    # --- OCR preposition error: Google's own fuzzy search returns the right book ---
    def test_ocr_preposition_error_corrected_pass1(self):
        """Google returns 'On Wings of Blood' on the first (title+author) query.
        The fuzzy ratio between 'of wings of blood' and 'on wings of blood' is ~0.94,
        which clears the 0.85 threshold, so the title correction is recorded."""
        call_count = {'n': 0}
        def fetch(url):
            call_count['n'] += 1
            return {'items': [{'volumeInfo': {
                'title': 'On Wings of Blood', 'authors': ['Briar Boleyn']
            }}]}
        result = verify_with_google_books(
            'Of Wings of Blood', ['Briar Boleyn'], _fetch_fn=fetch)
        assert result['status'] == 'corrected'
        assert result['corrections']['title']['from'] == 'Of Wings of Blood'
        assert result['corrections']['title']['to'] == 'On Wings of Blood'
        assert call_count['n'] == 1  # single pass — Google's ranking does the work

    def test_ocr_preposition_error_corrected_pass2(self):
        """Pass 1 (title+author) returns empty; pass 2 (title only) finds the correct book.
        The fuzzy title match still clears 0.85 and the correction is recorded."""
        call_count = {'n': 0}
        def fetch(url):
            call_count['n'] += 1
            if call_count['n'] == 1:
                return {'items': []}
            return {'items': [{'volumeInfo': {
                'title': 'On Wings of Blood', 'authors': ['Briar Boleyn']
            }}]}
        result = verify_with_google_books(
            'Of Wings of Blood', ['Briar Boleyn'], _fetch_fn=fetch)
        assert result['status'] == 'corrected'
        assert result['corrections']['title']['from'] == 'Of Wings of Blood'
        assert result['corrections']['title']['to'] == 'On Wings of Blood'
        assert call_count['n'] == 2  # pass 1 empty → pass 2 finds it

    # --- Title mismatch → unverified ---
    def test_title_mismatch_unverified(self):
        fetch = _make_fetch('Something Completely Different', ['Author Name'])
        result = verify_with_google_books('Dune', ['Frank Herbert'], _fetch_fn=fetch)
        assert result['status'] == 'unverified'

    # --- No results → unverified ---
    def test_no_results_unverified(self):
        result = verify_with_google_books('Dune', ['Frank Herbert'], _fetch_fn=_no_results_fetch)
        assert result['status'] == 'unverified'

    # --- Network error → unverified (graceful) ---
    def test_network_error_graceful(self):
        result = verify_with_google_books('Dune', ['Frank Herbert'], _fetch_fn=_error_fetch)
        assert result['status'] == 'unverified'
        assert result['corrections'] == {}

    # --- Author tokens don't match → title_only ---
    def test_author_mismatch_title_only(self):
        fetch = _make_fetch('Dune', ['Someone Else Entirely'])
        result = verify_with_google_books('Dune', ['Frank Herbert'], _fetch_fn=fetch)
        assert result['status'] == 'title_only'

    # --- Books has no authors → verified on title alone ---
    def test_no_authors_in_books_response(self):
        fetch = _make_fetch('Dune', [])
        result = verify_with_google_books('Dune', ['Frank Herbert'], _fetch_fn=fetch)
        assert result['status'] == 'verified'


# ---------------------------------------------------------------------------
# build_approved_data
# ---------------------------------------------------------------------------

ALL = ALL_FIELD_KEYS

class TestBuildApprovedData:

    def _full_meta(self):
        return {
            'title':       'Dune',
            'creators':    ['Frank Herbert'],
            'series':      'Dune Chronicles',
            'series_index': '1',
            'tags':        ['sci-fi', 'epic'],
            'languages':   ['eng'],
            'publisher':   'Chilton Books',
            'pub_year':    1965,
            'pub_month':   8,
            'pub_day':     1,
            'ids':         'isbn:9780441013593',
            'comments':    'A masterwork of science fiction.',
        }

    def test_all_fields_present(self):
        result = build_approved_data(self._full_meta(), ALL)
        assert result['title'] == 'Dune'
        assert result['authors'] == 'Frank Herbert'
        assert result['series'] == 'Dune Chronicles'
        assert result['series_index'] == '1'
        assert result['tags'] == 'sci-fi, epic'
        assert result['languages'] == 'eng'
        assert result['publisher'] == 'Chilton Books'
        assert result['pubdate'] == '1965-08-01'
        assert result['identifiers'] == 'isbn:9780441013593'
        assert result['comments'] == 'A masterwork of science fiction.'

    def test_disabled_fields_excluded(self):
        result = build_approved_data(self._full_meta(), ['title', 'authors'])
        assert 'title' in result
        assert 'authors' in result
        assert 'series' not in result
        assert 'tags' not in result
        assert 'pubdate' not in result

    def test_null_title_excluded(self):
        meta = self._full_meta()
        meta['title'] = None
        result = build_approved_data(meta, ALL)
        assert 'title' not in result

    def test_null_string_title_excluded(self):
        meta = self._full_meta()
        meta['title'] = 'null'
        result = build_approved_data(meta, ALL)
        assert 'title' not in result

    def test_pubdate_year_only(self):
        meta = self._full_meta()
        del meta['pub_month']
        del meta['pub_day']
        result = build_approved_data(meta, ALL)
        assert result['pubdate'] == '1965-01-01'

    def test_pubdate_missing_year_excluded(self):
        meta = self._full_meta()
        del meta['pub_year']
        result = build_approved_data(meta, ALL)
        assert 'pubdate' not in result

    def test_tags_as_list_joined(self):
        result = build_approved_data(self._full_meta(), ['tags'])
        assert result['tags'] == 'sci-fi, epic'

    def test_languages_as_list_joined(self):
        meta = {**self._full_meta(), 'languages': ['eng', 'fra']}
        result = build_approved_data(meta, ['languages'])
        assert result['languages'] == 'eng, fra'

    def test_fallback_to_editor_key(self):
        meta = {'editor': 'Some Editor'}
        result = build_approved_data(meta, ['authors'])
        assert result['authors'] == 'Some Editor'

    def test_empty_creators_excluded(self):
        meta = {'creators': []}
        result = build_approved_data(meta, ['authors'])
        assert 'authors' not in result

    def test_empty_metadata_returns_empty(self):
        result = build_approved_data({}, ALL)
        assert result == {}
