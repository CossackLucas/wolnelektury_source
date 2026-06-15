'''
Modul aggregating workers code
'''
import json

from threading import Thread
from typing import Optional
from datetime import datetime
from contextlib import closing
from collections import namedtuple

# pylint: disable=c-extension-no-member
# lxml.etree does not have exposed c-module
from lxml import etree
from lxml.html import fromstring, tostring, Element

# pylint: disable=import-error
from calibre.ebooks.metadata.book.base import Metadata

from calibre_plugins.wolnelektury_source.config import config
from calibre_plugins.wolnelektury_source.consts import COVER_NAMES, WOLNELEKTURY_ID
# pylint: enable=import-error

def run_workers():
    pass

WorkerInput = namedtuple('WorkerInput',
    ['data', 'log', 'timeout', 'browser', 'plugin', 'result_queue']
    )

class BaseWorker(Thread):
    '''
    Worker template class
    '''
    def __init__(self, worker_input: WorkerInput):
        super().__init__()
        self.daemon = True
        self.basic_data: dict = worker_input.data
        self.browser, self.log, self.timeout = worker_input.browser, worker_input.log, worker_input.timeout
        self.result_queue = worker_input.result_queue
        self.plugin = worker_input.plugin

    def run(self):
        if (result := self.__get_data()):
            self.result_queue.put(result)

    def __get_data(self):
        '''
        should return Optional[result_type]
        '''
        raise NotImplementedError('Redefine __get_data() method in child class')

class MetadataWorker(BaseWorker):
    '''
    Specialised worked for exctracting metadata for given id
    '''
    # pylint: disable=unused-private-member
    def __get_data(self):
        return self.__get_metadata()
    # pylint: enable=unused-private-member

    def __get_metadata(self) -> Optional[Metadata]:
        '''
        gets metadata from wolnelektury for given book by it's id
        '''
        wolnelektury_id = self.basic_data[WOLNELEKTURY_ID]
        wolnelektury_url: str = __get_xml_url(wolnelektury_id)
        me = None
        with closing(self.browser.open(wolnelektury_url, timeout=self.timeout)) as page:
            self.log.info(f'Page \'{wolnelektury_url}\' accessed and parsed')
            read_data = page.read().decode(encoding='utf-8')
            parsed_data = etree.fromstring(read_data)
            me = __extract_metadata_xml(parsed_data)
            cover_urls = self.__get_cover_urls(wolnelektury_id)
            if len(cover_urls) != 0:
                me.has_cover = True
                self.plugin.cache_identifier_to_cover_url(wolnelektury_id, cover_urls)

        return me

    # ToDo: should get_best_cover come back?
    def __get_cover_urls(self, wolnelektury_id: str) -> list[str]:
        '''
        get cover's urls from wolnelektury.pl. If none are found, result is empty
        '''
        self.log.info(f"Getting cover urls for {wolnelektury_id}")
        result: list[str] = []

        user_cover_names = [ config.get_pref('prefered_cover') ]
        user_cover_names.extend(set(COVER_NAMES.keys()) - set(user_cover_names))
        self.log.info(f'Cover types order is: {user_cover_names}')

        max_covers = config.get_pref('max_covers')
        self.log.info(f'max_covers preference is {max_covers}')

        with closing(self.browser.open(__get_api_url(wolnelektury_id), timeout=self.timeout)) as page:
            self.log.info("Parsing data for covers")
            parsed_data = json.load(page)
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
    

class AuthorWorker(BaseWorker):
    # pylint: disable=unused-private-member
    def __get_data(self):
        pass
    # pylint: enable=unused-private-member
