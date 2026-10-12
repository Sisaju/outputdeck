import argparse
import json
from pathlib import Path
import subprocess
import sys

from .audio import AudioController, AudioError
from .i18n import saved_language, translate


def show_output_notification(state):
    language = saved_language()
    title = translate('Headset aktiv' if state.output == 'headphones'
                      else 'Lautsprecher aktiv', language)
    volume = (translate('Lautstärke: {volume} %', language, volume=state.volume)
              if state.volume is not None else 'Sound Blaster Z')
    icon = Path(__file__).resolve().parent.parent / 'assets/soundblaster.svg'
    try:
        subprocess.run(['notify-send', '-a', 'OutputDeck', '-i', str(icon),
                        '-t', '1800', title, volume], capture_output=True, timeout=3)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def main():
    parser = argparse.ArgumentParser(description='OutputDeck')
    parser.add_argument('--toggle', action='store_true', help='Ausgang ohne Fenster umschalten')
    parser.add_argument('--output', choices=['speakers', 'headphones'])
    parser.add_argument('--status', action='store_true', help='Aktuellen Zustand als JSON ausgeben')
    parser.add_argument('--notify', action='store_true', help='Beim Umschalten Desktop-Benachrichtigung anzeigen')
    parser.add_argument('--screenshot', help=argparse.SUPPRESS)
    args = parser.parse_args()
    controller = AudioController()
    try:
        if args.toggle:
            controller.toggle()
        elif args.output:
            controller.select_output(args.output)
        if args.status or args.toggle or args.output:
            state = controller.snapshot()
            if args.notify and (args.toggle or args.output):
                show_output_notification(state)
            print(json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
            return 0
    except AudioError as exc:
        print(translate(str(exc), saved_language()), file=sys.stderr)
        return 1
    try:
        from .ui import launch
    except ImportError:
        print('Qt fehlt. Bitte ./install.sh ausführen.', file=sys.stderr)
        return 1
    return launch(controller, args.screenshot)


if __name__ == '__main__':
    sys.exit(main())
