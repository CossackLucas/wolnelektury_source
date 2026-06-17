'''
Custom functions used by plugin
'''
# pylint: disable=c-extension-no-member
import json

from typing import Optional, Callable
from contextlib import contextmanager
from datetime import datetime
from enum import Enum
from threading import Event

try:
    from urllib.parse import quote_plus
except ImportError:
    from urlib import quote_plus

try:
    from queue import Queue
except ImportError:
    from Queue import Queue

# lxml.etree does not have exposed c-module
from lxml import etree
from lxml.html import fromstring, tostring, Element

# pylint: disable=import-error
from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata.sources.base import Source
from calibre.utils.browser import Browser
from calibre.utils.logging import ThreadSafeLog

from calibre_plugins.wolnelektury_source.config import config
from calibre_plugins.wolnelektury_source.consts import WOLNELEKTURY_ID, COVER_NAMES, \
    AUTHOR_ID_REGEX, ID_REGEX
from calibre_plugins.wolnelektury_source.worker import WorkerInput, AuthorWorker, BaseWorker

from mechanize._response import response_seek_wrapper as Response
# pylint: enable=import-error

MAX_RESULTS = 3

# ToDo: should be looked into
@contextmanager
def access_data(thing: Callable, log=None):
    '''
    context manager trying to service all possible issues when parsing data
    '''
    try:
        yield thing
    except json.JSONDecodeError as e:
        if log is not None:
            log.exception(f'Error decoding data:\n{e}')
    except UnicodeDecodeError as e:
        if log is not None:
            log.exception(f'Error decoding data:\n{e}')
    except etree.LxmlError as e:
        if log is not None:
            log.exception(f'Error parsing using lxml:\n{e}')
    finally:
        thing.close()

# was StrEnum, but it changed req. Python to 3.11
class SearchCategory(Enum):
    '''
    Enum describing search category for WolneLektury.pl queries
    '''
    BOOK = 'book'
    AUTHOR = 'author'

def __build_search_query(query_tokens: list[str], category: SearchCategory) -> str:
    return 'https://wolnelektury.pl/szukaj/?q=' + quote_plus(' '.join(query_tokens)) \
        + '=&category=' + category.value

def check_site_for_books(worker_input: WorkerInput, abort: Event):
    '''
    perform search on wolnelektury site, and returns ids

    proposed algorithm: check by title, the those results by author
    then author and look for a book

    worker_data.data have to include title and authors list
    '''
    log: ThreadSafeLog = worker_input.log
    plugin: Source = worker_input.plugin
    title: Optional[str] = worker_input.data['title']
    authors: Optional[list[str]] = worker_input.data['authors']
    timeout: int = worker_input.timeout
    browser: Browser = plugin.browser
    rq: Queue = worker_input.result_queue

    if abort.is_set():
        return

    title_tokens: list[str] = list(plugin.get_title_tokens(title))
    title_query: str = __build_search_query(title_tokens, SearchCategory.BOOK)
    log.info(f'Checking query: {title_query}')

    found_books: list[str] = []
    with access_data(browser.open(title_query, timeout=timeout), log) as page:
        if abort.is_set():
            return
        parsed_data = fromstring(page.read().decode(encoding='utf-8'))
        found_books = __extract_books(parsed_data)
        log.info(f'{len(found_books)} book(s) were found')
        if authors is not None:
            checked_books = set()
            for author in authors:
                checked_books = checked_books | \
                    (__check_found_books(found_books, author, timeout, plugin))
            found_books = list(set(found_books) & checked_books)
        log.info(f'{len(found_books)} book(s) were left after filtering through authors')


    if len(found_books) != 0:
        rq.put(found_books)
        return

    author_query: str = __build_search_query(
        plugin.get_author_tokens(authors),
        SearchCategory.AUTHOR
    )
    log.info(f'Checking query for authors: {author_query}')

    found_authors = []
    with access_data(browser.open(author_query, timeout=timeout), log) as page:
        found_authors = __extract_authors(page)
        if abort.is_set():
            return
    log.info(f'{len(found_authors)} authors found')
    log.info(found_authors)

    workers_input = []
    for author_id in found_authors:
        temp = WorkerInput(
            { 'url': __get_authors_url(author_id), 'title': title },
            log, timeout, plugin, rq
        )
        workers_input.append(temp)

    AuthorWorker.run_workers(workers_input, abort)

def __extract_books(parsed_data: Element) -> list[str]:
    result = []
    xpath:str = './/article[@class=\'l-books__item book-container-activator\']'
    found = MAX_RESULTS
    for element in parsed_data.findall(xpath):
        if found == 0:
            break
        book_url: str = element[0][0].get('href')
        if book_match := ID_REGEX.match(book_url):
            result.append(book_match[1])
            found -= 1

    return result

def __check_found_books(found_books: list[str], author: str, timeout: int,
    plugin: Source) -> set[str]:
    def is_among_tokens(author, tokens):
        for token in author:
            if token in tokens:
                return True
        return False

    browser: Browser = plugin.browser
    result: set[str] = set()
    author_tokens = set(plugin.get_author_tokens([author]))
    # ToDo: does it need its own workers?
    for book in found_books:
        with access_data(browser.open(get_xml_url(book), timeout=timeout)) as page:
            parsed_data = etree.fromstring(page.read().decode(encoding='utf-8'))
            authors = __get_authors_from_parsed_xml(parsed_data)
            if authors is not None and is_among_tokens(
                author_tokens, set(plugin.get_author_tokens(authors))
            ):
                result.add(book)

    return result

