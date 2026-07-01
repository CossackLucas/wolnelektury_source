'''
Module with everything config related
'''

from typing import Any
from collections import namedtuple
import textwrap

# pylint: disable=import-error
from calibre.gui2.metadata.config import ConfigWidget as DefaultConfigWidget
from calibre.utils.config import JSONConfig
from calibre.ebooks.metadata.sources.base import Option
try:
    from calibre.utils.localization import _
except ImportError:
    from gettext import gettext as _

from calibre_plugins.wolnelektury_source.consts import PLUGIN_NAME, COVER_NAMES

from qt.core import QWidget, QLabel, QSpinBox, QListWidgetItem, QCheckBox, QListWidget, \
    QAbstractItemView
# pylint: enable=import-error

# pylint: disable=undefined-variable
# required to run tests
try:
    load_translations()
except NameError:
    pass
# pylint: enable=undefined-variable

def _get_defaults(options: list[Option]) -> dict:
    result = {}
    for option in options:
        result[option.name] = option.default
    return result

class PluginConfig:
    '''
    class used in everything related to plugin's config
    '''
    def __init__(self):
        # Localization is ~/.config/calibre/metadata_sources/WolneLektury.json
        self.__config = JSONConfig(f'metadata_sources/{PLUGIN_NAME}.json')
        self.__options = [
            Option('html_comments', 'bool', True, _('HTML in comments'),
                _('Choose if comments\' formating should be downloaded as well')),
            Option('prefered_covers', 'choices', list(COVER_NAMES.keys()),
                _('Prefered cover type'), _('Choose which cover type you prefere')),
            Option('max_covers', 'number', 2, _('Maximal number of covers to download'),
                _('Maximal number of covers to download from the site (up to 2)')),
    ]

        self.__config.defaults['Options'] = _get_defaults(self.__options)
        self.__ignoreable_fields = set(('publisher', 'pubdate', 'comments'))

    def get_pref(self, opt: str) -> Any:
        '''
        Returns value of requested preference
        If it's one of the ignore_fields, return True if the field should be extracted
        and False if it should be ignored
        Raises:
        ValueError: if value opt could not be found among the included
        '''
        if opt in self.__ignoreable_fields:
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

# aggregates data from COVER_NAMES dict records
CoverType = namedtuple('CoverType', ['cover_type', 'description'])

# pylint: disable=too-few-public-methods
class CoverItem(QListWidgetItem):
    '''
    Wrapper class for cover items used in QtListWidget
    '''
    def __init__(self, cover: CoverType, widget: QWidget):
        super().__init__(cover.description, widget, QListWidgetItem.ItemType.UserType)
        self._value = cover

    @property
    def value(self) -> CoverType:
        '''
        returns CoverType of the item
        '''
        return self._value
# pylint: enable=too-few-public-methods

class ConfigWidget(DefaultConfigWidget):
    '''
    Personalized config Qt widget
    '''
    def create_widgets(self, opt: Option):
        '''
        Automating widget creation. Modified standard method
        '''
        val: Any = self.plugin.prefs[opt.name]
        if opt.type == 'number':
            widget = QSpinBox(self)
            widget.setRange(1, opt.default)
            widget.setValue(val)
        elif opt.type == 'bool':
            widget = QCheckBox(opt.label, self)
            widget.setChecked(bool(val))
        elif opt.type == 'choices':
            widget = QListWidget(self)
            widget.setDragEnabled(True)
            widget.setAcceptDrops(False)
            widget.setDropIndicatorShown(True)
            widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
            max_width = 0
            for value in COVER_NAMES.values():
                if (width := len(value)) > max_width:
                    max_width = width
            widget.setMaximumSize(10*max_width, 25*len(COVER_NAMES))

            # prepared for new options
            if len(COVER_NAMES) != len(val):
                values = set(COVER_NAMES.keys())
                diff = values - set(val)
                for item in diff:
                    val.append(item)
            for item in val:
                widget.addItem(CoverItem(CoverType(item, COVER_NAMES[item]), widget))
        widget.opt = opt
        widget.setToolTip(textwrap.fill(opt.desc))
        self.widgets.append(widget)
        r = self.l.rowCount()
        if opt.type == 'bool':
            self.l.addWidget(widget, r, 0, 1, self.l.columnCount())
        else:
            l = QLabel(opt.label)
            l.setToolTip(widget.toolTip())
            self.memory.append(l)
            l.setBuddy(widget)
            self.l.addWidget(l, r, 0, 1, 1)
            self.l.addWidget(widget, r, 1, 1, 1)

    def commit(self):
        '''
        save widget config values into preferences
        Raises:
        TypeError: if widget type is not supported
        '''
        self.fields_model.commit()
        for w in self.widgets:
            match w:
                case QSpinBox():
                    val = w.value()
                case QCheckBox():
                    val = w.isChecked()
                case QListWidget():
                    val = []
                    count = w.count()
                    for i in range(0, count):
                        item = w.item(i).value
                        val.append(item.cover_type)
                case _:
                    raise TypeError(f'Qt widget type {type(w)} is not supported')
            self.plugin.prefs[w.opt.name] = val
