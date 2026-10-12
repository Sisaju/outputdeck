import os
import tempfile
import time
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QLineEdit
from PySide6.QtGui import QKeySequence

from soundblaster.audio import AudioError, State
from soundblaster.i18n import saved_language, translate
from soundblaster.ui import MainWindow
from unittest.mock import patch


class FakeController:
    def __init__(self):
        self.volume = 50
        self.muted = False
        self.volume_calls = []

    def snapshot(self):
        return State('0', 'Creative Sound Blaster Z', 'speakers', 'creative-analog',
                     self.volume, self.muted, True)

    def set_volume(self, volume):
        self.volume_calls.append(volume)
        self.volume = volume

    def toggle_mute(self):
        self.muted = not self.muted


class FakeFeatures(FakeController):
    def __init__(self):
        super().__init__()
        self.effect_level = 50
        self.effect_calls = []
        self.app_volume = 45
        self.app_calls = []

    def profiles(self):
        return {}

    def effects_snapshot(self):
        return {
            'controls': {key: {'enabled': True,
                               'level': self.effect_level if key not in ('equalizer', 'outfx') else None}
                         for key in ('surround', 'crystalizer', 'xbass', 'dialog',
                                     'smart_volume', 'equalizer', 'outfx')},
            'eq_preset': 'Flat', 'eq_presets': ['Flat', 'Rock'],
            'smart_mode': 'Normal', 'smart_modes': ['Normal', 'Night'],
        }

    def set_effect_level(self, key, level):
        self.effect_calls.append((key, level))
        self.effect_level = level

    def app_streams(self):
        return [{'index': 7, 'name': 'Browser', 'detail': 'Video',
                 'volume': self.app_volume, 'muted': False}]

    def set_app_volume(self, index, level):
        self.app_calls.append((index, level))
        self.app_volume = level


class InterfaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_config_home = os.environ.get('XDG_CONFIG_HOME')
        cls.original_data_home = os.environ.get('XDG_DATA_HOME')
        cls.config_home = tempfile.TemporaryDirectory()
        cls.data_home = tempfile.TemporaryDirectory()
        os.environ['XDG_CONFIG_HOME'] = cls.config_home.name
        os.environ['XDG_DATA_HOME'] = cls.data_home.name
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls):
        if cls.original_config_home is None:
            os.environ.pop('XDG_CONFIG_HOME', None)
        else:
            os.environ['XDG_CONFIG_HOME'] = cls.original_config_home
        if cls.original_data_home is None:
            os.environ.pop('XDG_DATA_HOME', None)
        else:
            os.environ['XDG_DATA_HOME'] = cls.original_data_home
        cls.config_home.cleanup()
        cls.data_home.cleanup()

    def wait_until(self, condition, timeout=1):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if condition():
                return
            time.sleep(0.01)
        self.fail('Die Oberfläche hat den Zustand nicht rechtzeitig aktualisiert.')

    def test_volume_changes_while_dragging_and_mute_is_explicit(self):
        fake = FakeController()
        window = MainWindow(fake)
        window.show()
        try:
            self.wait_until(lambda: not window.busy and window.current is not None)
            window.slider.setSliderDown(True)
            window.slider.setValue(63)
            self.wait_until(lambda: fake.volume_calls == [63])
            self.assertTrue(window.slider.isSliderDown())
            window.slider.setSliderDown(False)
            self.wait_until(lambda: not window.busy)
            window.mute_button.click()
            self.wait_until(lambda: not window.busy and window.current.muted)
            self.assertEqual(window.mute_status.text(), translate(
                '●  STUMMGESCHALTET · Kein Ton zu hören', window.language))
            self.assertEqual(window.mute_button.text(), translate('Ton einschalten', window.language))
            self.assertEqual(window.volume_value.text(), '63 %')
        finally:
            window.closing_for_real = True
            window.close()

    def test_effect_and_app_sliders_change_while_dragging(self):
        fake = FakeFeatures()
        window = MainWindow(fake)
        window.show()
        try:
            self.wait_until(lambda: not window.busy and window.current is not None)
            window._page(2)
            self.wait_until(lambda: not window.busy and window.effect_widgets['xbass'][1].isEnabled())
            effect_slider = window.effect_widgets['xbass'][1]
            effect_slider.setSliderDown(True)
            effect_slider.setValue(72)
            self.wait_until(lambda: ('xbass', 72) in fake.effect_calls)
            self.assertTrue(effect_slider.isSliderDown())
            effect_slider.setSliderDown(False)
            self.wait_until(lambda: not window.busy)
            window._page(3)
            self.wait_until(lambda: not window.busy and 7 in window.app_rows)
            app_slider = window.app_rows[7]['slider']
            app_slider.setSliderDown(True)
            app_slider.setValue(31)
            self.wait_until(lambda: (7, 31) in fake.app_calls)
            self.assertTrue(app_slider.isSliderDown())
        finally:
            window.closing_for_real = True
            window.close()

    def test_language_switch_updates_live_interface_and_is_saved(self):
        fake = FakeFeatures()
        window = MainWindow(fake)
        original = window.language
        window.show()
        try:
            self.wait_until(lambda: not window.busy and window.current is not None)
            window.language_combo.setCurrentIndex(1)
            self.app.processEvents()
            self.assertEqual(window.nav_output.text(), 'Audio output')
            self.assertEqual(window.shortcut_recorder.findChild(QLineEdit).placeholderText(),
                             'Press a key combination')
            self.assertEqual(window.speakers.badge.text(), 'ACTIVE')
            self.assertEqual(window.mute_button.text(), 'Mute audio')
            self.assertEqual(saved_language(), 'en')
            window._page(2)
            self.wait_until(lambda: not window.busy)
            self.assertEqual(window.effects_message.text(), 'Sound Blaster Z effects')
            window.language_combo.setCurrentIndex(0)
            self.assertEqual(window.nav_output.text(), 'Audio-Ausgabe')
            self.assertEqual(saved_language(), 'de')
        finally:
            window.language_combo.setCurrentIndex(0 if original == 'de' else 1)
            window.closing_for_real = True
            window.close()

    def test_optional_shortcut_is_hidden_until_configured(self):
        window = MainWindow(FakeController())
        window.show()
        try:
            self.assertTrue(window.shortcut_tip_frame.isHidden())
            window._page(4)
            self.assertEqual(window.shortcut_button.text(), translate('Tastenkürzel aktivieren', window.language))
            window.shortcut_recorder.setKeySequence(QKeySequence('Ctrl+Shift+F12'))
            with patch('soundblaster.ui.activate_shortcut') as activate:
                window.shortcut_button.click()
            activate.assert_called_once()
            self.assertEqual(activate.call_args.args[1], QKeySequence('Ctrl+Shift+F12')[0].toCombined())
            self.assertEqual(window.shortcut_feedback.text(), translate('Tastenkürzel aktiviert.', window.language))
        finally:
            window.closing_for_real = True
            window.close()

    def test_small_window_scrolls_without_crushing_output_controls(self):
        window = MainWindow(FakeController())
        window._shortcut_name = lambda: 'Ctrl + Alt + Q'
        window.resize(840, 620)
        window.show()
        try:
            window._render_shortcut()
            self.app.processEvents()
            scrollbar = window.pages.widget(0).verticalScrollBar()
            self.assertGreater(scrollbar.maximum(), 0)
            self.assertGreaterEqual(window.mute_button.height(), 30)
            self.assertGreaterEqual(window.volume_value.height(), 30)
            scrollbar.setValue(scrollbar.maximum())
            self.app.processEvents()
            self.assertTrue(window.shortcut_tip_frame.isVisible())
            window._page(1)
            self.app.processEvents()
            for _, save, apply in window.profile_cards.values():
                self.assertGreaterEqual(save.height(), 30)
                self.assertGreaterEqual(apply.height(), 30)
        finally:
            window.closing_for_real = True
            window.close()

    def test_sidebar_shows_red_error_only_when_card_is_missing(self):
        class UnpluggedController(FakeController):
            missing = True

            def snapshot(self):
                if self.missing:
                    raise AudioError('Keine Sound-Blaster-Soundkarte gefunden. Verbindung und Treiber prüfen.')
                return super().snapshot()

        fake = UnpluggedController()
        window = MainWindow(fake)
        window.show()
        try:
            self.wait_until(lambda: window.connection_error is not None)
            self.assertEqual(window.side_connection.text(), translate('Soundkarte nicht gefunden', window.language))
            self.assertTrue(window.side_connection.isVisible())
            self.assertTrue(window.side_device.isHidden())
            self.assertIn('#f08080', window.side_connection.styleSheet())
            fake.missing = False
            window.refresh()
            self.wait_until(lambda: window.current is not None)
            self.assertTrue(window.side_connection.isHidden())
            self.assertTrue(window.side_device.isVisible())
        finally:
            window.closing_for_real = True
            window.close()


if __name__ == '__main__':
    unittest.main()
