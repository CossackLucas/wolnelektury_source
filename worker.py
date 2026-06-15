'''
Modul aggregating workers code
'''
import json

from threading import Thread
from typing import Optional
from contextlib import closing
from collections import namedtuple

# pylint: disable=c-extension-no-member
# lxml.etree does not have exposed c-module
from lxml import etree

# pylint: disable=import-error
from calibre.ebooks.metadata.book.base import Metadata

from calibre_plugins.wolnelektury_source.main import extract_metadata_xml
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
        self.browser = worker_input.browser
        self.log = worker_input.log
        self.timeout = worker_input.timeout
        self.result_queue = worker_input.result_queue
        self.plugin = worker_input.plugin

    def run(self):
        try:
            if (result := self._get_data()):
                self.result_queue.put(result)
        except Exception as e:
            self.log.exception('Worker could not finish. Exception:')
            self.log.exception(e)

    def _get_data(self):
        '''
        should return Optional[result_type]
        '''
        raise NotImplementedError('Redefine __get_data() method in child class')

class MetadataWorker(BaseWorker):
    '''
    Specialised worked for exctracting metadata for given id
    '''
    def _get_data(self):
        return self.get_metadata()

    def get_metadata(self) -> Optional[Metadata]:
        '''
        gets metadata from wolnelektury for given book by it's id
        '''
        wolnelektury_id = self.basic_data[WOLNELEKTURY_ID]
        wolnelektury_url: str = _get_xml_url(wolnelektury_id)
        me = None
        with closing(self.browser.open(wolnelektury_url, timeout=self.timeout)) as page:
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
                self.log.info(f'Cover urls {cover_urls} added to cache under {wolnelektury_id}')

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

        with closing(self.browser.open(_get_api_url(wolnelektury_id), timeout=self.timeout)) as page:
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

def _get_api_url(wolnelektury_id: str) -> str:
    ''' 
    Generate api url from wolnelektury id (nothing is checked)
    '''
    return f'https://wolnelektury.pl/api/books/{wolnelektury_id}/?format=json'

def _get_xml_url(wolnelektury_id: str) -> str:
    ''' 
    Generate url for data xml file from wolnelektury id (nothing is checked)
    '''
    return f'https://wolnelektury.pl/media/book/xml/{wolnelektury_id}.xml'

class AuthorWorker(BaseWorker):
    # pylint: disable=unused-private-member
    def __get_data(self):
        pass
    # pylint: enable=unused-private-member