def __extract_authors(page: Response) -> list[str]:
    result = []
    read_data = page.read().decode(encoding='utf-8')
    parsed_data = fromstring(read_data)

    xpath: str = './/ul[@class=\'c-search-result c-search-result-author\']'
    author_data = parsed_data.find(xpath)
    if author_data is None:
        return []
    for author in author_data:
        url = author[0].get('href')
        if (found := AUTHOR_ID_REGEX.match(url)) is not None:
            result.append(found[1])

    return result

# pylint does not see worker.py
# pylint: disable=too-few-public-methods
class MetadataWorker(BaseWorker):
    '''
    Specialised worked for exctracting metadata for given id
    WorkerInput.data have to include book's id from wolnelektury.pl and source relevance
    '''
    def _get_data(self) -> Optional[Metadata]:
        return self.get_metadata()

    def get_metadata(self) -> Optional[Metadata]:
        '''
        gets metadata from wolnelektury for given book by it's id
        '''
        wolnelektury_id: str = self.basic_data[WOLNELEKTURY_ID]
        wolnelektury_url: str = get_xml_url(wolnelektury_id)
        me: Optional[Metadata] = None
        self.log.info(f'Trying to reach book page {wolnelektury_url}')
        with access_data(self.browser.open(wolnelektury_url, timeout=self.timeout)) as page:
            self.log.info(f'Page \'{wolnelektury_url}\' accessed and parsed')
            read_data = page.read().decode(encoding='utf-8')
            parsed_data = etree.fromstring(read_data)
            me = extract_metadata_xml(parsed_data)
            me.set_identifier(WOLNELEKTURY_ID, wolnelektury_id)
            me.source_relevance = self.basic_data['relevance']

            cover_urls = self.__get_cover_urls(wolnelektury_id)
            if len(cover_urls) != 0:
                me.has_cover = True
                self.plugin.cache_identifier_to_cover_url(wolnelektury_id, cover_urls)
        self.plugin.clean_downloaded_metadata(me)

        return me

    # ToDo: should get_best_cover come back?
    def __get_cover_urls(self, wolnelektury_id: str) -> list[str]:
        '''
        get cover's urls from wolnelektury.pl. If none are found, result is empty
        '''
        self.log.info(f"Getting cover urls for {wolnelektury_id}")
        result: list[str] = []

        user_cover_names: list[str] = [ config.get_pref('prefered_cover') ]
        user_cover_names.extend(set(COVER_NAMES.keys()) - set(user_cover_names))

        max_covers = config.get_pref('max_covers')

        with access_data(self.browser.open(get_api_url(wolnelektury_id), timeout=self.timeout)) as page:
            self.log.info("Parsing data for covers")
            parsed_data: dict = json.load(page)
            for i, cover_name in enumerate(user_cover_names):
                if max_covers == i:
                    self.log.info(
                        f'Stopping search for covers early at {i}th search, found {len(result)} url(s)'
                        )
                    break
                url = parsed_data.get(cover_name)
                if url is not None:
                    result.append(url)

        self.log.info(f'Search finished with {len(result)} urls found')

        return result
# pylint: enable=too-few-public-methods

def get_api_url(wolnelektury_id: str) -> str:
    ''' 
    Generate api url from wolnelektury id (nothing is checked)
    '''
    return f'https://wolnelektury.pl/api/books/{wolnelektury_id}/?format=json'

def get_xml_url(wolnelektury_id: str) -> str:
    ''' 
    Generate url for data xml file from wolnelektury id (nothing is checked)
    '''
    return f'https://wolnelektury.pl/media/book/xml/{wolnelektury_id}.xml'

def __get_authors_url(wolnelektury_id: str) -> str:
    ''' 
    Generate url for author's page on wolnelektury id (nothing is checked)
    '''
    return f'https://wolnelektury.pl/katalog/autor/{wolnelektury_id}/'

def extract_metadata_xml(parsed_data: etree.Element) -> Metadata:
    '''
    Extracts metadata from lxml etree
    Assumes data is from wolnelektury.pl
    '''
    me = Metadata('', '')

    if (book_title := __get_data_from_xml(parsed_data, 'title')) is not None:
        me.title = book_title

    book_authors = __get_authors_from_parsed_xml(parsed_data)
    me.authors = book_authors if len(book_authors) != 0 else [('Unknown')]

    if (book_lang := __get_data_from_xml(parsed_data, 'language')) is not None:
        me.language = book_lang

    if config.get_pref('pubdate') and \
        (book_date := __get_date_from_parsed_xml(parsed_data,'date')):
        me.pubdate = book_date

    if config.get_pref('comments') and (book_abstract := __get_abstract(parsed_data)):
        me.comments = book_abstract

    if (book_isbn := __get_isbn_from_parsed_xml(parsed_data)) is not None:
        me.isbn = book_isbn

    if config.get_pref('publisher'):
        me.publisher = 'Fundacja Nowoczesna Polska'

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
    book_isbn = __get_data_from_xml(parsed_data, 'meta[@id=\'epub-id\']')

    return book_isbn

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
        # Trying to avoid fragments
        if paragraph.tag != 'akap':
            continue
        if config.get_pref('html_comments'):
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

    tmp_str = replace_element(tmp_str, 'tytul_dziela', 'em')

    return tmp_str
