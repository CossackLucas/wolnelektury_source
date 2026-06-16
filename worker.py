'''
Modul aggregating workers code
'''
import time

from threading import Thread
from collections import namedtuple

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
        self.browser = worker_input.plugin.browser.clone_browser()
        self.log = worker_input.log
        self.timeout = worker_input.timeout
        self.result_queue = worker_input.result_queue
        self.plugin = worker_input.plugin

    def run(self):
        try:
            if (result := self._get_data()):
                self.result_queue.put(result)
        # ToDo: probably should be more preceise
        except Exception as e:
            self.log.exception('Worker could not finish. Exception:')

    def _get_data(self):
        '''
        should return Optional[result_type]
        '''
        raise NotImplementedError('Redefine __get_data() method in child class')

    @classmethod
    def run_workers(cls, workers_input: list[WorkerInput], abort):
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
    def _get_data(self):
        pass
