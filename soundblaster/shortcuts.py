"""Manage KDE command shortcuts for OutputDeck."""

import os
from pathlib import Path
import re
import shlex
import subprocess

from PySide6.QtGui import QKeySequence


SERVICE = 'net.local.soundblaster-control.toggle.desktop'
DBUS_SERVICE = 'org.kde.kglobalaccel'
DBUS_PATH = '/kglobalaccel'
DBUS_INTERFACE = 'org.kde.KGlobalAccel'


class ShortcutError(Exception):
    """KDE could not register the requested shortcut."""


class ShortcutConflict(ShortcutError):
    """The key combination is already taken by another action."""


def _runs_toggle(desktop, command):
    try:
        contents = desktop.read_text()
    except OSError:
        return False
    execution = re.search(r'^Exec=(.+)$', contents, re.M)
    if not execution:
        return False
    try:
        return shlex.split(execution.group(1)) == command
    except ValueError:
        return False


def _bus_call(method, signature, *arguments):
    command = ['busctl', '--user', 'call', DBUS_SERVICE, DBUS_PATH,
               DBUS_INTERFACE, method, signature, *map(str, arguments)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ShortcutError('KDE global shortcuts are unavailable') from exc
    if result.returncode:
        raise ShortcutError(result.stderr.strip() or 'KDE rejected the shortcut')
    return result.stdout.strip()


def _toggle_exec(run_script):
    escaped = str(Path(run_script).resolve())
    for character in ('\\', '"', '`', '$'):
        escaped = escaped.replace(character, '\\' + character)
    escaped = escaped.replace('%', '%%')
    return f'Exec="{escaped}" --toggle --notify'


def _saved_managed_key():
    config_home = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    try:
        config = (config_home / 'kglobalshortcutsrc').read_text()
    except OSError:
        return None
    section = re.search(r'^\[services\]\[' + re.escape(SERVICE) + r'\]\s*$', config, re.M)
    if not section:
        return None
    end = config.find('\n[', section.end())
    contents = config[section.end():end if end >= 0 else None]
    binding = re.search(r'^_launch=([^,\n]+)', contents, re.M)
    if not binding or binding.group(1).strip().lower() == 'none':
        return None
    key = QKeySequence(binding.group(1).strip())
    return key[0].toCombined() if key.count() else None


def migrate_managed_shortcut(run_script):
    """Rename and retarget our KDE action without changing its key binding."""
    data_home = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    desktop = data_home / 'kglobalaccel' / SERVICE
    key_code = _saved_managed_key()
    if not desktop.exists() and not key_code:
        return
    desktop.parent.mkdir(parents=True, exist_ok=True)
    contents = desktop.read_text() if desktop.exists() else (
        '[Desktop Entry]\nType=Application\n'
        'Name=OutputDeck - Switch output\n'
        'Name[de]=OutputDeck - Ausgang wechseln\n'
        'Terminal=false\nStartupNotify=false\n'
        'X-KDE-GlobalAccel-CommandShortcut=true\n')
    updated = re.sub(r'^Exec=.*$', lambda _: _toggle_exec(run_script), contents, flags=re.M)
    if 'Exec=' not in contents:
        updated += _toggle_exec(run_script) + '\n'
    updated = re.sub(r'^Name=.*$', 'Name=OutputDeck - Switch output', updated, flags=re.M)
    updated = re.sub(r'^Name\[de\]=.*$', 'Name[de]=OutputDeck - Ausgang wechseln', updated, flags=re.M)
    if updated != contents:
        desktop.write_text(updated)
    if key_code:
        action = [SERVICE, '_launch', 'OutputDeck', 'Switch output']
        try:
            _bus_call('doRegister', 'as', 4, *action)
            result = _bus_call('setShortcut', 'asaiu', 4, *action, 1, key_code, 6)
            if result != f'ai 1 {key_code}':
                raise ShortcutError('KDE did not restore the key combination')
        except ShortcutError:
            return False
    return True


def activate_shortcut(run_script, key_code):
    """Install a KDE command action and bind one available key combination."""
    key_code = int(key_code)
    if key_code <= 0:
        raise ShortcutError('No key combination selected')
    available = _bus_call('isGlobalShortcutAvailable', 'is', key_code, SERVICE)
    if available != 'b true':
        raise ShortcutConflict('Key combination already in use')

    data_home = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    desktop = data_home / 'kglobalaccel' / SERVICE
    desktop.parent.mkdir(parents=True, exist_ok=True)
    contents = ('[Desktop Entry]\nType=Application\n'
                'Name=OutputDeck - Switch output\n'
                'Name[de]=OutputDeck - Ausgang wechseln\n'
                f'{_toggle_exec(run_script)}\n'
                'Terminal=false\nStartupNotify=false\n'
                'X-KDE-GlobalAccel-CommandShortcut=true\n')
    previous = desktop.read_bytes() if desktop.exists() else None
    desktop.write_text(contents)
    action = [SERVICE, '_launch', 'OutputDeck', 'Switch output']
    try:
        _bus_call('doRegister', 'as', 4, *action)
        result = _bus_call('setShortcut', 'asaiu', 4, *action, 1, key_code, 6)
        if result != f'ai 1 {key_code}':
            raise ShortcutError('KDE did not accept the key combination')
    except ShortcutError:
        try:
            _bus_call('setShortcut', 'asaiu', 4, *action, 0, 6)
        except ShortcutError:
            pass
        if previous is None:
            desktop.unlink(missing_ok=True)
        else:
            desktop.write_bytes(previous)
        raise
    return desktop


def configured_shortcut(run_script):
    config_home = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    try:
        config = (config_home / 'kglobalshortcutsrc').read_text()
    except OSError:
        config = ''

    data_homes = [Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))]
    data_homes.extend(Path(p) for p in os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share').split(':') if p)
    command = [str(Path(run_script).resolve()), '--toggle', '--notify']

    managed = data_homes[0] / 'kglobalaccel' / SERVICE
    # Our service ID stays the same when the checkout is moved or installed.
    if managed.exists():
        try:
            result = _bus_call('shortcut', 'as', 4, SERVICE, '_launch',
                               'OutputDeck', 'Switch output')
            code = re.fullmatch(r'ai 1 (\d+)', result)
            if code and int(code.group(1)) > 0:
                return QKeySequence(int(code.group(1))).toString(QKeySequence.SequenceFormat.PortableText)
        except ShortcutError:
            pass

    for match in re.finditer(r'^\[services\]\[([^\]]+\.desktop)\]\s*$', config, re.M):
        service = match.group(1)
        end = config.find('\n[', match.end())
        section = config[match.end():end if end >= 0 else None]
        binding = re.search(r'^_launch=([^,\n]+)', section, re.M)
        if not binding or binding.group(1).strip().lower() in ('none', ''):
            continue
        for home in data_homes:
            for folder in ('applications', 'kglobalaccel'):
                desktop = home / folder / service
                if (service == SERVICE and desktop == managed and desktop.exists()) or _runs_toggle(desktop, command):
                    return binding.group(1).strip()
    return None
