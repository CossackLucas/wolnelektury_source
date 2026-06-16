'''
Metadata source plugin using wolnelektury.pl page as source
Main definition file
'''
import re

try:
    from queue import Queue
except ImportError:
    from Queue import Queue

try:
    from urllib.error import HTTPError
except ImportError:
    from urllib import HTTPError

# pylint: disable=import-error
from calibre.ebooks.metadata.sources.base import Source
from calibre.utils.localization import _
from calibre.constants import numeric_version
# ToDo: to be removed and replaced with local implementation
from calibre.ebooks.metadata.sources.base import InternalMetadataCompareKeyGen

from calibre_plugins.wolnelektury_source.main import check_site_for_books, \
    MetadataWorker, WorkerInput
from calibre_plugins.wolnelektury_source.config import config
from calibre_plugins.wolnelektury_source.consts import PLUGIN_VERSION, PLUGIN_NAME, WOLNELEKTURY_ID
# pylint: enable=import-error

# pylint: disable=undefined-variable
# required to run tests
try:
    load_translations()
except NameError:
    pass
# pylint: enable=undefined-variable

CALIBRE_VERSION = ".".join([str(x) for x in numeric_version])

class WolneLekturySource(Source):
    '''
    source plugin definition
    '''
    name = PLUGIN_NAME
    author = 'Łukasz Kozak'
    description = _('Download metadata and covers from site wolnelektury.pl')
    version = PLUGIN_VERSION
    # 0.3.0 checked with 6.12
    minimum_calibre_version = (6, 12, 0)
    capabilities = frozenset(['identify', 'cover'])
    touched_fields = frozenset([
        'title',
        'authors',
        'language',
        'publisher',
        'pubdate',
        'comments',
        f'identifier:{WOLNELEKTURY_ID}',
        'identifier:isbn'
    ])

    has_html_comments = True
    supports_gzip_transfer_encoding = False
    ignore_ssl_errors = False
    # ToDo: to be repaired 
    cached_cover_url_is_reliable = True
    config_help_message = '<p>'+_('Calibre')+': <b>'+CALIBRE_VERSION+'</b> • ' + \
        _('Plugin version')+': <b>'+'.'.join([str(x) for x in version])+'</b> • ' + \
        _('Please report bugs through the') + \
        ' <a href="https://www.mobileread.com/forums/showthread.php?t=373972">MobileRead</a>' + _(' forum or ')+\
        '<a href="https://github.com/CossackLucas/wolnelektury_source">GitHub</a>'+_('.') + '<br>' \
        + _('<b>Warning</b>: ISBN could be pointing to different file format edition of the book')
    can_get_multiple_covers = True
    prefer_results_with_isbn = False
    options = config.get_options()

    @property
    def prefs(self):
        '''
        redifined dictionary of preferences
        '''
        # self._config_obj exists in Source class definition
        # pylint: disable=access-member-before-definition,attribute-defined-outside-init
        if self._config_obj is None:
            self._config_obj = config.get_prefs()
        return self._config_obj
        # pylint: enable=access-member-before-definition,attribute-defined-outside-init

    def is_configured(self):
        '''
        probably won't change, defaults will be enough
        '''
        return True

    def is_customizable(self):
        '''
        Done
        '''
        return True

    # ToDo: my own custom widget
    #def config_widget(self):
        #return super().config_widget()

    def save_settings(self, config_widget):
        '''
        needed as 'max_covers' already used and if set to 0, calibre uses it and shows no covers
        '''
        def clear_max_covers(value: int) -> int:
            value = max(value, 1)
            value = min(value, 2)
            return value

        super().save_settings(config_widget)
        self.prefs['max_covers'] = clear_max_covers(self.prefs['max_covers'])

    # working methods
    def get_book_url(self, identifiers):
        '''
        Return a 3-tuple or None. The 3-tuple is of the form:
        (identifier_type, identifier_value, URL).
        The URL is the URL for the book identified by identifiers at this
        source. identifier_type, identifier_value specify the identifier
        corresponding to the URL.
        This URL must be browsable to by a human using a browser. It is meant
        to provide a clickable link for the user to easily visit the books page
        at this source.
        If no URL is found, return None. This method must be quick, and
        consistent, so only implement it if it is possible to construct the URL
        from a known scheme given identifiers.

        There are only to certain identifiers to draw from here:
        wolnelektury_id and potentialy url itself
        '''
        book_id = None
        book_url = None

        if book_id := identifiers.get(WOLNELEKTURY_ID):
            book_url = f'https://wolnelektury.pl/katalog/lektura/{book_id}/'
        elif book_url := identifiers.get('url'):
            book_id = self.id_from_url(book_url)

        if book_id is not None:
            return (WOLNELEKTURY_ID, book_id, book_url)
        return None

    def get_cached_cover_url(self, identifiers):
        '''
        Return cached cover URL for the book identified by
        the identifiers dictionary or None if no such URL exists.

        Note that this method must only return validated URLs, i.e. not URLS
        that could result in a generic cover image or a not found error.
        '''
        book_id = identifiers.get(WOLNELEKTURY_ID)
        if book_id is None:
            if (url := self.get_book_url(identifiers)) is not None:
                book_id = self.id_from_url(url)
        return self.cached_identifier_to_cover_url(book_id) if book_id is not None else None

    __WOLNELEKTURY_ID_REGEX = (
        re.compile(r'(https?:\/\/)(www.)?wolnelektury.pl\/katalog\/lektura\/([a-z\-]+)\/?'),
        re.compile(r'(https?:\/\/)(www.)?wolnelektury.pl\/media\/book\/cover\/([a-z\-]+).jpg\/?'),
        re.compile(r'(https?:\/\/)(www.)?wolnelektury.pl\/media\/book\/cover_simple\/([a-z\-]+)_[a-zA-Z0-9]+.jpg\/?')
    )

    def id_from_url(self, url):
        '''
        Parse a URL and return a tuple of the form:
        (identifier_type, identifier_value).
        If the URL does not match the pattern for the metadata source,
        return None.
        '''
        for regex in self.__WOLNELEKTURY_ID_REGEX:
            search_result = regex.search(url)
            if search_result is not None:
                return search_result.group(3)

        return None

    # pylint: disable=dangerous-default-value
    def identify_results_keygen(self, title=None, authors=None,
            identifiers={}):
        '''
        Return a function that is used to generate a key that can sort Metadata
        objects by their relevance given a search query (title, authors,
        identifiers).

        These keys are used to sort the results of a call to :meth:`identify`.

        For details on the default algorithm see
        :class:`InternalMetadataCompareKeyGen`. Re-implement this function in
        your plugin if the default algorithm is not suitable.
        '''
        # ToDo: prepare my version
        def keygen(mi):
            return InternalMetadataCompareKeyGen(mi, self, title, authors,
                identifiers)
        return keygen
    # pylint: enable=dangerous-default-value

    # pylint: disable=too-many-positional-arguments, too-many-arguments, dangerous-default-value
    def identify(self, log, result_queue, abort, title=None, authors=None,
            identifiers={}, timeout=30):
        '''
        Identify a book by its Title/Author/ISBN/etc.

        If identifiers(s) are specified and no match is found and this metadata
        source does not store all related identifiers (for example, all ISBNs
        of a book), this method should retry with just the title and author
        (assuming they were specified).

        If this metadata source also provides covers, the URL to the cover
        should be cached so that a subsequent call to the get covers API with
        the same ISBN/special identifier does not need to get the cover URL
        again. Use the caching API for this.

        Every Metadata object put into result_queue by this method must have a
        `source_relevance` attribute that is an integer indicating the order in
        which the results were returned by the metadata source for this query.
        This integer will be used by :meth:`compare_identify_results`. If the
        order is unimportant, set it to zero for every result.

        Make sure that any cover/ISBN mapping information is cached before the
        Metadata object is put into result_queue.

        :param log: A log object, use it to output debugging information/errors
        :param result_queue: A result Queue, results should be put into it.
                            Each result is a Metadata object
        :param abort: If abort.is_set() returns True, abort further processing
                      and return as soon as possible
        :param title: The title of the book, can be None
        :param authors: A list of authors of the book, can be None
        :param identifiers: A dictionary of other identifiers, most commonly
                            {'isbn':'1234...'}
        :param timeout: Timeout in seconds, no network request should hang for
                        longer than timeout.
        :return: None if no errors occurred, otherwise a unicode representation
                 of the error suitable for showing to the user
        '''
        if abort.is_set():
            return None

        log.info('Identification of a book')

        wolnelektury_id = identifiers.get(WOLNELEKTURY_ID)
        if (wolnelektury_id is None) and (search_result := self.get_book_url(identifiers)):
            wolnelektury_id = search_result[1]
        if abort.is_set():
            return None

        found_books = []
        if wolnelektury_id is None:
            log.info('Preliminary identification failed. Complex search starts')
            data = {
                'title': title,
                'authors': authors
            }
            rq = Queue()
            worker_input = WorkerInput(
                data,
                log,
                timeout,
                self,
                rq
            )
            check_site_for_books(worker_input, abort)
            if rq.empty():
                log.error('No book could be identified on wolnelektury.pl')
                return None
            #found_books = list( iter(rq.get_nowait()) )
            while not rq.empty():
                tmp = rq.get_nowait()
                # ToDo: solve this hack
                # queue expands 1st list, next are included as are
                #if isinstance(tmp, list):
                    #found_books.extend(tmp)
                #found_books.append(rq.get_nowait())
                found_books.extend(tmp)
        else:
            log.info('Preliminary identification was a success')
            found_books = [wolnelektury_id]

        if abort.is_set():
            return None

        if len(found_books) == 0:
            log.error('No book could be identified on wolnelektury.pl')
            return None
        log.info(f'Found books\' ids: {found_books}')

        workers_input = []
        for i, book_id in enumerate(found_books, 1):
            basic_data = { WOLNELEKTURY_ID: book_id, 'relevance': i }
            w = WorkerInput(
                basic_data,
                log,
                timeout,
                self,
                result_queue
            )
            workers_input.append(w)

        if abort.is_set():
            return None

        log.info('Starting metadata download')
        MetadataWorker.run_workers(workers_input, abort)

        return None
    # pylint: enable=too-many-positional-arguments, too-many-arguments, dangerous-default-value

    # pylint: disable=too-many-positional-arguments, too-many-arguments, dangerous-default-value
    def download_cover(self, log, result_queue, abort,
            title=None, authors=None, identifiers={}, timeout=30, get_best_cover=False):
        '''
        Download a cover and put it into result_queue. The parameters all have
        the same meaning as for :meth:`identify`. Put (self, cover_data) into
        result_queue.

        This method should use cached cover URLs for efficiency whenever
        possible. When cached data is not present, most plugins simply call
        identify and use its results.

        If the parameter get_best_cover is True and this plugin can get
        multiple covers, it should only get the "best" one.
        '''
        log.info('Downloading cover')
        urls = self.get_cached_cover_url(identifiers)
        if urls is None:
            log.info('No cached cover found, running identify')
            rq = Queue()
            self.identify(log, rq, abort, title, authors, identifiers, timeout)

            if abort.is_set():
                return None

            if rq.empty():
                return None
            book = rq.get()
            # ToDo: is it right?
            if book.source_relevance == 1:
                urls = self.get_cached_cover_url(book.get_identifiers())
            else:
                # ToDo: should be changed to never?
                raise RuntimeError('Should not be accesible!')
        else:
            log.info('Cached covers found.')

        if abort.is_set():
            return None

        if len(urls) == 0:
            log.error('No book cover found')
            return None

        if abort.is_set():
            return None
        self.download_multiple_covers(
            title,
            authors,
            urls,
            get_best_cover,
            timeout,
            result_queue,
            abort,
            log
        )

        return None
    # pylint: enable=too-many-positional-arguments, too-many-arguments, dangerous-default-value

