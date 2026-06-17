'''
Modul aggregating workers code
'''
import time

from typing import Optional, Any
from contextlib import closing
from threading import Thread, Event
from collections import namedtuple

try:
    from queue import Queue
except ImportError:
    from Queue import Queue

from lxml.html import fromstring

# pylint: disable=import-error
from calibre.utils.browser import Browser
from calibre.utils.logging import ThreadSafeLog
from calibre.ebooks.metadata.sources.base import Source
from calibre_plugins.wolnelektury_source.consts import ID_REGEX
# pylint: enable=import-error

MAX_RESULTS = 6
TITLE_THRESHOLD = 0.3

WorkerInput = namedtuple('WorkerInput',
    ['data', 'log', 'timeout', 'plugin', 'result_queue']
    )

class BaseWorker(Thread):
    '''
    Worker template class
    '''
    def __init__(self, worker_input: WorkerInput):
        super().__init__()
        self.daemon = True
        self.basic_data: dict = worker_input.data
        self.browser: Browser = worker_input.plugin.browser.clone_browser()
        self.log: ThreadSafeLog = worker_input.log
        self.timeout: int = worker_input.timeout
        self.result_queue: Queue = worker_input.result_queue
        self.plugin: Source = worker_input.plugin

    def run(self):
        try:
            if (result := self._get_data()) is not None:
                self.result_queue.put(result)

        # probably should be more preceise, but for threads it's enough
        # pylint: disable=broad-exception-caught
        except Exception:
            self.log.exception('Worker could not finish. Exception')
        # pylint: enable=broad-exception-caught

    def _get_data(self) -> Optional[Any]:
        '''
        should return Optional[result_type]
        '''
        raise NotImplementedError('Redefine __get_data() method in child class')

    @classmethod
    def run_workers(cls, workers_input: list[WorkerInput], abort: Event):
        '''
        allows running workers with given input
        '''
        workers = []
        for worker_input in workers_input:
            w = cls(worker_input)
            workers.append(w)

        if abort.is_set():
            return

        for w in workers:
            w.start()
            time.sleep(0.1)

        while not abort.is_set():
            is_alive = False
            for w in workers:
                w.join(0.2)
                if abort.is_set():
                    break
                if w.is_alive():
                    is_alive = True
            if not is_alive:
                break

class AuthorWorker(BaseWorker):
    '''
    Specialised worked for exctracting author's books for given id
    WorkerInput.data have to include authors's page url from wolnelektury.pl and book's title
    '''
    def _get_data(self) -> Optional[list[str]]:
        result = []
        url: str = self.basic_data['url']
        with closing(self.browser.open(url, timeout=self.timeout)) as page:
            result.extend(self._extract_authors_books(page))

        return None if len(result) == 0 else result

    def _extract_authors_books(self, page: bytes) -> list[str]:
        result = []
        read_data = page.read().decode(encoding='utf-8')
        parsed_data = fromstring(read_data)
        title_tokens = set( self.plugin.get_title_tokens(self.basic_data['title']) )
        not_check_tokens = len(title_tokens) != 0

        xpath: str = './/article[@class=\'l-books__item book-container-activator\']'
        no_to_find = MAX_RESULTS
        for book in parsed_data.findall(xpath):
            if no_to_find == 0:
                break
            book_url: str = book[0][0].get('href')
            #book_url: str = book.find('figure/a').get('href')
            # 10 times slower
            found = ID_REGEX.match(book_url)
            if found is None:
                continue


            book_title: Optional[str] = book[0][0][0].get('alt')
            #book_title: Optional[str] = book.find('figure/a/img').get('alt')
            if book_title is None:
                continue
            title_tokens = set(self.plugin.get_title_tokens(book_title))
            if not_check_tokens:
                no_to_find -= 1
                result.append(found[1])

            word_count = 0
            for word in title_tokens:
                if word not in title_tokens:
                    continue
                word_count += 1

            if word_count / len(title_tokens) >= TITLE_THRESHOLD:
                result.append(found[1])
                no_to_find -= 1

        return result
