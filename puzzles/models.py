import uuid
from typing import cast

from django.conf import settings
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


class AuthorizedEmail(models.Model):
    objects = models.Manager()
    email = models.EmailField(unique=True, verbose_name="כתובת אימייל")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="נוסף בתאריך")
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="authorized_emails_added",
        verbose_name="נוסף על ידי",
    )

    class Meta:
        ordering = ["email"]
        verbose_name = "משתמש מורשה"
        verbose_name_plural = "משתמשים מורשים"

    def save(self, *args, **kwargs):
        self.email = cast(str, self.email).strip().lower()  # ty: ignore[invalid-assignment]  # Django's descriptor is typed as EmailField.
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email
