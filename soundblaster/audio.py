"""Hardware routing via ALSA; volume and mute via the card's PipeWire sink."""

from dataclasses import asdict, dataclass
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


class AudioError(RuntimeError):
    pass


@dataclass(frozen=True)
class State:
    card: str
    device: str
    output: str
    sink: str | None
    volume: int | None
    muted: bool
    is_default: bool

    def to_dict(self):
        return asdict(self)


class AudioController:
    EFFECTS = {
        'surround': 'FX: Surround',
        'crystalizer': 'FX: Crystalizer',
        'xbass': 'FX: X-Bass',
        'dialog': 'FX: Dialog Plus',
        'smart_volume': 'FX: Smart Volume',
        'equalizer': 'FX: Equalizer',
        'outfx': 'Enable OutFX',
    }
    PROFILES = ('Musik', 'Gaming', 'Nacht')

    def __init__(self, run=None, cards_path=Path('/proc/asound/cards'), state_path=None):
        self._run = run or self._command
        self.cards_path = cards_path
        config_root = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
        self.state_path = Path(state_path) if state_path else config_root / 'soundblaster-control/state.json'

    @staticmethod
    def _command(args):
        try:
            result = subprocess.run(
                args, capture_output=True, text=True, timeout=5,
                env={**os.environ, 'LC_ALL': 'C.UTF-8'},
            )
        except FileNotFoundError as exc:
            raise AudioError(f'{args[0]} fehlt. Bitte alsa-utils und pulseaudio-utils installieren.') from exc
        except subprocess.TimeoutExpired as exc:
            raise AudioError('Die Audiosteuerung antwortet nicht. Bitte erneut versuchen.') from exc
        if result.returncode:
            detail = result.stderr.strip() or result.stdout.strip()
            raise AudioError(f'{args[0]}: {detail or "Befehl fehlgeschlagen"}')
        return result.stdout

    def _card(self):
        try:
            cards = self.cards_path.read_text()
        except OSError as exc:
            raise AudioError('Keine ALSA-Soundkarten gefunden.') from exc
        for match in re.finditer(r'^\s*(\d+)\s+\[([^]]+)\]\s*:\s*(.+)$', cards, re.M):
            if re.search(r'creative|sound\s*blaster', match[2] + match[3], re.I):
                return match[1]
        raise AudioError('Keine Sound-Blaster-Soundkarte gefunden. Verbindung und Treiber prüfen.')

    def _output(self, card):
        text = self._run(['amixer', '-c', card, 'cget', 'name=Output Select'])
        match = re.search(r': values=(\d+)\s*$', text, re.M)
        if not match or match[1] not in ('0', '1'):
            raise AudioError('Diese Soundkarte unterstützt die Umschaltung über „Output Select“ nicht.')
        return 'headphones' if match[1] == '1' else 'speakers'

    def snapshot(self):
        card = self._card()
        output = self._output(card)
        # Routing remains usable when the audio server is stopped or the card
        # has no active playback profile.
        try:
            sinks = json.loads(self._run(['pactl', '-f', 'json', 'list', 'sinks']))
            sink = next((s for s in sinks if str(s.get('properties', {}).get('alsa.card')) == card
                         and 'iec958' not in s['name']), None)
        except (AudioError, ValueError, KeyError):
            sink = None
        if sink is None:
            return State(card, 'Sound Blaster', output, None, None, False, False)
        props = sink.get('properties', {})
        volumes = [v['value'] for v in sink.get('volume', {}).values()]
        volume = round(sum(volumes) / len(volumes) * 100 / 65536) if volumes else None
        try:
            default = self._run(['pactl', 'get-default-sink']).strip()
        except AudioError:
            default = ''
        return State(card, props.get('alsa.mixer_name', 'Sound Blaster'), output,
                     sink['name'], volume, bool(sink.get('mute')), default == sink['name'])

    def select_output(self, output):
        if output not in ('speakers', 'headphones'):
            raise ValueError('Ungültiger Ausgang')
        with self._state_lock():
            card = self._card()
            current = self._output(card)
            if current == output:
                return
            state = self.snapshot()
            data = self._load_state()
            levels = data.setdefault('route_volumes', {})
            if state.volume is not None:
                levels[current] = state.volume
            target = levels.get(output)
            if target is None and output == 'headphones' and state.volume is not None:
                target = min(state.volume, 35)
            self._run(['amixer', '-c', card, 'cset', 'name=Output Select',
                       '1' if output == 'headphones' else '0'])
            if self._output(card) != output:
                raise AudioError('Der Ausgang wurde nicht übernommen. Automatische Kopfhörer-Erkennung in ALSA prüfen.')
            if state.sink and target is not None:
                self._run(['pactl', 'set-sink-volume', state.sink, f'{target}%'])
                levels[output] = target
            self._save_state(data)

    def toggle(self):
        card = self._card()
        self.select_output('speakers' if self._output(card) == 'headphones' else 'headphones')

    def _sink(self):
        state = self.snapshot()
        if not state.sink:
            raise AudioError('Kein aktiver Sound-Blaster-Ausgang im Audioserver. Audio-Profil in den Systemeinstellungen prüfen.')
        return state.sink

    def set_volume(self, volume):
        if not isinstance(volume, int) or not 0 <= volume <= 100:
            raise ValueError('Lautstärke muss zwischen 0 und 100 liegen')
        with self._state_lock():
            state = self.snapshot()
            if not state.sink:
                raise AudioError('Kein aktiver Sound-Blaster-Ausgang im Audioserver.')
            self._run(['pactl', 'set-sink-volume', state.sink, f'{volume}%'])
            data = self._load_state()
            data.setdefault('route_volumes', {})[state.output] = volume
            self._save_state(data)

    def toggle_mute(self):
        self._run(['pactl', 'set-sink-mute', self._sink(), 'toggle'])

    def set_default(self):
        self._run(['pactl', 'set-default-sink', self._sink()])

    @contextmanager
    def _state_lock(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with (self.state_path.parent / '.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _load_state(self):
        try:
            return json.loads(self.state_path.read_text())
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            raise AudioError('Gespeicherte Klangprofile konnten nicht gelesen werden.') from exc

    def _save_state(self, data):
        with tempfile.NamedTemporaryFile('w', dir=self.state_path.parent,
                                         prefix='.state-', delete=False) as temp:
            json.dump(data, temp, ensure_ascii=False, indent=2)
            temp.write('\n')
            temp_path = Path(temp.name)
        os.replace(temp_path, self.state_path)

    def _control(self, name):
        return self._run(['amixer', '-c', self._card(), 'sget', name])

    @staticmethod
    def _switch(text):
        match = re.search(r'\[(on|off)\]', text)
        if not match:
            raise AudioError('Ein Sound-Blaster-Effekt konnte nicht gelesen werden.')
        return match[1] == 'on'

    @staticmethod
    def _enum(text):
        items = re.search(r'^\s*Items:\s*(.+)$', text, re.M)
        current = re.search(r"^\s*Item\d+:\s*'([^']+)'", text, re.M)
        if not items or not current:
            raise AudioError('Eine Sound-Blaster-Auswahl konnte nicht gelesen werden.')
        options = re.findall(r"'([^']+)'", items[1])
        if not options:
            raise AudioError('Eine Sound-Blaster-Auswahl konnte nicht gelesen werden.')
        return current[1], options

    def effects_snapshot(self):
        controls = {}
        for key, name in self.EFFECTS.items():
            text = self._control(name)
            level = re.search(r'\[(\d+)%\]', text)
            controls[key] = {'enabled': self._switch(text),
                             'level': int(level[1]) if level else None}
        eq, presets = self._enum(self._control('FX: Equalizer Preset'))
        smart, modes = self._enum(self._control('FX: Smart Volume Setting'))
        return {'controls': controls, 'eq_preset': eq, 'eq_presets': presets,
                'smart_mode': smart, 'smart_modes': modes}

    def set_effect_enabled(self, key, enabled):
        if key not in self.EFFECTS or not isinstance(enabled, bool):
            raise ValueError('Ungültiger Effekt')
        self._run(['amixer', '-c', self._card(), 'sset', self.EFFECTS[key],
                   'on' if enabled else 'off'])

    def set_effect_level(self, key, level):
        if key not in self.EFFECTS or key in ('equalizer', 'outfx'):
            raise ValueError('Ungültiger Effekt')
        if not isinstance(level, int) or not 0 <= level <= 100:
            raise ValueError('Effektstärke muss zwischen 0 und 100 liegen')
        self._run(['amixer', '-c', self._card(), 'sset', self.EFFECTS[key], f'{level}%'])

    def _set_enum(self, name, choice):
        _, choices = self._enum(self._control(name))
        if choice not in choices:
            raise ValueError('Ungültige Auswahl')
        self._run(['amixer', '-c', self._card(), 'sset', name, choice])

    def set_eq_preset(self, choice):
        self._set_enum('FX: Equalizer Preset', choice)

    def set_smart_mode(self, choice):
        self._set_enum('FX: Smart Volume Setting', choice)

    def profiles(self):
        return self._load_state().get('profiles', {})

    def route_volumes(self):
        return self._load_state().get('route_volumes', {})

    def save_profile(self, name):
        if name not in self.PROFILES:
            raise ValueError('Unbekanntes Klangprofil')
        state = self.snapshot()
        effects = self.effects_snapshot()
        with self._state_lock():
            data = self._load_state()
            data.setdefault('profiles', {})[name] = {
                'output': state.output, 'volume': state.volume,
                'effects': {k: {'enabled': v['enabled'], 'level': v['level']}
                            for k, v in effects['controls'].items()},
                'eq_preset': effects['eq_preset'],
                'smart_mode': effects['smart_mode'],
            }
            self._save_state(data)

    def apply_profile(self, name):
        if name not in self.PROFILES:
            raise ValueError('Unbekanntes Klangprofil')
        profile = self.profiles().get(name)
        if not profile:
            raise AudioError('Dieses Profil ist noch leer. Zuerst aktuellen Klang speichern.')
        self.select_output(profile['output'])
        for key, settings in profile['effects'].items():
            if key in self.EFFECTS:
                if settings.get('level') is not None and key not in ('equalizer', 'outfx'):
                    self.set_effect_level(key, settings['level'])
                self.set_effect_enabled(key, settings['enabled'])
        self.set_eq_preset(profile['eq_preset'])
        self.set_smart_mode(profile['smart_mode'])
        if profile.get('volume') is not None:
            self.set_volume(profile['volume'])

    def app_streams(self):
        state = self.snapshot()
        if not state.sink:
            return []
        sinks = json.loads(self._run(['pactl', '-f', 'json', 'list', 'sinks']))
        sink = next((s for s in sinks if s.get('name') == state.sink), None)
        if not sink:
            return []
        inputs = json.loads(self._run(['pactl', '-f', 'json', 'list', 'sink-inputs']))
        streams = []
        for item in inputs:
            if str(item.get('sink')) != str(sink['index']):
                continue
            props = item.get('properties', {})
            volumes = [v['value'] for v in item.get('volume', {}).values()]
            streams.append({
                'index': int(item['index']),
                'name': props.get('application.name') or props.get('application.process.binary') or 'Unbekannte App',
                'detail': props.get('media.name', 'Wiedergabe'),
                'volume': min(100, round(sum(volumes) / len(volumes) * 100 / 65536)) if volumes else 0,
                'muted': bool(item.get('mute')),
            })
        return streams

    def _app_stream(self, index):
        if not isinstance(index, int):
            raise ValueError('Ungültiger Wiedergabestream')
        if not any(item['index'] == index for item in self.app_streams()):
            raise AudioError('Diese App spielt nicht mehr über die Sound Blaster ab.')
        return str(index)

    def set_app_volume(self, index, volume):
        if not isinstance(volume, int) or not 0 <= volume <= 100:
            raise ValueError('Lautstärke muss zwischen 0 und 100 liegen')
        self._run(['pactl', 'set-sink-input-volume', self._app_stream(index), f'{volume}%'])

    def toggle_app_mute(self, index):
        self._run(['pactl', 'set-sink-input-mute', self._app_stream(index), 'toggle'])
