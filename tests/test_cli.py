import unittest
from unittest.mock import patch

from soundblaster.__main__ import show_output_notification
from soundblaster.audio import State


class NotificationTest(unittest.TestCase):
    @patch('soundblaster.__main__.subprocess.run')
    @patch('soundblaster.__main__.saved_language', return_value='de')
    def test_shortcut_notification_names_new_output_and_volume(self, language, run):
        state = State('0', 'Sound Blaster Z', 'headphones', 'analog', 35, False, True)
        show_output_notification(state)
        args = run.call_args.args[0]
        self.assertEqual(args[0], 'notify-send')
        self.assertIn('Headset aktiv', args)
        self.assertIn('Lautstärke: 35 %', args)

    @patch('soundblaster.__main__.subprocess.run')
    @patch('soundblaster.__main__.saved_language', return_value='en')
    def test_shortcut_notification_uses_selected_english(self, language, run):
        state = State('0', 'Sound Blaster Z', 'speakers', 'analog', 42, False, True)
        show_output_notification(state)
        args = run.call_args.args[0]
        self.assertIn('Speakers active', args)
        self.assertIn('Volume: 42 %', args)


if __name__ == '__main__':
    unittest.main()
