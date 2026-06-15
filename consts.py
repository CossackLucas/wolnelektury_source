'''
Source of main data
'''

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

PLUGIN_VERSION = (0, 4, 1)
PLUGIN_NAME = 'WolneLektury'
WOLNELEKTURY_ID = 'wolnelektury'

COVER_NAMES = {'cover': _('Regular cover'), 'simple_cover': _('Simplified cover')}
