'''
Module with everything config related
'''

from typing import Optional

# pylint: disable=import-error
from calibre.gui2.metadata.config import ConfigWidget as DefaultConfigWidget
from calibre.utils.config import JSONConfig
from calibre.ebooks.metadata.sources.base import Source, Option
try:
    from calibre.utils.localization import _
except ImportError:
    from gettext import gettext as _

from calibre_plugins.wolnelektury_source.consts import PLUGIN_NAME, COVER_NAMES
# pylint: enable=import-error

# pylint: disable=undefined-variable
# required to run tests
try:
    load_translations()
except NameError:
    pass
# pylint: enable=undefined-variable

class PluginConfig:
    '''
    class used in everything related to plugin's config
    '''
    # Localization is ~/.config/calibre/metadata_sources/WolneLektury.json
    __config = JSONConfig(f'metadata_sources/{PLUGIN_NAME}.json')
    __options = [
        Option('html_comments', 'bool', True, _('HTML in comments'),
            _('Choose if comments\' formating should be downloaded as well')),
        Option('prefered_cover', 'choices', 'cover',
           _('Prefered cover type'), _('Choose which cover type you prefere'),
           COVER_NAMES),
        Option('max_covers', 'number', 2, _('Maximal number of covers to download'),
                      _('Maximal number of covers to download from the site (up to 2)')),
    ]

    def __init__(self):
        self.__config.defaults['Options'] = {
            'html_comments': True,
            'prefered_cover': 'cover',
            'max_covers': 2
        }

    def get_pref(self, opt: str) -> Optional[bool|str|int]:
        '''
        Returns value of requested preference
        If it's one of the ignore_fields, return True if the field should be extracted
        and false if it should be ignored
        Raises:
        ValueError: if value opt could not be found among the included
        '''
        if opt in set(('publisher', 'pubdate', 'comments')):
            if (ignore_fields := self.__config.get('ignore_fields')) is not None and \
                opt in ignore_fields:
                return False
            return True

        if (value := self.__config.get(opt)) is not None:
            return value

        raise ValueError(f'\'{opt}\' not among allowed values')

    def get_prefs(self) -> dict:
        '''
        return the entire config dictionary
        '''
        return self.__config

    def get_options(self) -> list[Option]:
        '''
        returns list of Options available in the config widget
        '''
        return self.__options

config = PluginConfig()

# pylint: disable=too-few-public-methods
class ConfigWidget(DefaultConfigWidget):
    '''
    Custom widget for plugin's config edition
    '''
    def __init__(self, plugin: Source):
        super().__init__(plugin)
# pylint: enable=too-few-public-methods
