'''
Modul aggregating workers code
'''
import time

from typing import Optional, Any
from threading import Thread, Event
from collections import namedtuple

try:
    from queue import Queue
except ImportError:
    from Queue import Queue

# pylint: disable=import-error
from calibre.utils.browser import Browser
from calibre.utils.logging import ThreadSafeLog
from calibre.ebooks.metadata.sources.base import Source
# pylint: enable=import-error

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
