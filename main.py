'''
Custom functions used by plugin
'''
# pylint: disable=c-extension-no-member
import json
import re

from typing import Optional
from contextlib import contextmanager
from collections import namedtuple
from datetime import datetime

try:
    from urllib.error import HTTPError, URLError
except ImportError:
    from urllib import HTTPError, URLError
try:
    from urllib.parse import quote_plus
except ImportError:
    from urlib import quote_plus

from socket import gaierror

# lxml.etree does not have exposed c-module
from lxml import etree
from lxml.html import fromstring, tostring, Element

# pylint: disable=import-error
from calibre.ebooks.metadata.book.base import Metadata

from calibre_plugins.wolnelektury_source.config import prefs
# pylint: enable=import-error

WOLNELEKTURY_ID = 'wolnelektury_id'
MAX_RESULTS = 3

@contextmanager
def access_data(thing, log=None):
    '''
    context manager trying to service all possible issues when getting data via Internet
    '''
    try:
        yield thing
    #ToDo: URLError and gaierror do not work for browser, crash still happens when there's not connection
    except (HTTPError, URLError, gaierror) as e:
        if log is not None:
            log.exception(f'Network error:\n{e}')
    except AttributeError as e:
        if log is not None:
            log.exception(f'{e}')
    except json.JSONDecodeError:
        if log is not None:
            log.exception(f'Error decoding data:\n{e}')
    except UnicodeDecodeError:
        if log is not None:
            log.exception(f'Error decoding data:\n{e}')
    except etree.LxmlError as e:
        if log is not None:
            log.exception(f'Error parsing using lxml:\n{e}')
    finally:
        thing.close()

BaseArgs = namedtuple('BaseArgs', ['abort', 'browser', 'log', 'timeout'])

def get_metadata(base_args: BaseArgs, wolnelektury_id: str) -> Optional[Metadata]:
    '''
    gets metadata from wolnelektury for given book by it's id
    '''
    abort, browser, log, timeout = base_args

    if abort.is_set():
        return None

    wolnelektury_url: str = __get_xml_url(wolnelektury_id)
    me = None
    with access_data(browser.open(wolnelektury_url, timeout=timeout), log) as page:
        if abort.is_set():
            return None
        log.info(f'Page \'{wolnelektury_url}\' accessed and parsed')
        read_data = page.read().decode(encoding='utf-8')
        me = __extract_metadata_xml(etree.fromstring(read_data))

    return me

# 'cover' has to stay first to break for best cover to work properly
COVER_NAMES = ('cover', 'simple_cover')
def get_cover_urls(base_args: BaseArgs, wolnelektury_id: str, get_best_cover=False) -> list[str]:
    '''
    get cover's urls from wolnelektury.pl. If none are found, result is empty
    '''
    abort, browser, log, timeout = base_args

    log.info(f"Getting cover urls for {wolnelektury_id}")
    if abort.is_set():
        return ()
    result: list[str] = []

    source_url: str = __get_api_url(wolnelektury_id)
    prefered_cover = prefs.get_prefs('prefered_cover')
 
    user_cover_names = [ prefered_cover ]
    # ToDo: is there less hacky way to do it?
    user_cover_names.extend(set(COVER_NAMES) - set(user_cover_names))
    log.info(f'Cover types order is: {user_cover_names}')

    max_covers = prefs.get_prefs('max_covers')
    log.info(f'max_covers preference is {max_covers}')

    with access_data(browser.open(source_url, timeout=timeout), log) as page:
        log.info("Parsing data for covers")
        parsed_data = json.load(page)
        for i, name in enumerate(user_cover_names):
            if max_covers == i:
                log.info(f'Stopping search for covers early at {i}th search, found {len(result)} url(s)')
                break
            if abort.is_set():
                break
            url = parsed_data.get(name)
            if url is not None:
                result.append(url)
            if get_best_cover:
                log.info('Stopping search for covers early, as best covers was found')
                break

    return result

def check_site_for_books(
    base_args: BaseArgs,
    title_tokens: list[str],
    author_tokens: list[str]
    ) -> list[str]:
    '''
    perform search on wolnelektury site, and returns ids

    proposed algorithm: check by title, the those results by author
    then author and look for a book
    '''
    abort, browser, log, timeout = base_args

    if abort.is_set():
        return []
    # ToDo: should we used queries using =&category=book ?
    title_query: str = 'https://wolnelektury.pl/szukaj/?q=' + quote_plus(' '.join(title_tokens))
    log.info(f'Checking query: {title_query}')

    found_books: list[str] = []
    with access_data(browser.open(title_query, timeout=timeout), log) as page:
        if abort.is_set():
            return []
        parsed_data = fromstring(page.read().decode(encoding='utf-8'))
        found_books = __extract_books(parsed_data)
        log.info(f'{len(found_books)} book(s) were found') 
        # ToDo: finish check
        #found_books = __check_found_books(found_books, author_tokens)

    if len(found_books) != 0:
        return found_books

    return []

    # ToDo: expand search
    raise NotImplementedError('Looking for an author should be checked')
    author_query: str = 'https://wolnelektury.pl/szukaj/?q=' + quote_plus(' '.join(author_tokens))
    with access_data(browser(author_query, timeout=timeout), log) as page:
        found_authors = __extract_authors(page)
        if abort.is_set():
            return []

        found_books = __extract_authors_books(found_authors)

    return found_books

