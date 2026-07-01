'''
Source of main data
'''
import re

# pylint: disable=import-error
from calibre.constants import numeric_version
try:
    from calibre.utils.localization import _
except ImportError:
    from gettext import gettext as _
# pylint: enable=import-error

# pylint: disable=undefined-variable
# required to run tests
try:
    load_translations()
except NameError:
    pass
# pylint: enable=undefined-variable

PLUGIN_VERSION = (1, 0, 0)
PLUGIN_NAME = 'WolneLektury'
WOLNELEKTURY_ID = 'wolnelektury'

ID_REGEX = re.compile(r'/katalog/lektura/([a-z\-]+)/')
AUTHOR_ID_REGEX = re.compile(r'/katalog/autor/([a-z\-]+)/')
WOLNELEKTURY_ID_REGEX = (
    re.compile(r'(https?:\/\/)(www.)?wolnelektury.pl\/katalog\/lektura\/([a-z\-]+)\/?'),
    re.compile(r'(https?:\/\/)(www.)?wolnelektury.pl\/media\/book\/cover\/([a-z\-]+).jpg\/?'),
    re.compile(
        r'(https?:\/\/)(www.)?wolnelektury.pl\/media\/book\/cover_simple\/([a-z\-]+)_[a-zA-Z0-9]+.jpg\/?'
    )
)

PLUGIN_DESCRIPTION = _('Download metadata and covers from site wolnelektury.pl')

CONFIG_HELP_MESSAGE = '<p>' + _('Calibre') + ': <b>' + \
    ".".join([str(x) for x in numeric_version]) + \
    '</b> • ' + _('Plugin version') + ': <b>' + \
    '.'.join([str(x) for x in PLUGIN_VERSION]) + \
    '</b> • ' + _('Please report bugs through the ') + \
    '<a href="https://www.mobileread.com/forums/showthread.php?t=373972">' + \
    _('MobileRead') + '</a>' + _(' forum or ') + \
    '<a href="https://github.com/CossackLucas/wolnelektury_source">' + _('GitHub') + '</a>' + \
    _('.') + '<br><b>' + _('Warning') + '</b>: ' + \
    _('ISBN could be pointing to different file format edition of the book.')
