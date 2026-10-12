"""Render the English README screenshot without touching audio hardware."""

import os
from pathlib import Path
import sys
import tempfile

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
CONFIG = tempfile.TemporaryDirectory()
os.environ['XDG_CONFIG_HOME'] = CONFIG.name
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from soundblaster.audio import State
from soundblaster.ui import MainWindow


class DemoAudio:
    def snapshot(self):
        return State('0', 'Creative Sound Blaster Z', 'speakers', 'demo-sink',
                     42, False, True)

    def route_volumes(self):
        return {'speakers': 42, 'headphones': 25}

    def profiles(self):
        return {}


def main():
    app = QApplication([])
    window = MainWindow(DemoAudio())
    window._shortcut_name = lambda: None
    window.language_combo.setCurrentIndex(1)
    window.show()
    docs = ROOT / 'docs'
    docs.mkdir(exist_ok=True)

    def capture():
        window.grab().save(str(docs / 'screenshot-en.png'))
        window._quit()

    QTimer.singleShot(700, capture)
    app.exec()
    CONFIG.cleanup()


if __name__ == '__main__':
    main()