if __name__ == "__main__":
    # To run these test use:
    # calibre-debug -e __init__.py
    from io import StringIO
    import sys
    import contextlib
    # pylint: disable=import-error,ungrouped-imports
    from calibre.ebooks.metadata.sources.test import authors_test, comments_test,\
        pubdate_test, test_identify_plugin, title_test, isbn_test
    from calibre import prints

    tests = [
        (  # (0) A title, author search and pub date
         {'title': 'Lalka', 'authors':['Bolesław Prus']},
         [title_test('Lalka', exact=True),
          authors_test(['Bolesław Prus']),
          pubdate_test(2008, 12, 10)]
        ),

        (  # (1) An id from the site
         {'identifiers':{WOLNELEKTURY_ID: 'sienkiewicz-jako-sie-pan-lubomirski-nawrocil'}, },
         [title_test('Jako się pan Lubomirski nawrócił i kościół w Tarnawie zbudował', exact=True),
          authors_test(['Henryk Sienkiewicz'])]
        ),

        (  # (2) An url from the site
         {'identifiers':{'url': 'https://wolnelektury.pl/katalog/lektura/sienkiewicz-jako-sie-pan-lubomirski-nawrocil/'}, },
         [title_test('Jako się pan Lubomirski nawrócił i kościół w Tarnawie zbudował', exact=True),
          authors_test(['Henryk Sienkiewicz'])]),

        ( # (3) Multiple authors, special symbol in title and isbn
        {'title': 'manto',},
        [title_test('#manto', exact=True),
         authors_test([
            'Łukasz Orbitowski', 'Jacek Świdziński']),
        isbn_test('978-83-288-5848-0')
        ])
    ]
    tests_to_fail = [( # (0) No isbn and comments
         {'identifiers':{WOLNELEKTURY_ID: 'napoj-cienisty-lalka'}, },
         [title_test('Lalka', exact=True),
         authors_test(['Bolesław Leśmian']),
    ])]
    tests = tests[:]

    out = StringIO()
    try:
        with contextlib.redirect_stderr(out):
            with contextlib.redirect_stdout(out):
                test_identify_plugin(WolneLekturySource.name, tests)
    except SystemExit as e:
        prints(out.getvalue())
        prints('Basic tests failed')
        raise SystemExit from e
    prints('Basic tests passed')

    out = StringIO()
    def check_test(stream: StringIO) -> bool:
        '''
        Checks if test failed 'correctly'
        '''
        test_line = stream.getvalue().splitlines()[-1]
        if test_line in set(['Failed to find identifier: isbn2', 'Failed to find comments2']):
            return True
        return False
    try:
        with contextlib.redirect_stderr(out):
            with contextlib.redirect_stdout(out):
                test_identify_plugin(WolneLekturySource.name, tests_to_fail)
    except SystemExit as e:
        if e.args[0] != 1 or check_test(out):
            prints(out.getvalue())
            prints('Complex tests failed')
            raise SystemExit(1) from e
    else:
        prints(out.getvalue())
        prints('Complex tests failed')
        raise SystemExit(1)
    prints('Complex tests passed')
