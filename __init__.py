'''
Metadata source plugin using wolnelektury.pl page
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

import gettext

# pylint: disable=import-error
from calibre.ebooks.metadata.sources.base import Source, Option
from calibre.utils.localization import _
# ToDo: to be removed and replaced with local implementation
from calibre.ebooks.metadata.sources.base import InternalMetadataCompareKeyGen

from calibre_plugins.wolnelektury_source.main import get_metadata, get_cover_urls, \
    BaseArgs, access_data, check_site_for_books, WOLNELEKTURY_ID
# pylint: enable=import-error

# pylint: disable=undefined-variable
# required to run tests
try:
    load_translations()
except NameError:
    pass
# pylint: enable=undefined-variable

PLUGIN_VERSION = (0, 2, 2)

class WolneLekturySource(Source):
    '''
    source plugin definition
    '''
    name = 'WolneLektury'
    author = 'Łukasz Kozak'
    description = _('Downloading metadata and covers from site wolnelektury.pl')
    version = PLUGIN_VERSION
    # ToDo: TBD, should be checked, it's first version with Python 3
    minimum_calibre_version = (5, 0, 0) 
    supported_platforms = ['windows', 'osx', 'linux']
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

    has_html_comments = True # ToDo: add as an option
    supports_gzip_transfer_encoding = False
    ignore_ssl_errors = False
    cached_cover_url_is_reliable = True # ToDo: confirm
    config_help_message = None # ToDo
    can_get_multiple_covers = True
    auto_trim_covers = False # ToDo: confirm
    prefer_results_with_isbn = False
    options = (
        Option('html_comments', 'bool', True, _('HTML in comments'),
            _('Choose if comments\' formating should be downloaded as well')),
        Option('prefered_cover', 'choices', 'cover',
           _('Prefered cover type'), _('Choose which cover type you prefere'),
            {'cover': _('Regular cover'), 'simple_cover': _('Simplified cover')}),
        # ToDo: can it be limited to max number?
        Option('max_covers', 'number', 2, _('Maximal number of covers to download'),
                      _('Maximal number of covers to download from the site (up to 2)')),
    )

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
        needed as 'max_covers' already used and if left as 0, calibre remembers it and shows no covers
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
        # ToDo: should validate the adresses
        cover_url = None
        if wolnelektury_id := identifiers.get(WOLNELEKTURY_ID):
            cover_url = f'https://wolnelektury.pl/media/book/cover/{wolnelektury_id}.jpg'
        elif result := self.get_book_url(identifiers):
            cover_url = f'https://wolnelektury.pl/media/book/cover/{result[1]}.jpg'
        if cover_url:
            # ToDo: make sure it makes sense
            with access_data(self.browser.open_novisit(cover_url, timeout=10), None) as page:
                if page.getcode() != 200:
                    cover_url = None
        return cover_url

    WOLNELEKTURY_ID_REGEX = re.compile(
        r'(https?:\/\/)(www.)?wolnelektury.pl\/katalog\/lektura\/([a-z\-]+)\/?'
    )

    def id_from_url(self, url):
        '''
        Parse a URL and return a tuple of the form:
        (identifier_type, identifier_value).
        If the URL does not match the pattern for the metadata source,
        return None.
        '''
        search_result = self.WOLNELEKTURY_ID_REGEX.search(url)
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

        base_args = BaseArgs(abort, self.browser, log, timeout)
        found_books = []
        if wolnelektury_id is None:
            log.info('Preliminary identification failed. Complex search starts')
            found_books = check_site_for_books(
                base_args,
                self.get_title_tokens(title),
                self.get_author_tokens(authors)
            )
        else:
            log.info('Preliminary identification was a success')
            found_books = [wolnelektury_id]

        if abort.is_set():
            return None

        if len(found_books) == 0:
            return 'The book could not be identified on wolnelektury.pl'

        no_books = 0
        for book_id in found_books:
            if me := get_metadata(base_args, book_id):
                me.set_identifier(WOLNELEKTURY_ID, book_id)
                no_books += 1
                me.source_relevance = no_books
                self.clean_downloaded_metadata(me)
                result_queue.put(me)
                log.info(
                    f'Metadata for "{book_id}" id found on the site'
                )
            else:
                log.error(
                    f'Metadata could not be found for "{book_id}" id on the site'
                )
            if abort.is_set():
                return None

        log.info(f'{no_books} books metadata were downloaded')

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
        if get_best_cover and (cover_url := self.get_cached_cover_url(identifiers)):
            result_queue.put((self, cover_url))
            log.info('Downloaded best cover')
            return None

        wolnelektury_id = identifiers.get(WOLNELEKTURY_ID)
        identify_queue = Queue()
        found_books: list[str] = []

        if wolnelektury_id is None:
            result = self.identify(log, identify_queue, abort, title, authors, identifiers, timeout)
            if abort.is_set():
                return None

            if result is not None:
                return result
            if not identify_queue.empty:
                found_books = [book_id for me in iter(identify_queue.get_nowait, None) \
                    if (book_id := me.get_identifiers().get(WOLNELEKTURY_ID))]
        else:
            found_books = [wolnelektury_id]

        if len(found_books) == 0:
            return 'No books were identified to find covers'

        urls: list[str] = []
        base_args = BaseArgs(abort, self.browser, log, timeout)
        for book_id in found_books:
            urls.extend(get_cover_urls(base_args, wolnelektury_id, get_best_cover))

        log.info(f'Found cover urls: {urls}')

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
    # pylint: disable=import-error,ungrouped-imports
    from calibre.ebooks.metadata.sources.test import authors_test, comments_test,\
        pubdate_test, test_identify_plugin, title_test, isbn_test
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
        ]),

        ( # (4) Non polish language book
         {'identifiers': { WOLNELEKTURY_ID: 'nietzsche-richard-wagner-in-bayreuth'}, },
         [title_test('Richard Wagner in Bayreuth', exact=True),
         lambda me: bool(me.language == 'ger')
        ])
    ]
    tests_to_fail = [( # (0) No isbn and comments
         {'identifiers':{WOLNELEKTURY_ID: 'napoj-cienisty-lalka'}, },
         [title_test('Lalka', exact=True),
         authors_test(['Bolesław Leśmian']),
         lambda me: bool(me.comments is None and me.isbn is None)
    ])]
    tests = tests[:]
    test_identify_plugin(WolneLekturySource.name, tests)
    try:
        test_identify_plugin(WolneLekturySource.name, tests_to_fail)
    except SystemExit as e:
        # ToDo: not exact, should be modified or removed!
        if e.args[0] != 1:
            raise SystemExit(1) from e
    else:
        raise SystemExit(1)
