"""Canonical physical coordinates: never mirror this data for RTL."""

from typing import TypedDict


class Slot(TypedDict):
    direction: str
    number: int
    length: int
    cells: list[list[int]]


ROWS = (
    "...#.......",
    ".#.#.#.#.#.",
    ".....#.....",
    ".###.#.#.#.",
    "......#....",
    "##.#####.##",
    "....#......",
    ".#.#.#.###.",
    ".....#.....",
    ".#.#.#.#.#.",
    ".......#...",
)
NUMBERS = {
    1: (0, 10),
    2: (0, 8),
    3: (0, 6),
    4: (0, 4),
    5: (0, 2),
    6: (0, 0),
    7: (2, 10),
    8: (2, 4),
    9: (4, 10),
    10: (4, 5),
    11: (4, 2),
    12: (6, 10),
    13: (6, 6),
    14: (6, 3),
    15: (6, 0),
    16: (7, 4),
    17: (8, 10),
    18: (8, 8),
    19: (8, 4),
    20: (10, 10),
    21: (10, 6),
}
LENGTHS = {
    "across": {1: 7, 5: 3, 7: 5, 8: 5, 9: 4, 10: 6, 12: 6, 14: 4, 17: 5, 19: 5, 20: 3, 21: 7},
    "down": {1: 5, 2: 7, 3: 4, 4: 5, 5: 3, 6: 5, 11: 7, 12: 5, 13: 5, 15: 5, 16: 4, 18: 3},
}
SLOTS: list[Slot] = []
for direction, entries in LENGTHS.items():
    for number, length in entries.items():
        row, col = NUMBERS[number]
        cells = [
            [row + (i if direction == "down" else 0), col - (i if direction == "across" else 0)]
            for i in range(length)
        ]
        SLOTS.append({"direction": direction, "number": number, "length": length, "cells": cells})
TEMPLATE = {"rows": ROWS, "numbers": NUMBERS, "slots": SLOTS}
FINAL_LETTERS = str.maketrans("ךםןףץ", "כמנפצ")


def normalize(text):
    return text.translate(FINAL_LETTERS)
