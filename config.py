'''
Module with everything config related
'''

from typing import Optional, Any
import textwrap

# pylint: disable=import-error
from calibre.gui2.metadata.config import ConfigWidget as DefaultConfigWidget
from calibre.gui2.metadata.config import FieldsModel, FieldsList
from calibre.utils.config import JSONConfig
from calibre.utils.icu import sort_key
from calibre.ebooks.metadata.sources.base import Source, Option
try:
    from calibre.utils.localization import _
except ImportError:
    from gettext import gettext as _

from calibre_plugins.wolnelektury_source.consts import PLUGIN_NAME, COVER_NAMES

from qt.core import QWidget, QLabel, QVBoxLayout, QSpinBox, QDoubleSpinBox, \
    QCheckBox, QComboBox, QListView, QGridLayout, QGroupBox, QListWidget, QAbstractItemView
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

class ConfigWidget(QWidget):
    '''
    Personalized config Qt widget
    '''
    def __init__(self, plugin: Source):
        super().__init__()
        self.plugin = plugin

        self.overl = l = QVBoxLayout(self)
        if plugin.config_help_message:
            self.pchm = QLabel(plugin.config_help_message)
            self.pchm.setWordWrap(True)
            self.pchm.setOpenExternalLinks(True)
            l.addWidget(self.pchm, 10)

        # ignored fields selection widget
        # ToDo: try to synchronize with calibre translation
        # ToDo: modifying existing class or initilaised version could be neccesery
        self.gb = QGroupBox(_('Metadata fields to download'), self)
        l.addWidget(self.gb)
        self.gb.l = g = QVBoxLayout(self.gb)
        # ToDo: check docs and set proper size and position
        g.setContentsMargins(0, 0, 0, 0)
        self.fields_view = v = FieldsList(self)
        g.addWidget(v)
        v.setFlow(QListView.Flow.LeftToRight)
        v.setWrapping(True)
        v.setResizeMode(QListView.ResizeMode.Adjust)
        self.fields_model = FieldsModel(self.plugin)
        self.fields_model.initialize()
        v.setModel(self.fields_model)

        # Option(s) widgets
        self.memory: list[QLabel] = []
        self.widgets: list[QWidget] = []
        self.l = QGridLayout()
        # ToDo: check docs and set correctly
        self.l.setContentsMargins(0, 0, 0, 0)
        l.addLayout(self.l, 100)
        for opt in plugin.options:
            self.create_widgets(opt)

    def create_widgets(self, opt: Option):
        '''
        Automating widget creation. Modified standard method
        '''
        val: Any = self.plugin.prefs[opt.name]
        if opt.type == 'number':
            c = QSpinBox
            widget = c(self)
            widget.setRange(1, opt.default)
            widget.setValue(val)
        elif opt.type == 'bool':
            widget = QCheckBox(opt.label, self)
            widget.setChecked(bool(val))
        elif opt.type == 'choices':
            widget = QListWidget(self)
            # ToDo check docs, set size and pos and check params
            widget.setDragEnabled(True)
            widget.setAcceptDrops(True)
            widget.setDropIndicatorShown(True)
            widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
            default = COVER_NAMES[opt.default]
            cover_names_list = [default]
            list_def = list(COVER_NAMES.values())
            idx_default = list_def.index(default)
            list_def.pop(idx_default)
            cover_names_list.extend(list_def)
            widget.addItems(cover_names_list)
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
        '''
        self.fields_model.commit()
        for w in self.widgets:
            # replace with match?
            # case Class():
            val = None
            if isinstance(w, (QSpinBox, QDoubleSpinBox)):
                val = w.value()
            elif isinstance(w, QCheckBox):
                val = w.isChecked()
            elif isinstance(w, QListWidget):
                val = w.item(0).text()
            elif isinstance(w, QComboBox):
                idx = w.currentIndex()
                val = str(w.itemData(idx) or '')
            self.plugin.prefs[w.opt.name] = val
