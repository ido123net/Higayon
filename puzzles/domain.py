from django.db import transaction

from .grid import LENGTHS, SLOTS, TEMPLATE, normalize
from .models import Clue, Puzzle, Solution


class Invalid(ValueError):
    pass


def fail(message):
    raise Invalid(message)


def object_fields(data, fields):
    if not isinstance(data, dict) or set(data) - set(fields):
        fail("מבנה הבקשה או שמות השדות אינם תקינים.")


def validate_clues(clues):
    if not isinstance(clues, list) or len(clues) != len(SLOTS):
        fail("יש לשלוח את כל 24 ההגדרות.")
    seen = set()
    for clue in clues:
        object_fields(clue, ["direction", "number", "text", "enumeration"])
        d, n, text = clue.get("direction"), clue.get("number"), clue.get("text")
        if not isinstance(d, str) or type(n) is not int or n not in LENGTHS.get(d, {}):
            fail("מספר ההגדרה או הכיוון אינם תקינים.")
        if (d, n) in seen:
            fail("הגדרה כפולה.")
        seen.add((d, n))
        if not isinstance(text, str) or not text.strip() or len(text) > 5000:
            fail("יש להזין טקסט הגדרה באורך עד 5000 תווים.")
        groups = clue.get("enumeration")
        if groups is not None and (
            not isinstance(groups, list)
            or not groups
            or any(type(v) is not int or v < 1 for v in groups)
            or sum(groups) != LENGTHS[d][n]
        ):
            fail("סכום קבוצות האורך חייב להתאים לאורך ההגדרה.")
    return clues


@transaction.atomic
def save_puzzle(data, puzzle=None):
    object_fields(data, ["title", "clues"])
    if puzzle is None and not {"title", "clues"} <= data.keys():
        fail("יש לשלוח כותרת ואת כל ההגדרות.")
    if not data:
        fail("הבקשה ריקה.")
    title = data.get("title", puzzle.title if puzzle else None)
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        fail("יש להזין כותרת באורך עד 200 תווים.")
    clues = validate_clues(data["clues"]) if "clues" in data else None
    if puzzle is None:
        puzzle = Puzzle.objects.create(title=title)
    elif "title" in data:
        puzzle.title = title
        puzzle.save(update_fields=["title"])
    if clues is not None:
        puzzle.clues.all().delete()
        Clue.objects.bulk_create(
            [
                Clue(
                    puzzle=puzzle,
                    direction=c["direction"],
                    number=c["number"],
                    text=c["text"],
                    enumeration=c.get("enumeration"),
                )
                for c in clues
            ]
        )
    return puzzle


@transaction.atomic
def save_solutions(puzzle, data):
    object_fields(data, ["answers"])
    answers = data.get("answers")
    if not isinstance(answers, list) or len(answers) != len(SLOTS):
        fail("יש לשלוח את כל 24 הפתרונות.")
    seen, normalized = set(), []
    for answer in answers:
        object_fields(answer, ["direction", "number", "answer"])
        d, n, text = answer.get("direction"), answer.get("number"), answer.get("answer")
        if (
            not isinstance(d, str)
            or type(n) is not int
            or n not in LENGTHS.get(d, {})
            or (d, n) in seen
        ):
            fail("זהות פתרון שגויה או כפולה.")
        if not isinstance(text, str):
            fail("פתרון חייב להיות טקסט.")
        text = normalize(text)
        if len(text) != LENGTHS[d][n] or any(not "א" <= c <= "ת" for c in text):
            fail("הפתרון חייב להכיל אותיות עבריות בלבד ובאורך המתאים.")
        seen.add((d, n))
        normalized.append({"direction": d, "number": n, "answer": text})
    cells = {}
    for answer in normalized:
        slot = next(
            s
            for s in SLOTS
            if s["direction"] == answer["direction"] and s["number"] == answer["number"]
        )
        for cell, char in zip(slot["cells"], answer["answer"], strict=True):
            key = tuple(cell)
            if key in cells and cells[key] != char:
                fail("הפתרונות אינם תואמים בנקודות ההצטלבות.")
            cells[key] = char
    Solution.objects.update_or_create(puzzle=puzzle, defaults={"answers": normalized})


def metadata(puzzle):
    return {
        "id": str(puzzle.id),
        "title": puzzle.title,
        "created_at": puzzle.created_at.isoformat(),
    }


def serialize(puzzle):
    return {
        **metadata(puzzle),
        "template": TEMPLATE,
        "clues": list(
            puzzle.clues.order_by("direction", "number").values(
                "direction", "number", "text", "enumeration"
            )
        ),
    }
