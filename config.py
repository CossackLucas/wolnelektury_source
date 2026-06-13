'''
Module with everything config related
'''

from typing import Optional

# pylint: disable=import-error
from calibre.utils.config import JSONConfig
# pylint: enable=import-error

class PluginConfig:
# Localization is ~/.config/calibre/metadata_sources/WolneLektury.json
    config = JSONConfig('metadata_sources/WolneLektury.json')

    def get_prefs(self, opt: str) -> Optional[bool|str|int]:
        if opt in set(('publisher', 'pubdate', 'comments')):
            if (ignore_fields := self.config.get('ignore_fields')) is not None and \
                opt in ignore_fields:
                return False
            return True

        if (value := self.config.get(opt)) is not None:
            # ToDo: should be validated on input
            if opt == 'max_covers':
                value = self.__clean_max_covers(value)
            return value

        raise ValueError(f'\'{opt}\' not among allowed values')

    def __clean_max_covers(self, value: int) -> int:
        value = max(value, 1)
        value = min(value, 2)
        return value

prefs = PluginConfig()
