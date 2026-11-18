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


class SolvingSession(models.Model):
    objects = models.Manager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    puzzle = models.ForeignKey(Puzzle, on_delete=models.CASCADE, verbose_name="תשבץ")
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="יוצר"
    )
    invite_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    invite_active = models.BooleanField(default=True, verbose_name="קישור הצטרפות פעיל")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="נוצר בתאריך")

    class Meta:
        verbose_name = "מפגש פתרון"
        verbose_name_plural = "מפגשי פתרון"

    def __str__(self):
        return f"{cast(Puzzle, self.puzzle).title} · {self.id}"


class SessionMember(models.Model):
    objects = models.Manager()
    session = models.ForeignKey(SolvingSession, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        verbose_name="משתתף",
    )

    guest_name = models.CharField(max_length=80, blank=True, verbose_name="שם אורח")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(user__isnull=False, guest_name="")
                    | (models.Q(user__isnull=True) & ~models.Q(guest_name=""))
                ),
                name="session_member_identity",
            ),
            models.UniqueConstraint(fields=["session", "user"], name="unique_session_member"),
        ]
        verbose_name = "משתתף במפגש"
        verbose_name_plural = "משתתפים במפגש"


class ConfirmedAnswer(models.Model):
    objects = models.Manager()
    member = models.ForeignKey(SessionMember, on_delete=models.CASCADE, related_name="answers")
    direction = models.CharField(max_length=6)
    number = models.PositiveSmallIntegerField()
    answer = models.CharField(max_length=11, blank=True)
    version = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["member", "direction", "number"], name="unique_member_answer"
            )
        ]
