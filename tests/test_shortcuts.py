import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from soundblaster.shortcuts import (ShortcutConflict, activate_shortcut,
                                    configured_shortcut, migrate_managed_shortcut,
                                    SERVICE)


class ShortcutTest(unittest.TestCase):
    def test_existing_shortcut_survives_installation_from_another_folder(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict(os.environ, {'XDG_DATA_HOME': directory,
                                      'XDG_CONFIG_HOME': directory,
                                      'XDG_DATA_DIRS': directory}):
            root = Path(directory)
            desktop = root / 'kglobalaccel' / SERVICE
            desktop.parent.mkdir()
            desktop.write_text('[Desktop Entry]\nName=Sound Blaster Control\n'
                               'Exec="/old/download/run.sh" --toggle --notify\n')
            config = root / 'kglobalshortcutsrc'
            contents = f'[services][{SERVICE}]\n_launch=Ctrl+Alt+Q\n'
            config.write_text(contents)
            target = root / 'installed app' / 'run.sh'
            with patch('soundblaster.shortcuts._bus_call', return_value='ai 1 201326673'):
                self.assertEqual(configured_shortcut(target), 'Ctrl+Alt+Q')
            with patch('soundblaster.shortcuts._bus_call', return_value='ai 0'):
                self.assertEqual(configured_shortcut(target), 'Ctrl+Alt+Q')
            with patch('soundblaster.shortcuts._bus_call',
                       return_value='ai 1 201326673'):
                self.assertTrue(migrate_managed_shortcut(target))
            self.assertIn(f'Exec="{target}" --toggle --notify', desktop.read_text())
            self.assertIn('Name=OutputDeck - Switch output', desktop.read_text())
            self.assertEqual(config.read_text(), contents)

    def test_migration_restores_action_removed_by_kde_refresh(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict(os.environ, {'XDG_DATA_HOME': directory,
                                      'XDG_CONFIG_HOME': directory}):
            root = Path(directory)
            (root / 'kglobalshortcutsrc').write_text(
                f'[services][{SERVICE}]\n_launch=Ctrl+Alt+Q\n')
            target = root / 'installed' / 'run.sh'
            with patch('soundblaster.shortcuts._bus_call',
                       return_value='ai 1 201326673') as bus:
                self.assertTrue(migrate_managed_shortcut(target))
            desktop = root / 'kglobalaccel' / SERVICE
            self.assertIn('Name=OutputDeck - Switch output', desktop.read_text())
            self.assertIn(f'Exec="{target}" --toggle --notify', desktop.read_text())
            self.assertEqual(bus.call_args.args[0], 'setShortcut')
            self.assertIn(201326673, bus.call_args.args)

    def test_migration_does_not_create_a_shortcut_or_touch_other_actions(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict(os.environ, {'XDG_DATA_HOME': directory,
                                      'XDG_CONFIG_HOME': directory}):
            desktop = Path(directory) / 'kglobalaccel' / 'other.desktop'
            desktop.parent.mkdir()
            desktop.write_text('Exec=/bin/true\n')
            migrate_managed_shortcut('/installed/run.sh')
            self.assertFalse((desktop.parent / SERVICE).exists())
            self.assertEqual(desktop.read_text(), 'Exec=/bin/true\n')

    def test_activation_creates_a_kde_command_shortcut(self):
        run_script = Path(__file__).resolve().parent.parent / 'run.sh'
        key = 201326673
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict(os.environ, {'XDG_DATA_HOME': directory,
                                      'XDG_CONFIG_HOME': directory}):
            with patch('soundblaster.shortcuts._bus_call', side_effect=[
                'b true', '', f'ai 1 {key}']) as bus:
                desktop = activate_shortcut(run_script, key)
            self.assertTrue(desktop.exists())
            self.assertIn(f'Exec="{run_script}" --toggle --notify', desktop.read_text())
            self.assertEqual([call.args[0] for call in bus.call_args_list],
                             ['isGlobalShortcutAvailable', 'doRegister', 'setShortcut'])
            self.assertEqual(bus.call_args_list[-1].args[-2:], (key, 6))
            with patch('soundblaster.shortcuts._bus_call', return_value=f'ai 1 {key}'):
                self.assertEqual(configured_shortcut(run_script), 'Ctrl+Alt+Q')

    def test_conflict_does_not_create_a_shortcut(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict(os.environ, {'XDG_DATA_HOME': directory}), \
             patch('soundblaster.shortcuts._bus_call', return_value='b false'):
            with self.assertRaises(ShortcutConflict):
                activate_shortcut('/tmp/run.sh', 201326673)
            self.assertFalse((Path(directory) / 'kglobalaccel').exists())

    def test_only_a_bound_toggle_command_is_shown(self):
        run_script = Path(__file__).resolve().parent.parent / 'run.sh'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'config'
            apps = root / 'data' / 'applications'
            config.mkdir()
            apps.mkdir(parents=True)
            service = 'custom-toggle.desktop'
            (apps / service).write_text(
                '[Desktop Entry]\nType=Application\n'
                f'Exec="{run_script}" --toggle --notify\n')
            shortcuts = config / 'kglobalshortcutsrc'
            with patch.dict(os.environ, {'XDG_CONFIG_HOME': str(config),
                                      'XDG_DATA_HOME': str(root / 'data'),
                                      'XDG_DATA_DIRS': str(root / 'empty')}):
                self.assertIsNone(configured_shortcut(run_script))
                shortcuts.write_text(f'[services][{service}]\n_launch=none\n')
                self.assertIsNone(configured_shortcut(run_script))
                shortcuts.write_text(f'[services][{service}]\n_launch=Ctrl+Alt+Q\n')
                self.assertEqual(configured_shortcut(run_script), 'Ctrl+Alt+Q')
                (apps / service).write_text('[Desktop Entry]\nExec=/bin/true\n')
                self.assertIsNone(configured_shortcut(run_script))


if __name__ == '__main__':
    unittest.main()
