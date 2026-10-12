"""Desktop interface for the Sound Blaster controller."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import subprocess
import sys

from PySide6.QtCore import QObject, QRectF, Qt, QSettings, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame,
    QGridLayout, QHBoxLayout, QKeySequenceEdit, QLabel, QLineEdit, QMainWindow, QMenu, QPushButton,
    QScrollArea, QSlider, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

from .i18n import translate
from .shortcuts import (ShortcutConflict, ShortcutError, activate_shortcut,
                        configured_shortcut)

ICON = Path(__file__).resolve().parent.parent / 'assets' / 'soundblaster.svg'

STYLE = """
QWidget { background: #17191e; color: #f5f2ef; font-family: 'Noto Sans', sans-serif; font-size: 13px; }
QLabel { background: transparent; }
QPushButton#choice QLabel, QPushButton#choice QWidget { background: transparent; }
QFrame#sidebar { background: #1f2229; border-right: 1px solid #30343b; }
QLabel#brand { font-size: 15px; font-weight: 750; }
QLabel#eyebrow { color: #f3a36e; font-size: 11px; font-weight: 700; letter-spacing: 1.5px; }
QLabel#title { font-size: 34px; font-weight: 750; }
QLabel#subtitle, QLabel#muted, QLabel#status { color: #a2a6ae; }
QLabel#cardtitle, QLabel#device { font-size: 17px; font-weight: 700; }
QLabel#section { font-size: 12px; color: #a2a6ae; font-weight: 650; letter-spacing: 1px; }
QLabel#value { font-size: 30px; font-weight: 750; }
QFrame#panel { background: #22252c; border: 1px solid #353942; border-radius: 18px; }
QFrame#panel[muted="true"] { border-color: #bb705c; }
QFrame#tip { background: #282a2e; border: 1px solid #383a3d; border-radius: 14px; }
QPushButton#nav { background: transparent; border: 0; border-radius: 10px; color: #aeb1b8; text-align: left; padding: 13px 15px; font-weight: 600; }
QPushButton#nav:hover { background: #30343c; color: white; }
QPushButton#nav[active="true"] { background: #3b302c; color: #ffaf7d; }
QPushButton#choice { background: #282b32; border: 1px solid #3c4049; border-radius: 16px; text-align: left; }
QPushButton#choice:hover { background: #30343b; border-color: #7d6051; }
QPushButton#choice[active="true"] { background: #3b302c; border: 2px solid #ef9664; }
QPushButton#choice:disabled { color: #777b83; border-color: #33363d; }
QPushButton#pill { background: #34383f; border: 1px solid #474b53; border-radius: 10px; padding: 9px 16px; font-weight: 650; }
QPushButton#pill:hover { background: #41454e; }
QPushButton#pill[muted="true"] { background: #ef9664; border-color: #ef9664; color: #241b17; }
QPushButton#primary { background: #ed9667; color: #201914; border: 0; border-radius: 10px; padding: 11px 18px; font-weight: 750; }
QPushButton#primary:hover { background: #ffab7b; }
QPushButton#primary:disabled { background: #685c56; color: #bbb0aa; }
QSlider::groove:horizontal { height: 7px; background: #444750; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #ef9664; border-radius: 3px; }
QSlider::handle:horizontal { background: #ffb98f; width: 19px; margin: -6px 0; border-radius: 9px; }
QCheckBox { spacing: 12px; }
QCheckBox { background: transparent; }
QCheckBox::indicator { width: 17px; height: 17px; }
QComboBox { background: #34383f; border: 1px solid #51545c; border-radius: 9px; padding: 7px 11px; min-width: 140px; }
QComboBox QAbstractItemView { background: #282b32; color: #f5f2ef; selection-background-color: #694738; }
QKeySequenceEdit { background: #34383f; border: 1px solid #51545c; border-radius: 9px; padding: 6px 10px; }
QKeySequenceEdit QLineEdit { background: transparent; border: none; color: #f5f2ef; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #555963; border-radius: 4px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


def label(text, kind=None, wrap=False):
    widget = QLabel(text)
    widget.setProperty('source_text', text)
    if kind:
        widget.setObjectName(kind)
    widget.setWordWrap(wrap)
    return widget


def button(text, kind='pill'):
    widget = QPushButton(text)
    widget.setProperty('source_text', text)
    widget.setObjectName(kind)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    return widget


class Glyph(QWidget):
    def __init__(self, kind):
        super().__init__()
        self.kind = kind
        self.setFixedSize(54, 54)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor('#f4ae81'), 2.7))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if self.kind == 'speakers':
            shape = QPainterPath()
            shape.moveTo(8, 22); shape.lineTo(17, 22); shape.lineTo(27, 14)
            shape.lineTo(27, 40); shape.lineTo(17, 32); shape.lineTo(8, 32)
            shape.closeSubpath()
            p.drawPath(shape)
            p.drawArc(QRectF(25, 15, 19, 24), -75 * 16, 150 * 16)
            p.drawArc(QRectF(22, 8, 30, 38), -70 * 16, 140 * 16)
        else:
            p.drawArc(QRectF(9, 9, 36, 36), 0, 180 * 16)
            p.drawRoundedRect(QRectF(8, 29, 9, 17), 3, 3)
            p.drawRoundedRect(QRectF(37, 29, 9, 17), 3, 3)
            p.drawLine(13, 21, 13, 30)
            p.drawLine(41, 21, 41, 30)


class Choice(QPushButton):
    def __init__(self, kind, title, description):
        super().__init__()
        self.setObjectName('choice')
        self.setFixedHeight(160)
        self.setMinimumWidth(230)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(title + ' auswählen')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 17, 20, 17)
        layout.setSpacing(6)
        top = QHBoxLayout()
        top.addWidget(Glyph(kind))
        top.addStretch()
        self.badge = label('AKTIV', 'eyebrow')
        top.addWidget(self.badge)
        layout.addLayout(top)
        layout.addStretch()
        layout.addWidget(label(title, 'cardtitle'))
        self.description = label(description, 'muted')
        layout.addWidget(self.description)
        self.set_active(False)

    def set_active(self, active):
        self.setProperty('active', active)
        self.badge.setVisible(active)
        self.style().unpolish(self)
        self.style().polish(self)


class Bridge(QObject):
    finished = Signal(object, object)


class MainWindow(QMainWindow):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.bridge = Bridge()
        self.bridge.finished.connect(self._job_finished)
        self.current = None
        self.connection_error = None
        self.busy = False
        self.job_kind = ''
        self.volume_pending = False
        self.effect_pending = {}
        self.app_pending = {}
        self.effect_widgets = {}
        self.app_rows = {}
        self.closing_for_real = False
        self.settings = QSettings('SoundBlasterControl', 'SoundBlasterControl')
        self.language = self.settings.value('language', 'de')
        if self.language not in ('de', 'en'):
            self.language = 'de'
        self.latest_effects = None
        self.latest_apps = None
        self.setWindowTitle('OutputDeck')
        self.setWindowIcon(QIcon(str(ICON)))
        self.setMinimumSize(840, 620)
        self.resize(1020, 700)
        self.setStyleSheet(STYLE)
        self._build()
        self._tray()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(2200)
        self.volume_timer = QTimer(self)
        self.volume_timer.setSingleShot(True)
        self.volume_timer.timeout.connect(self._commit_volume)
        self.effect_timer = QTimer(self)
        self.effect_timer.setSingleShot(True)
        self.effect_timer.timeout.connect(self._commit_effect)
        self.app_timer = QTimer(self)
        self.app_timer.setSingleShot(True)
        self.app_timer.timeout.connect(self._commit_app_volume)
        self._apply_language()
        self.refresh()

    def _t(self, source, **values):
        return translate(source, self.language, **values)

    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        sidebar = QFrame(objectName='sidebar')
        sidebar.setFixedWidth(216)
        left = QVBoxLayout(sidebar)
        left.setContentsMargins(19, 27, 19, 24)
        left.setSpacing(8)
        brand = QHBoxLayout()
        mark = label('◖))')
        mark.setStyleSheet('color: #f4a574; font-size: 23px; font-weight: 800;')
        brand.addWidget(mark)
        brand.addWidget(label('OUTPUTDECK', 'brand'))
        left.addLayout(brand)
        left.addSpacing(50)
        left.addWidget(label('STEUERUNG', 'section'))
        left.addSpacing(7)
        self.nav_output = button('Audio-Ausgabe', 'nav')
        self.nav_profiles = button('Klangprofile', 'nav')
        self.nav_effects = button('Soundeffekte', 'nav')
        self.nav_apps = button('Apps', 'nav')
        self.nav_device = button('Gerät && Infos', 'nav')
        self.nav_buttons = (self.nav_output, self.nav_profiles, self.nav_effects,
                            self.nav_apps, self.nav_device)
        for index, nav in enumerate(self.nav_buttons):
            nav.clicked.connect(lambda checked=False, index=index: self._page(index))
            left.addWidget(nav)
        left.addStretch()
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet('background: #3b3e45;')
        left.addWidget(line)
        left.addSpacing(13)
        left.addWidget(label('DEIN GERÄT', 'section'))
        self.side_device = label('Suche Soundkarte …', 'muted', True)
        left.addWidget(self.side_device)
        self.side_connection = label('', 'status', True)
        self.side_connection.hide()
        left.addWidget(self.side_connection)
        row.addWidget(sidebar)
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(45, 28, 45, 24)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._output_page())
        self.pages.addWidget(self._profiles_page())
        self.pages.addWidget(self._effects_page())
        self.pages.addWidget(self._apps_page())
        self.pages.addWidget(self._device_page())
        outer.addWidget(self.pages)
        row.addWidget(content, 1)
        self._page(0)

    def _output_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(label('OUTPUTDECK', 'eyebrow'))
        layout.addSpacing(13)
        layout.addWidget(label('Audio-Ausgabe', 'title'))
        layout.addSpacing(6)
        layout.addWidget(label('Wähle, wo du deinen Sound hören möchtest.', 'subtitle'))
        layout.addSpacing(18)
        heading = QHBoxLayout()
        heading.addWidget(label('AUSGANG WÄHLEN', 'section'))
        heading.addStretch()
        self.output_status = label('Ausgang wird erkannt …', 'status')
        heading.addWidget(self.output_status)
        layout.addLayout(heading)
        layout.addSpacing(13)
        choices = QHBoxLayout()
        choices.setSpacing(16)
        self.speakers = Choice('speakers', 'Lautsprecher', 'Sound über deine Boxen')
        self.headphones = Choice('headphones', 'Headset', 'Sound über deine Kopfhörer')
        self.speakers.clicked.connect(lambda: self._action('speakers', lambda: self.controller.select_output('speakers')))
        self.headphones.clicked.connect(lambda: self._action('headphones', lambda: self.controller.select_output('headphones')))
        choices.addWidget(self.speakers, 1)
        choices.addWidget(self.headphones, 1)
        layout.addLayout(choices)
        layout.addSpacing(9)
        layout.addWidget(label('Lautsprecher und Headset merken sich ihre Lautstärke getrennt.', 'muted', True))
        layout.addSpacing(11)
        self.volume_panel = QFrame(objectName='panel')
        volume = QVBoxLayout(self.volume_panel)
        volume.setContentsMargins(23, 20, 23, 22)
        volume.setSpacing(10)
        header = QHBoxLayout()
        header.addWidget(label('Lautstärke', 'cardtitle'))
        header.addStretch()
        self.volume_value = label('– %', 'value')
        header.addWidget(self.volume_value)
        volume.addLayout(header)
        volume.addWidget(label('Sound Blaster · Hauptausgang', 'muted'))
        volume.addSpacing(8)
        slider_row = QHBoxLayout()
        slider_row.setSpacing(18)
        slider_row.addWidget(label('◖', 'muted'))
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setEnabled(False)
        self.slider.valueChanged.connect(self._volume_changed)
        slider_row.addWidget(self.slider, 1)
        slider_row.addWidget(label('◖))', 'muted'))
        volume.addLayout(slider_row)
        volume.addSpacing(8)
        self.mute_button = button('Ton ausschalten')
        self.mute_button.setEnabled(False)
        self.mute_button.clicked.connect(lambda: self._action('mute', self.controller.toggle_mute))
        mute_row = QHBoxLayout()
        mute_row.setSpacing(16)
        mute_row.addWidget(self.mute_button)
        self.mute_status = label('Tonstatus wird erkannt …', 'status')
        mute_row.addWidget(self.mute_status)
        mute_row.addStretch()
        volume.addLayout(mute_row)
        self.volume_panel.setMinimumHeight(volume.sizeHint().height())
        layout.addWidget(self.volume_panel)
        layout.addStretch(1)
        self.shortcut_tip_frame = QFrame(objectName='tip')
        tip_row = QHBoxLayout(self.shortcut_tip_frame)
        tip_row.setContentsMargins(18, 15, 18, 15)
        tip_icon = label('⌨')
        tip_icon.setStyleSheet('color: #f0a070; font-size: 22px;')
        tip_row.addWidget(tip_icon)
        tip_row.addSpacing(7)
        self.shortcut_tip = label('Schnell wechseln mit deinem KDE-Tastenkürzel', 'muted', True)
        tip_row.addWidget(self.shortcut_tip)
        tip_row.addStretch()
        layout.addWidget(self.shortcut_tip_frame)
        layout.addSpacing(8)
        self.message = label('Bereit', 'status', True)
        layout.addWidget(self.message)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def _page_header(self, heading, subtitle):
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        layout.addWidget(label('OUTPUTDECK', 'eyebrow'))
        layout.addSpacing(6)
        layout.addWidget(label(heading, 'title'))
        layout.addWidget(label(subtitle, 'subtitle', True))
        return holder

    def _profiles_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        layout.addWidget(self._page_header('Klangprofile',
            'Speichere deinen aktuellen Ausgang, die Lautstärke und alle Effekte als Profil.'))
        layout.addWidget(label('DEINE PROFILE', 'section'))
        self.profile_cards = {}
        for name, note in (('Musik', 'Für deinen Lieblingsklang'),
                           ('Gaming', 'Für Spiele und räumlichen Sound'),
                           ('Nacht', 'Für entspanntes Hören')):
            card = QFrame(objectName='panel')
            row = QHBoxLayout(card)
            row.setContentsMargins(20, 17, 20, 17)
            text = QVBoxLayout()
            text.setSpacing(4)
            text.addWidget(label(name, 'cardtitle'))
            summary = label(note, 'muted', True)
            text.addWidget(summary)
            row.addLayout(text, 1)
            save = button('Aktuellen Klang speichern')
            apply = button('Aktivieren', 'primary')
            apply.setEnabled(False)
            save.clicked.connect(lambda checked=False, name=name: self._profile_action('profile_save', name))
            apply.clicked.connect(lambda checked=False, name=name: self._profile_action('profile_apply', name))
            row.addWidget(save)
            row.addWidget(apply)
            card.setMinimumHeight(row.sizeHint().height())
            layout.addWidget(card)
            self.profile_cards[name] = (summary, save, apply)
        layout.addWidget(label('Tipp: Stelle zuerst Ausgang, Lautstärke und Effekte ein. Speichere dann den Klang im gewünschten Profil.', 'muted', True))
        self.profile_message = label('', 'muted', True)
        layout.addWidget(self.profile_message)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def _effects_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(self._page_header('Soundeffekte',
            'Regle die Effekte deiner Sound Blaster Z direkt auf der Karte.'))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 8, 4)
        body_layout.setSpacing(14)
        main = QFrame(objectName='panel')
        main_layout = QHBoxLayout(main)
        main_layout.setContentsMargins(19, 15, 19, 15)
        main_text = QVBoxLayout()
        main_text.addWidget(label('Effekte aktivieren', 'cardtitle'))
        main_text.addWidget(label('Hauptschalter für die Ausgangseffekte', 'muted'))
        main_layout.addLayout(main_text, 1)
        self.outfx_check = QCheckBox()
        self.outfx_check.setEnabled(False)
        self.outfx_check.setAccessibleName('Ausgangseffekte aktivieren')
        self.outfx_check.toggled.connect(lambda enabled: self._effect_toggle('outfx', enabled))
        main_layout.addWidget(self.outfx_check)
        body_layout.addWidget(main)
        grid = QGridLayout()
        grid.setSpacing(14)
        names = (
            ('surround', 'Surround', 'Räumlicher Klang'),
            ('crystalizer', 'Crystalizer', 'Mehr Details im Sound'),
            ('xbass', 'X-Bass', 'Kräftigere Tiefen'),
            ('dialog', 'Dialog Plus', 'Deutlichere Stimmen'),
            ('smart_volume', 'Smart Volume', 'Gleichmäßigere Lautstärke'),
        )
        for number, (key, title, description) in enumerate(names):
            card = QFrame(objectName='panel')
            content = QVBoxLayout(card)
            content.setContentsMargins(18, 15, 18, 16)
            content.setSpacing(8)
            heading = QHBoxLayout()
            heading.addWidget(label(title, 'cardtitle'))
            heading.addStretch()
            toggle = QCheckBox()
            toggle.setEnabled(False)
            toggle.setAccessibleName(title + ' aktivieren')
            toggle.toggled.connect(lambda enabled, key=key: self._effect_toggle(key, enabled))
            heading.addWidget(toggle)
            content.addLayout(heading)
            content.addWidget(label(description, 'muted'))
            value_row = QHBoxLayout()
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setEnabled(False)
            value = label('– %', 'muted')
            slider.valueChanged.connect(lambda level, key=key, value=value:
                self._effect_level_changed(key, level, value))
            value_row.addWidget(slider, 1)
            value_row.addWidget(value)
            content.addLayout(value_row)
            if key == 'smart_volume':
                mode_row = QHBoxLayout()
                mode_row.addWidget(label('Modus', 'muted'))
                self.smart_combo = QComboBox()
                self.smart_combo.setEnabled(False)
                self.smart_combo.currentTextChanged.connect(lambda value:
                    self._effect_enum_changed('smart_mode', value))
                mode_row.addStretch()
                mode_row.addWidget(self.smart_combo)
                content.addLayout(mode_row)
            grid.addWidget(card, number // 2, number % 2)
            self.effect_widgets[key] = (toggle, slider, value)
        body_layout.addLayout(grid)
        equalizer = QFrame(objectName='panel')
        eq_row = QHBoxLayout(equalizer)
        eq_row.setContentsMargins(19, 15, 19, 15)
        eq_text = QVBoxLayout()
        eq_text.addWidget(label('Equalizer', 'cardtitle'))
        eq_text.addWidget(label('Klangvoreinstellung auswählen', 'muted'))
        eq_row.addLayout(eq_text, 1)
        self.eq_combo = QComboBox()
        self.eq_combo.setEnabled(False)
        self.eq_combo.currentTextChanged.connect(lambda value:
            self._effect_enum_changed('eq_preset', value))
        eq_row.addWidget(self.eq_combo)
        self.eq_check = QCheckBox()
        self.eq_check.setEnabled(False)
        self.eq_check.setAccessibleName('Equalizer aktivieren')
        self.eq_check.toggled.connect(lambda enabled: self._effect_toggle('equalizer', enabled))
        eq_row.addWidget(self.eq_check)
        body_layout.addWidget(equalizer)
        body_layout.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        self.effects_message = label('Effekte werden geladen …', 'muted', True)
        layout.addWidget(self.effects_message)
        return page

    def _apps_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        layout.addWidget(self._page_header('App-Lautstärken',
            'Passe laufende Wiedergabe-Apps einzeln an. Angezeigt werden Apps auf der Sound Blaster.'))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self.apps_layout = QVBoxLayout(body)
        self.apps_layout.setContentsMargins(0, 0, 8, 0)
        self.apps_layout.setSpacing(12)
        self.apps_empty = label('Gerade spielt keine App über die Sound Blaster.', 'muted', True)
        self.apps_layout.addWidget(self.apps_empty)
        self.apps_layout.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        self.apps_message = label('Aktualisiert sich automatisch, während diese Seite geöffnet ist.', 'muted')
        layout.addWidget(self.apps_message)
        return page

    def _device_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(label('OUTPUTDECK', 'eyebrow'))
        layout.addSpacing(13)
        layout.addWidget(label('Gerät & Infos', 'title'))
        layout.addSpacing(6)
        layout.addWidget(label('Verbindung und Einstellungen deiner Soundkarte.', 'subtitle'))
        layout.addSpacing(14)
        panel = QFrame(objectName='panel')
        info = QVBoxLayout(panel)
        info.setContentsMargins(23, 14, 23, 14)
        info.setSpacing(6)
        info.addWidget(label('ERKANNTES GERÄT', 'section'))
        self.device_name = label('Suche Soundkarte …', 'device', True)
        info.addWidget(self.device_name)
        self.card_detail = label('ALSA-Karte –', 'muted')
        info.addWidget(self.card_detail)
        self.default_detail = label('Standardausgabe wird geprüft …', 'muted', True)
        info.addWidget(self.default_detail)
        info.addSpacing(1)
        self.default_button = button('Als Standardausgabe festlegen', 'primary')
        self.default_button.setEnabled(False)
        self.default_button.clicked.connect(lambda: self._action('default', self.controller.set_default))
        info.addWidget(self.default_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(panel)
        layout.addSpacing(8)
        prefs = QFrame(objectName='panel')
        p = QVBoxLayout(prefs)
        p.setContentsMargins(23, 14, 23, 14)
        p.setSpacing(6)
        p.addWidget(label('BEDIENUNG', 'section'))
        self.shortcut_header = label('Tastenkürzel', 'cardtitle')
        p.addWidget(self.shortcut_header)
        self.shortcut_detail = label('Dein KDE-Shortcut schaltet den Ausgang um und zeigt den neuen Zustand als Benachrichtigung.', 'muted', True)
        p.addWidget(self.shortcut_detail)
        self.shortcut_input_label = label('Tastenkombination auswählen:', 'muted')
        p.addWidget(self.shortcut_input_label)
        self.shortcut_recorder = QKeySequenceEdit()
        self.shortcut_recorder.setMaximumSequenceLength(1)
        self.shortcut_recorder.setMinimumSize(210, 36)
        self.shortcut_recorder.setAccessibleName(self._t('Tastenkombination auswählen:'))
        self.shortcut_recorder.findChild(QLineEdit).setPlaceholderText(self._t('Tastenkombination drücken'))
        self.shortcut_button = button('Tastenkürzel einrichten')
        self.shortcut_button.setMinimumHeight(36)
        self.shortcut_button.clicked.connect(self._shortcut_action)
        shortcut_row = QHBoxLayout()
        shortcut_row.setSpacing(10)
        shortcut_row.addWidget(self.shortcut_recorder)
        shortcut_row.addWidget(self.shortcut_button)
        shortcut_row.addStretch()
        p.addLayout(shortcut_row)
        self.shortcut_feedback = label('', 'muted', True)
        self.shortcut_feedback.hide()
        p.addWidget(self.shortcut_feedback)
        self.shortcut_setup_hint = label('Suche in KDE nach deinem bestehenden Tastenkürzel und ändere dort die Tastenkombination.', 'muted', True)
        self.shortcut_setup_hint.hide()
        p.addWidget(self.shortcut_setup_hint)
        p.addSpacing(1)
        self.tray_checkbox = QCheckBox('Beim Schließen im Infobereich weiterlaufen')
        self.tray_checkbox.setProperty('source_text', 'Beim Schließen im Infobereich weiterlaufen')
        self.tray_checkbox.setChecked(self.settings.value('close_to_tray', True, type=bool))
        self.tray_checkbox.toggled.connect(lambda value: self.settings.setValue('close_to_tray', value))
        p.addWidget(self.tray_checkbox)
        p.addWidget(label('Ein Klick auf das Symbol öffnet die App erneut.', 'muted'))
        layout.addWidget(prefs)
        layout.addSpacing(8)
        language_panel = QFrame(objectName='panel')
        language_row = QHBoxLayout(language_panel)
        language_row.setContentsMargins(23, 12, 23, 12)
        language_text = QVBoxLayout()
        language_text.addWidget(label('OBERFLÄCHE', 'section'))
        language_text.addWidget(label('Wähle die Sprache der App und der Benachrichtigungen.', 'muted', True))
        language_row.addLayout(language_text, 1)
        self.language_combo = QComboBox()
        self.language_combo.addItem('Deutsch', 'de')
        self.language_combo.addItem('English', 'en')
        self.language_combo.setCurrentIndex(0 if self.language == 'de' else 1)
        self.language_combo.currentIndexChanged.connect(self._language_changed)
        language_row.addWidget(self.language_combo)
        layout.addWidget(language_panel)
        layout.addStretch()
        system_button = button('System-Audioeinstellungen öffnen')
        system_button.clicked.connect(self._open_system_settings)
        layout.addWidget(system_button, 0, Qt.AlignmentFlag.AlignLeft)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _page(self, index):
        self.pages.setCurrentIndex(index)
        for number, nav in enumerate(self.nav_buttons):
            nav.setProperty('active', number == index)
            nav.style().unpolish(nav)
            nav.style().polish(nav)
        if index == 1:
            self._render_profiles()
        if hasattr(self, 'refresh_timer'):
            self.refresh()

    def _shortcut_name(self):
        run_script = Path(__file__).resolve().parent.parent / 'run.sh'
        binding = configured_shortcut(run_script)
        if not binding:
            return None
        name = binding.replace('+', ' + ')
        return name.replace('Ctrl', 'Strg') if self.language == 'de' else name

    def _render_shortcut(self):
        name = self._shortcut_name()
        self.shortcut_tip_frame.setVisible(bool(name))
        self.shortcut_input_label.setVisible(not name)
        self.shortcut_recorder.setVisible(not name)
        if name:
            self.shortcut_tip.setText(self._t('Schnell wechseln mit deinem KDE-Tastenkürzel') + f': {name}')
            self.shortcut_header.setText((f'Tastenkürzel: {name}' if self.language == 'de'
                                          else f'Shortcut: {name}'))
            self.shortcut_detail.setText(self._t(
                'Dein KDE-Shortcut schaltet den Ausgang um und zeigt den neuen Zustand als Benachrichtigung.'))
            self.shortcut_button.setText(self._t('Tastenkürzel ändern'))
            self.shortcut_setup_hint.setText(self._t('Suche in KDE nach deinem bestehenden Tastenkürzel und ändere dort die Tastenkombination.'))
        else:
            self.shortcut_header.setText(self._t('Tastenkürzel nicht eingerichtet'))
            self.shortcut_detail.setText(self._t('Optional: Schalte Lautsprecher und Headset mit einer frei wählbaren Tastenkombination um.'))
            self.shortcut_button.setText(self._t('Tastenkürzel aktivieren'))
            self.shortcut_setup_hint.hide()

    def _shortcut_action(self):
        if self._shortcut_name():
            self._open_shortcut_settings()
            return
        sequence = self.shortcut_recorder.keySequence()
        if sequence.isEmpty():
            self.shortcut_feedback.setText(self._t('Wähle zuerst eine Tastenkombination aus.'))
            self.shortcut_feedback.show()
            return
        run_script = Path(__file__).resolve().parent.parent / 'run.sh'
        try:
            activate_shortcut(run_script, sequence[0].toCombined())
        except ShortcutConflict:
            self.shortcut_feedback.setText(self._t('Diese Tastenkombination ist bereits belegt. Wähle eine andere.'))
            self.shortcut_feedback.show()
            return
        except (ShortcutError, OSError):
            self.shortcut_feedback.setText(self._t('Tastenkürzel konnte nicht eingerichtet werden. KDE Plasma muss laufen.'))
            self.shortcut_feedback.show()
            return
        self.shortcut_feedback.setText(self._t('Tastenkürzel aktiviert.'))
        self.shortcut_feedback.show()
        self._render_shortcut()

    def _open_shortcut_settings(self):
        if not shutil.which('kcmshell6'):
            self.shortcut_detail.setText(self._t('Die Tastenkürzel-Einstellungen von KDE Plasma sind hier nicht verfügbar.'))
            return
        try:
            subprocess.Popen(['kcmshell6', 'kcm_keys'], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except OSError:
            self.shortcut_detail.setText(self._t('Die Tastenkürzel-Einstellungen von KDE Plasma konnten nicht geöffnet werden.'))
            return
        self.shortcut_setup_hint.show()

    def _language_changed(self, index):
        language = self.language_combo.itemData(index)
        if language not in ('de', 'en') or language == self.language:
            return
        self.language = language
        self.settings.setValue('language', language)
        self.settings.sync()
        self._apply_language()

    def _apply_language(self):
        for widget in self.findChildren(QWidget):
            source = widget.property('source_text')
            if source is not None and hasattr(widget, 'setText'):
                widget.setText(self._t(source))
        self.open_action.setText(self._t('OutputDeck öffnen'))
        self.speakers_action.setText(self._t('Lautsprecher'))
        self.headphones_action.setText(self._t('Headset'))
        self.quit_action.setText(self._t('Beenden'))
        self.speakers.setAccessibleName(self._t('Lautsprecher') +
                                        (' auswählen' if self.language == 'de' else ' selected output'))
        self.headphones.setAccessibleName(self._t('Headset') +
                                          (' auswählen' if self.language == 'de' else ' selected output'))
        self.outfx_check.setAccessibleName(self._t('Ausgangseffekte aktivieren'))
        self.eq_check.setAccessibleName(self._t('Equalizer aktivieren'))
        self.shortcut_recorder.setAccessibleName(self._t('Tastenkombination auswählen:'))
        self.shortcut_recorder.findChild(QLineEdit).setPlaceholderText(self._t('Tastenkombination drücken'))
        for key, (toggle, _, _) in self.effect_widgets.items():
            title = {'surround': 'Surround', 'crystalizer': 'Crystalizer',
                     'xbass': 'X-Bass', 'dialog': 'Dialog Plus',
                     'smart_volume': 'Smart Volume'}[key]
            toggle.setAccessibleName(self._t(title) +
                                     (' aktivieren' if self.language == 'de' else ' enable'))
        self._render_shortcut()
        self._render_connection_state()
        self._render_profiles()
        if self.current:
            self._render(self.current)
        if self.latest_effects:
            self._render_effects(self.latest_effects)
        if self.latest_apps is not None:
            self._render_apps(self.latest_apps)
        self._set_message('Bereit')

    def _tray(self):
        self.tray = QSystemTrayIcon(QIcon(str(ICON)), self)
        menu = QMenu()
        self.open_action = QAction('OutputDeck öffnen', self)
        self.open_action.triggered.connect(self.show_and_raise)
        menu.addAction(self.open_action)
        menu.addSeparator()
        self.speakers_action = menu.addAction('Lautsprecher', lambda: self._action('speakers', lambda: self.controller.select_output('speakers')))
        self.headphones_action = menu.addAction('Headset', lambda: self._action('headphones', lambda: self.controller.select_output('headphones')))
        menu.addSeparator()
        self.quit_action = QAction('Beenden', self)
        self.quit_action.triggered.connect(self._quit)
        menu.addAction(self.quit_action)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip('OutputDeck')
        self.tray.activated.connect(lambda reason: self.show_and_raise() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def _submit(self, kind, func):
        if self.busy:
            return
        self.busy = True
        self.job_kind = kind
        if kind != 'refresh':
            self._set_message('Änderung wird übernommen …')
            if kind not in ('volume', 'effects_refresh', 'effects_level',
                            'apps_refresh', 'app_volume', 'app_mute', 'effects_action'):
                self._set_controls(False)
        if kind in ('effects_refresh', 'effects_action'):
            self._set_effect_controls(False)
        elif kind == 'effects_level':
            self._set_effect_switches(False)
        if kind.startswith('app'):
            self._set_app_mute_buttons(False)
        if kind.startswith('profile'):
            for _, save, apply in self.profile_cards.values():
                save.setEnabled(False)
                apply.setEnabled(False)

        def work():
            try:
                result = func()
                if kind in ('effects_action', 'effects_level'):
                    result = self.controller.effects_snapshot()
                elif kind in ('app_volume', 'app_mute'):
                    result = self.controller.app_streams()
                elif kind not in ('refresh', 'effects_refresh', 'apps_refresh'):
                    result = self.controller.snapshot()
                self.bridge.finished.emit(result, None)
            except Exception as exc:
                self.bridge.finished.emit(None, exc)

        self.executor.submit(work)

    def _action(self, kind, func):
        if self.busy:
            return
        self.volume_timer.stop()
        self.volume_pending = False
        self._submit(kind, func)

    def refresh(self):
        self._render_shortcut()
        if self.busy:
            return
        page = self.pages.currentIndex()
        if page == 2:
            if not self.effect_pending and not any(w[1].isSliderDown() for w in self.effect_widgets.values()):
                self._submit('effects_refresh', self.controller.effects_snapshot)
        elif page == 3:
            if not self.app_pending and not any(r['slider'].isSliderDown() for r in self.app_rows.values()):
                self._submit('apps_refresh', self.controller.app_streams)
        elif not self.volume_pending and not self.slider.isSliderDown():
            self._submit('refresh', self.controller.snapshot)
            if page == 1:
                self._render_profiles()

    def _job_finished(self, state, error):
        kind = self.job_kind
        self.busy = False
        if error is not None:
            self._set_message(str(error), True)
            if kind == 'refresh':
                self.current = None
                self.connection_error = ('Soundkarte nicht gefunden' if str(error).startswith(
                    ('Keine ALSA-Soundkarten gefunden.', 'Keine Sound-Blaster-Soundkarte gefunden.'))
                    else 'Soundkarte nicht verfügbar')
                self._render_connection_state()
                self.output_status.setText(self._t('Karte nicht verfügbar'))
                self._set_controls(False)
            elif self.current:
                self._set_controls(True)
            if kind.startswith('effects'):
                self.effects_message.setText(self._t(str(error)))
                self.effects_message.setStyleSheet('color: #f5a18a;')
                self._set_effect_controls(True)
            if kind.startswith('app'):
                self.apps_message.setText(self._t(str(error)))
                self.apps_message.setStyleSheet('color: #f5a18a;')
                self._set_app_mute_buttons(True)
            if kind.startswith('profile'):
                self.profile_message.setText(self._t(str(error)))
                self.profile_message.setStyleSheet('color: #f5a18a;')
                self._render_profiles()
            self._schedule_pending()
            return
        if kind.startswith('effects'):
            self._render_effects(state)
            if kind != 'effects_refresh' and state['controls']['outfx']['enabled']:
                self.effects_message.setText(self._t('Änderung übernommen'))
            self.effects_message.setStyleSheet('color: #a2a6ae;')
            self._schedule_pending()
            return
        if kind.startswith('app'):
            self._render_apps(state)
            self.apps_message.setText(self._t('App-Lautstärken werden automatisch aktualisiert.'))
            self.apps_message.setStyleSheet('color: #a2a6ae;')
            self._schedule_pending()
            return
        self.current = state
        self._render(state)
        if kind in ('profile_save', 'profile_apply'):
            self._render_profiles()
            message = ('Profil „{profile}“ gespeichert.' if kind == 'profile_save'
                       else 'Profil „{profile}“ aktiviert.')
            self.profile_message.setText(self._t(message, profile=self._t(self.profile_name)))
            self.profile_message.setStyleSheet('color: #9bd9b2;')
        if kind != 'refresh':
            self._set_message('Änderung übernommen')
        elif self.message.text() not in ('Bereit', 'Änderung übernommen'):
            self._set_message('Bereit')
        self._schedule_pending()

    def _schedule_pending(self):
        if self.volume_pending and not self.volume_timer.isActive():
            self.volume_timer.start(80)
        if self.effect_pending and not self.effect_timer.isActive():
            self.effect_timer.start(80)
        if self.app_pending and not self.app_timer.isActive():
            self.app_timer.start(80)

    def _render_profiles(self):
        try:
            profiles = self.controller.profiles()
        except AttributeError:
            profiles = {}  # Minimal controllers used by the interface test.
        except Exception as exc:
            self._set_message(str(exc), True)
            return
        for name, (summary, save, apply) in self.profile_cards.items():
            save.setEnabled(True)
            profile = profiles.get(name)
            if profile:
                output = self._t('Headset' if profile['output'] == 'headphones' else 'Lautsprecher')
                level = f" · {profile['volume']} %" if profile.get('volume') is not None else ''
                summary.setText(f'{output}{level} · EQ: {profile.get("eq_preset", "Flat")}')
                apply.setEnabled(True)
            else:
                summary.setText(self._t('Noch nicht gespeichert'))
                apply.setEnabled(False)

    def _profile_action(self, kind, name):
        if self.busy:
            return
        self.profile_name = name
        if kind == 'profile_save':
            action = lambda: self.controller.save_profile(name)
        else:
            action = lambda: self.controller.apply_profile(name)
        self._action(kind, action)

    def _set_effect_switches(self, enabled):
        for widget in (self.outfx_check, self.eq_check, self.eq_combo, self.smart_combo):
            widget.setEnabled(enabled)
        for toggle, _, _ in self.effect_widgets.values():
            toggle.setEnabled(enabled)

    def _set_effect_controls(self, enabled):
        self.outfx_check.setEnabled(enabled)
        self.eq_check.setEnabled(enabled)
        self.eq_combo.setEnabled(enabled)
        self.smart_combo.setEnabled(enabled)
        for toggle, slider, _ in self.effect_widgets.values():
            toggle.setEnabled(enabled)
            # Keep the held slider interactive during ongoing level writes.
            if not slider.isSliderDown():
                slider.setEnabled(enabled)

    def _render_effects(self, effects):
        for key, (toggle, slider, value) in self.effect_widgets.items():
            control = effects['controls'][key]
            toggle.blockSignals(True)
            toggle.setChecked(control['enabled'])
            toggle.blockSignals(False)
            if key not in self.effect_pending and not slider.isSliderDown():
                slider.blockSignals(True)
                slider.setValue(control['level'] or 0)
                slider.blockSignals(False)
                value.setText(f"{control['level']} %" if control['level'] is not None else '– %')
        for key, widget in (('outfx', self.outfx_check), ('equalizer', self.eq_check)):
            widget.blockSignals(True)
            widget.setChecked(effects['controls'][key]['enabled'])
            widget.blockSignals(False)
        for widget, choices, current in (
            (self.eq_combo, effects['eq_presets'], effects['eq_preset']),
            (self.smart_combo, effects['smart_modes'], effects['smart_mode']),
        ):
            widget.blockSignals(True)
            widget.clear()
            widget.addItems(choices)
            widget.setCurrentText(current)
            widget.blockSignals(False)
        self._set_effect_controls(True)
        self.latest_effects = effects
        self.effects_message.setText(self._t('Effekte sind ausgeschaltet. Aktiviere den Hauptschalter oben.'
                                              if not effects['controls']['outfx']['enabled']
                                              else 'Effekte der Sound Blaster Z'))

    def _effect_toggle(self, key, enabled):
        if self.busy:
            return
        self._submit('effects_action', lambda: self.controller.set_effect_enabled(key, enabled))

    def _effect_enum_changed(self, key, value):
        if self.busy or not value:
            return
        if key == 'eq_preset':
            action = lambda: self.controller.set_eq_preset(value)
        else:
            action = lambda: self.controller.set_smart_mode(value)
        self._submit('effects_action', action)

    def _effect_level_changed(self, key, level, value_label):
        value_label.setText(f'{level} %')
        self.effect_pending[key] = level
        if not self.effect_timer.isActive():
            self.effect_timer.start(95)

    def _commit_effect(self):
        if self.busy:
            self.effect_timer.start(80)
            return
        key, level = next(iter(self.effect_pending.items()))
        del self.effect_pending[key]
        self._submit('effects_level', lambda: self.controller.set_effect_level(key, level))

    def _app_row(self, stream):
        index = stream['index']
        card = QFrame(objectName='panel')
        layout = QVBoxLayout(card)
        layout.setContentsMargins(19, 14, 19, 15)
        layout.setSpacing(9)
        head = QHBoxLayout()
        title = label(stream['name'], 'cardtitle')
        head.addWidget(title)
        head.addStretch()
        mute = button(self._t('Stumm' if not stream['muted'] else 'Ton an'))
        mute.clicked.connect(lambda: self._submit('app_mute',
            lambda: self.controller.toggle_app_mute(index)))
        head.addWidget(mute)
        layout.addLayout(head)
        detail = label(stream['detail'], 'muted')
        layout.addWidget(detail)
        volume_row = QHBoxLayout()
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        amount = label(f"{stream['volume']} %", 'muted')
        slider.valueChanged.connect(lambda level: self._app_volume_changed(index, level, amount))
        volume_row.addWidget(slider, 1)
        volume_row.addWidget(amount)
        layout.addLayout(volume_row)
        self.app_rows[index] = {'card': card, 'title': title, 'detail': detail,
                                'mute': mute, 'slider': slider, 'amount': amount}
        return card

    def _set_app_mute_buttons(self, enabled):
        for row in self.app_rows.values():
            row['mute'].setEnabled(enabled)

    def _render_apps(self, streams):
        self.latest_apps = streams
        present = {item['index'] for item in streams}
        for index in list(self.app_rows):
            if index not in present and index not in self.app_pending:
                row = self.app_rows.pop(index)
                self.apps_layout.removeWidget(row['card'])
                row['card'].deleteLater()
        for stream in streams:
            index = stream['index']
            if index not in self.app_rows:
                self.apps_layout.insertWidget(self.apps_layout.count() - 1,
                                              self._app_row(stream))
            row = self.app_rows[index]
            row['title'].setText(stream['name'])
            row['detail'].setText(stream['detail'] + (self._t(' · Stummgeschaltet') if stream['muted'] else ''))
            row['mute'].setText(self._t('Ton an' if stream['muted'] else 'Stumm'))
            row['mute'].setEnabled(True)
            if index not in self.app_pending and not row['slider'].isSliderDown():
                row['slider'].blockSignals(True)
                row['slider'].setValue(stream['volume'])
                row['slider'].blockSignals(False)
                row['amount'].setText(f"{stream['volume']} %")
        self.apps_empty.setVisible(not streams)

    def _app_volume_changed(self, index, level, amount):
        amount.setText(f'{level} %')
        self.app_pending[index] = level
        if not self.app_timer.isActive():
            self.app_timer.start(95)

    def _commit_app_volume(self):
        if self.busy:
            self.app_timer.start(80)
            return
        index, level = next(iter(self.app_pending.items()))
        del self.app_pending[index]
        self._submit('app_volume', lambda: self.controller.set_app_volume(index, level))

    def _render_connection_state(self):
        if self.connection_error:
            self.side_device.hide()
            self.side_connection.setText(self._t(self.connection_error))
            self.side_connection.setStyleSheet('color: #f08080; font-weight: 700;')
            self.side_connection.show()
        else:
            self.side_connection.hide()
            self.side_device.show()

    def _render(self, state):
        self.speakers.set_active(state.output == 'speakers')
        self.headphones.set_active(state.output == 'headphones')
        active = self._t('Headset' if state.output == 'headphones' else 'Lautsprecher')
        self.output_status.setText(self._t('●  {output} aktiv', output=active))
        self.connection_error = None
        self._render_connection_state()
        self.side_device.setText(state.device)
        self.device_name.setText(state.device)
        self.card_detail.setText(self._t('ALSA-Karte {card}  ·  Hardware-Ausgang: {output}',
                                         card=state.card, output=active))
        self.default_detail.setText(self._t('Diese Soundkarte ist die Standardausgabe.' if state.is_default
                                             else 'Diese Soundkarte ist nicht die Standardausgabe.'))
        if not self.volume_pending and not self.slider.isSliderDown():
            self.slider.blockSignals(True)
            self.slider.setValue(min(100, state.volume or 0))
            self.slider.blockSignals(False)
            self.volume_value.setText(f'{state.volume} %' if state.volume is not None else '– %')
        self.mute_button.setText(self._t('Ton einschalten' if state.muted else 'Ton ausschalten'))
        try:
            remembered = self.controller.route_volumes()
        except AttributeError:
            remembered = {}
        for output, choice in (('speakers', self.speakers), ('headphones', self.headphones)):
            if output == state.output and state.volume is not None:
                choice.description.setText(self._t('Aktuell {volume} %', volume=state.volume))
            elif output in remembered:
                choice.description.setText(self._t('Zuletzt {volume} %', volume=remembered[output]))
            else:
                choice.description.setText(self._t('Sound über deine Boxen' if output == 'speakers'
                                                    else 'Sound über deine Kopfhörer'))
        self.mute_status.setText(self._t('●  STUMMGESCHALTET · Kein Ton zu hören' if state.muted
                                          else '●  Ton ist eingeschaltet'))
        self.mute_status.setStyleSheet('color: #ffa681; font-weight: 700;' if state.muted
                                       else 'color: #9bd9b2;')
        for widget in (self.mute_button, self.volume_panel):
            widget.setProperty('muted', state.muted)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.tray.setToolTip(self._t('Sound Blaster · {output}', output=active))
        self._set_controls(True)

    def _set_controls(self, enabled):
        self.speakers.setEnabled(enabled)
        self.headphones.setEnabled(enabled)
        has_sink = enabled and self.current is not None and bool(self.current.sink)
        self.slider.setEnabled(has_sink)
        self.mute_button.setEnabled(has_sink)
        self.default_button.setEnabled(has_sink and not self.current.is_default)

    def _volume_changed(self, value):
        self.volume_value.setText(f'{value} %')
        self.volume_pending = True
        # Throttle writes while dragging, without waiting for slider release.
        if not self.volume_timer.isActive():
            self.volume_timer.start(80)

    def _commit_volume(self):
        if self.busy:
            self.volume_timer.start(80)
            return
        value = self.slider.value()
        self.volume_pending = False
        self._submit('volume', lambda: self.controller.set_volume(value))

    def _set_message(self, message, error=False):
        self.message.setText(self._t(message))
        self.message.setStyleSheet('color: #f5a18a;' if error else 'color: #9da2ab;')

    def _open_system_settings(self):
        try:
            subprocess.Popen(['kcmshell6', 'kcm_pulseaudio'], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except OSError as exc:
            self._set_message(f'Systemeinstellungen konnten nicht geöffnet werden: {exc}', True)
            self._page(0)

    def show_and_raise(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.refresh()

    def closeEvent(self, event):
        if not self.closing_for_real and self.tray.isVisible() and self.tray_checkbox.isChecked():
            event.ignore()
            self.hide()
            return
        self.executor.shutdown(wait=False, cancel_futures=True)
        event.accept()

    def _quit(self):
        self.closing_for_real = True
        self.tray.hide()
        QApplication.instance().quit()


def launch(controller, screenshot=None):
    app = QApplication(sys.argv)
    app.setApplicationName('OutputDeck')
    app.setOrganizationName('SoundBlasterControl')
    app.setWindowIcon(QIcon(str(ICON)))
    window = MainWindow(controller)
    window.show()
    if screenshot:
        def capture():
            window.grab().save(screenshot)
            window._quit()
        QTimer.singleShot(1700, capture)
    return app.exec()
