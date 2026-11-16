import uuid

from django.db import models


class Puzzle(models.Model):
    objects = models.Manager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True, editable=False, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class Clue(models.Model):
    objects = models.Manager()
    puzzle = models.ForeignKey(Puzzle, on_delete=models.CASCADE, related_name="clues")
    direction = models.CharField(max_length=6)
    number = models.PositiveSmallIntegerField()
    text = models.TextField()
    enumeration = models.JSONField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["puzzle", "direction", "number"], name="unique_clue_slot"
            )
        ]


class Solution(models.Model):
    objects = models.Manager()
    puzzle = models.OneToOneField(Puzzle, on_delete=models.CASCADE, related_name="solution")
    answers = models.JSONField()
