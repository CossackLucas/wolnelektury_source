'''
Source of main data
'''
import re

# pylint: disable=import-error
from calibre.utils.localization import _
# pylint: enable=import-error

# pylint: disable=undefined-variable
# required to run tests
try:
    load_translations()
except NameError:
    pass
# pylint: enable=undefined-variable

PLUGIN_VERSION = (0, 5, 2)
PLUGIN_NAME = 'WolneLektury'
WOLNELEKTURY_ID = 'wolnelektury'

COVER_NAMES = {'cover': _('Regular cover'), 'simple_cover': _('Simplified cover')}

ID_REGEX = re.compile(r'/katalog/lektura/([a-z\-]+)/')
AUTHOR_ID_REGEX = re.compile(r'/katalog/autor/([a-z\-]+)/')
WOLNELEKTURY_ID_REGEX = (
    re.compile(r'(https?:\/\/)(www.)?wolnelektury.pl\/katalog\/lektura\/([a-z\-]+)\/?'),
    re.compile(r'(https?:\/\/)(www.)?wolnelektury.pl\/media\/book\/cover\/([a-z\-]+).jpg\/?'),
    re.compile(
        r'(https?:\/\/)(www.)?wolnelektury.pl\/media\/book\/cover_simple\/([a-z\-]+)_[a-zA-Z0-9]+.jpg\/?'
    )
)
