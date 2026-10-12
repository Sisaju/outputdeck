import json
import tempfile
import unittest
from pathlib import Path

from soundblaster.audio import AudioController, AudioError


CARDS = ' 0 [Creative       ]: HDA-Intel - HDA Creative\n 1 [NVidia ]: HDA-Intel - HDA NVidia\n'


class FakeAudio:
    def __init__(self):
        self.output = 0
        self.volume = 50
        self.calls = []

    def run(self, args):
        self.calls.append(args)
        if args[:3] == ['amixer', '-c', '0']:
            if args[3] == 'cget':
                return f'  : values={self.output}\n'
            if args[3] == 'cset':
                self.output = int(args[5])
                return ''
        if args == ['pactl', '-f', 'json', 'list', 'sinks']:
            return json.dumps([
                {'name': 'hdmi', 'properties': {'alsa.card': '1'},
                 'volume': {'left': {'value': 65536}}, 'mute': False},
                {'index': 20, 'name': 'creative-analog', 'properties': {'alsa.card': '0',
                    'alsa.mixer_name': 'Creative Sound Blaster Z'},
                 'volume': {'left': {'value': round(self.volume * 65536 / 100)},
                            'right': {'value': round(self.volume * 65536 / 100)}},
                 'mute': False},
            ])
        if args == ['pactl', 'get-default-sink']:
            return 'creative-analog\n'
        if args[:2] == ['pactl', 'set-sink-volume']:
            self.volume = int(args[3].rstrip('%'))
            return ''
        raise AssertionError(args)


class AudioControllerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cards = Path(self.temp.name) / 'cards'
        self.cards.write_text(CARDS)
        self.fake = FakeAudio()
        self.audio = AudioController(self.fake.run, self.cards,
                                     Path(self.temp.name) / 'state.json')

    def tearDown(self):
        self.temp.cleanup()

    def test_snapshot_uses_creative_sink_and_hardware_route(self):
        state = self.audio.snapshot()
        self.assertEqual((state.card, state.output, state.sink, state.volume),
                         ('0', 'speakers', 'creative-analog', 50))
        self.assertTrue(state.is_default)

    def test_toggle_changes_only_creative_output_select(self):
        self.audio.toggle()
        self.assertEqual(self.audio.snapshot().output, 'headphones')
        self.assertIn(['amixer', '-c', '0', 'cset', 'name=Output Select', '1'],
                      self.fake.calls)
        self.assertFalse(any(c[:2] == ['pactl', 'set-default-sink'] for c in self.fake.calls))

    def test_volume_targets_creative_sink(self):
        self.audio.set_volume(37)
        self.assertIn(['pactl', 'set-sink-volume', 'creative-analog', '37%'],
                      self.fake.calls)

    def test_missing_card_raises_clear_error(self):
        self.cards.write_text(' 1 [NVidia ]: HDA-Intel - HDA NVidia\n')
        with self.assertRaisesRegex(AudioError, 'Keine Sound-Blaster'):
            self.audio.snapshot()

    def test_each_output_remembers_its_own_volume(self):
        self.audio.set_volume(60)
        self.audio.select_output('headphones')
        self.assertEqual(self.fake.volume, 35)
        self.audio.set_volume(22)
        self.audio.select_output('speakers')
        self.assertEqual(self.fake.volume, 60)
        self.audio.select_output('headphones')
        self.assertEqual(self.fake.volume, 22)


class RichFakeAudio(FakeAudio):
    def __init__(self):
        super().__init__()
        self.switches = dict.fromkeys(AudioController.EFFECTS, True)
        self.levels = dict.fromkeys(('surround', 'crystalizer', 'xbass', 'dialog', 'smart_volume'), 50)
        self.eq = 'Flat'
        self.smart = 'Normal'
        self.app_volume = 42

    def run(self, args):
        if args[:3] == ['amixer', '-c', '0'] and args[3] in ('sget', 'sset'):
            self.calls.append(args)
            name = args[4]
            if name == 'FX: Equalizer Preset':
                if args[3] == 'sset':
                    self.eq = args[5]
                return f"  Items: 'Flat' 'Rock'\n  Item0: '{self.eq}'\n"
            if name == 'FX: Smart Volume Setting':
                if args[3] == 'sset':
                    self.smart = args[5]
                return f"  Items: 'Normal' 'Night'\n  Item0: '{self.smart}'\n"
            key = next(k for k, n in AudioController.EFFECTS.items() if n == name)
            if args[3] == 'sset':
                if args[5].endswith('%'):
                    self.levels[key] = int(args[5][:-1])
                else:
                    self.switches[key] = args[5] == 'on'
            volume = f" [{self.levels[key]}%]" if key in self.levels else ''
            return f"  Mono: Playback{volume} [{'on' if self.switches[key] else 'off'}]\n"
        if args == ['pactl', '-f', 'json', 'list', 'sink-inputs']:
            self.calls.append(args)
            return json.dumps([
                {'index': 7, 'sink': 20, 'properties': {'application.name': 'Browser',
                    'media.name': 'Video'}, 'volume': {'left': {
                    'value': round(self.app_volume * 65536 / 100)}}, 'mute': False},
                {'index': 8, 'sink': 21, 'properties': {'application.name': 'HDMI-App'},
                 'volume': {'left': {'value': 65536}}, 'mute': False},
            ])
        if args[:2] == ['pactl', 'set-sink-input-volume']:
            self.calls.append(args)
            self.app_volume = int(args[3].rstrip('%'))
            return ''
        return super().run(args)


class FeatureTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        cards = Path(self.temp.name) / 'cards'
        cards.write_text(CARDS)
        self.fake = RichFakeAudio()
        self.audio = AudioController(self.fake.run, cards,
                                     Path(self.temp.name) / 'state.json')

    def tearDown(self):
        self.temp.cleanup()

    def test_effects_and_profile_round_trip(self):
        self.audio.set_effect_level('xbass', 38)
        self.audio.set_eq_preset('Rock')
        self.audio.save_profile('Gaming')
        self.audio.set_effect_level('xbass', 12)
        self.audio.set_eq_preset('Flat')
        self.audio.apply_profile('Gaming')
        effects = self.audio.effects_snapshot()
        self.assertEqual(effects['controls']['xbass']['level'], 38)
        self.assertEqual(effects['eq_preset'], 'Rock')

    def test_only_streams_on_sound_blaster_are_controlled(self):
        self.assertEqual([item['name'] for item in self.audio.app_streams()], ['Browser'])
        self.audio.set_app_volume(7, 29)
        self.assertEqual(self.fake.app_volume, 29)
        with self.assertRaisesRegex(AudioError, 'nicht mehr'):
            self.audio.set_app_volume(8, 20)


if __name__ == '__main__':
    unittest.main()