ID_REGEX = re.compile(r'/katalog/lektura/([a-z\-]+)/')

def __extract_books(parsed_data: Element) -> list[str]:
    result = []
    xpath:str = './/article[@class=\'l-books__item book-container-activator\']'
    found = MAX_RESULTS
    # ToDo: check iter_find instead of findall
    for element in parsed_data.findall(xpath):
        if found == 0:
            break
        book_url: str = element[0][0].get('href')
        if book_match := ID_REGEX.match(book_url):
            result.append(book_match[1])
            found -= 1

    return result

def __check_found_books(found_books: list[str], author_tokens: list[str]) -> list[str]:
    result: list[str] = []
    # ToDo: check, if authors are matching for given book
    for book in found_books:
        print(book)
    raise NotImplementedError(f'__check_found_books not implemented, {author_tokens}')
    return result

def __extract_authors(page) -> list[str]:
    result = []
    raise NotImplementedError(f'__extract_authors not implemented, {page}')
    # ToDo: search for  <ul class="c-search-result c-search-result-author">
    return result

def __extract_authors_books(authors_list: list[str]) -> list[str]:
    result = []
    # ToDo: check <article class="l-books__item book-container-activator" data-pop="-79" data-longpress="hover">
    for author in authors_list:
        print(author)
    raise NotImplementedError('__extract_authors_book not implemented')
    return result

def __get_api_url(wolnelektury_id: str) -> str:
    ''' 
    Generate api url from wolnelektury id (nothing is checked)
    '''
    return f'https://wolnelektury.pl/api/books/{wolnelektury_id}/?format=json'

def __get_xml_url(wolnelektury_id: str) -> str:
    ''' 
    Generate url for data xml file from wolnelektury id (nothing is checked)
    '''
    return f'https://wolnelektury.pl/media/book/xml/{wolnelektury_id}.xml'

def __extract_metadata_xml(parsed_data: etree.Element) -> Metadata:
    me = Metadata('', '')

    if (book_title := __get_data_from_xml(parsed_data, 'title')) is not None:
        me.title = book_title

    book_authors = __get_authors_from_parsed_xml(parsed_data)
    me.authors = book_authors if len(book_authors) != 0 else [('Unknown')]

    if (book_lang := __get_data_from_xml(parsed_data, 'language')) is not None:
        me.language = book_lang

    if prefs.get_prefs('pubdate') and (book_date := __get_date_from_parsed_xml(parsed_data,'date')):
        me.pubdate = book_date

    if prefs.get_prefs('comments') and (book_abstract := __get_abstract(parsed_data)):
        me.comments = book_abstract

    # isbn is needed for calibre not to merge the results
    # but the site publishes different isbns for different formats!
    # ToDo: solve this issue
    if (book_isbn := __get_isbn_from_parsed_xml(parsed_data)) is not None:
        me.isbn = book_isbn

    if prefs.get_prefs('publisher'):
        me.publisher = 'Fundacja Nowoczesna Polska'

    # ToDo: should be checked?
    me.has_cover = True

    return me

def __get_data_from_xml(parsed_data: etree.Element, element: str) -> Optional[str]:
    found_data = parsed_data.find('.//{*}' + element)
    return None if found_data is None else found_data.text

def __get_authors_from_parsed_xml(parsed_data: etree.Element) -> list[str]:
    found_data = parsed_data.findall('.//{*}creator')
    if len(found_data) == 0:
        return []

    result: list[str] = []
    for reversed_author in found_data:
        result.append(__standardize_author(reversed_author.text))

    return result

def __get_isbn_from_parsed_xml(parsed_data: etree.Element) -> Optional[str]:
    # ToDo: Should check other ISBNs for other formats?
    book_isbn = __get_data_from_xml(parsed_data, 'meta[@id=\'epub-id\']')
    if book_isbn is None:
        return book_isbn

    # removing prefix ISBN-
    book_isbn = book_isbn[5:]

    return book_isbn.replace('-', '')

def __get_date_from_parsed_xml(parsed_data: etree.Element, element: str) -> Optional[datetime]:
    found_date = ''
    if (found_date := __get_data_from_xml(parsed_data, element)) is None:
        return None
    date_list = found_date.split('-')
    return datetime(int(date_list[0]), int(date_list[1]), int(date_list[2]))

def __standardize_author(reversed_name: str) -> str:
    if ',' not in reversed_name:
        return reversed_name
    elements = reversed_name.split(',')
    return f"{elements[1].strip()} {elements[0]}"

def __get_abstract(parsed_data: etree.Element) -> Optional[str]:
    result: str = ''
    abstract = parsed_data.find('.//abstrakt')
    if abstract is None:
        return None

    for paragraph in abstract:
        if paragraph.tag != 'akap':
            continue
        if prefs.get_prefs('html_comments'):
            pseudo_html = tostring(paragraph, encoding="utf-8").decode(encoding="utf-8")
            result += __get_html_formatting(pseudo_html)
        else:
            result += ''.join(paragraph.itertext())
            result += '\n\n'

    return None if len(result) == 0 else result

def __get_html_formatting(data: str) -> str:
    def replace_element(data: str, old: str, new: str) -> str:
        tmp_str = data.replace(f'<{old}>', f'<{new}>')
        return tmp_str.replace(f'</{old}>', f'</{new}>')

    tmp_str = replace_element(data, 'akap', 'p')

    tmp_str = replace_element(tmp_str, 'tytul_dziela', 'i')

    return tmp_str
