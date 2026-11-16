from django.core.management.base import BaseCommand

from puzzles.domain import save_puzzle
from puzzles.grid import SLOTS


class Command(BaseCommand):
    help = "יצירת תשבץ דוגמה עם הגדרות לדוגמה בלבד"

    def handle(self, *args, **options):
        puzzle = save_puzzle(
            {
                "title": "תשבץ דוגמה — אינו תוכן מהעיתון",
                "clues": [
                    {
                        "direction": s["direction"],
                        "number": s["number"],
                        "text": f"הגדרה לדוגמה בלבד, מספר {s['number']}",
                        "enumeration": [s["length"]],
                    }
                    for s in SLOTS
                ],
            }
        )
        self.stdout.write(str(puzzle.id))
