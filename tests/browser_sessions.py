"""Exercise sharing with two isolated browser contexts and real HTTP requests."""

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "higayon.settings")
os.environ.setdefault("DEBUG", "true")
import django

django.setup()
from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from playwright.sync_api import expect, sync_playwright

from puzzles.domain import save_puzzle
from puzzles.models import AuthorizedEmail, ConfirmedAnswer, SessionMember, SolvingSession
from puzzles.tests import AppTests, payload


@override_settings(
    DEBUG=True,
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    OWNER_EMAIL="owner@example.com",
    ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"],
    STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
)
class SharedBrowserTests(StaticLiveServerTestCase):
    def test_explicit_confirmation_drafts_and_decisions(self):
        owner = AppTests.user("owner@example.com")
        friend = AppTests.user("friend@example.com")
        AuthorizedEmail.objects.get_or_create(email=friend.email)
        puzzle = save_puzzle(payload())
        session = SolvingSession.objects.create(puzzle=puzzle, creator=owner)
        for user in (owner, friend):
            SessionMember.objects.create(session=session, user=user)
        cookies = []
        for user in (owner, friend):
            client = Client()
            client.force_login(user)
            cookies.append(client.cookies[settings.SESSION_COOKIE_NAME].value)
        with ThreadPoolExecutor(max_workers=1) as pool, sync_playwright() as p:

            def db(fn):
                return pool.submit(fn).result()

            browser = p.chromium.launch(channel="chrome", headless=True)
            contexts = []
            pages = []
            errors = []
            for cookie in cookies:
                context = browser.new_context(viewport={"width": 375, "height": 812})
                context.add_cookies(
                    [
                        {
                            "name": settings.SESSION_COOKIE_NAME,
                            "value": cookie,
                            "url": self.live_server_url,
                        }
                    ]
                )
                page = context.new_page()
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(f"{self.live_server_url}/sessions/{session.pk}/")
                page.wait_for_selector(".clue")
                contexts.append(context)
                pages.append(page)
            page, other = pages
            writes = []
            page.on(
                "request",
                lambda r: (
                    writes.append(r.post_data)
                    if r.method == "POST" and "/answers/" in r.url
                    else None
                ),
            )
            page.locator("#across .clue").first.click()
            page.locator("#entry").fill("אבגדהוז")
            expect(page.locator("#confirm-answer")).to_be_enabled()
            self.assertEqual(writes, [])
            self.assertEqual(db(lambda: ConfirmedAnswer.objects.count()), 0)
            page.locator("#confirm-answer").click()
            expect(page.locator("#confirmation-state")).to_have_text("התשובה אושרה")
            self.assertEqual(len(writes), 1)
            self.assertEqual(db(lambda: ConfirmedAnswer.objects.get().answer), "אבגדהוז")
            # A second browser reads counts only; no letters from the first user.
            expect(other.locator("#active-count")).to_have_text(
                "1 משתתפים אחרים אישרו", timeout=15000
            )
            self.assertTrue(
                all(not letter for letter in other.locator(".letter").all_text_contents())
            )
            # Edits stay local and blocking decisions can restore without a write.
            page.locator("#across .clue").first.click()
            page.locator("#entry").fill("זוהדגבא")
            page.locator("#down .clue").first.click()
            expect(page.locator("#answer-decisions")).to_be_visible()
            self.assertEqual(len(writes), 1)
            page.locator("#decision-list select").select_option("restore")
            page.locator("#decisions-apply").click()
            expect(page.locator("#answer-decisions")).not_to_be_visible()
            self.assertEqual(len(writes), 1)
            self.assertEqual(page.locator(".cell").nth(10).locator(".letter").inner_text(), "א")
            # Deletion, refresh, and explicit withdrawal preserve local empty cells.
            page.locator("#across .clue").first.click()
            page.locator("#entry").press("Delete")
            page.reload()
            expect(page.locator("#answer-decisions")).to_be_visible()
            self.assertEqual(len(writes), 1)
            page.locator("#decision-list select").select_option("submit")
            page.locator("#decisions-apply").click()
            expect(page.locator("#answer-decisions")).not_to_be_visible()
            self.assertEqual(db(lambda: ConfirmedAnswer.objects.get().answer), "")
            self.assertEqual(len(writes), 2)
            # Failed writes preserve the draft and require an explicit retry.
            page.locator("#across .clue").first.click()
            page.locator("#entry").fill("אבגדהוז")
            answer_url = f"**/api/v1/sessions/{session.pk}/answers/"
            page.route(answer_url, lambda route: route.abort())
            page.locator("#confirm-answer").click()
            expect(page.locator("#status")).to_contain_text("אין חיבור")
            self.assertEqual(db(lambda: ConfirmedAnswer.objects.get().answer), "")
            page.unroute(answer_url)
            page.locator("#confirm-answer").click()
            expect(page.locator("#confirmation-state")).to_have_text("התשובה אושרה")
            # Crossing letters affect both confirmed clues and require two decisions.
            page.locator("#down .clue").first.click()
            page.locator("#entry").fill("אבגדה")
            page.locator("#confirm-answer").click()
            expect(page.locator("#confirmation-state")).to_have_text("התשובה אושרה")
            page.locator("#entry").press("Home")
            page.locator("#entry").fill("ז")
            page.locator("#across .clue").nth(1).click()
            expect(page.locator("#decision-list select")).to_have_count(2)
            page.locator("#decisions-cancel").click()
            expect(page.locator("#answer-decisions")).not_to_be_visible()
            page.locator("#across .clue").nth(1).click()
            for select in page.locator("#decision-list select").all():
                select.select_option("submit")
            page.locator("#decisions-apply").click()
            expect(page.locator("#answer-decisions")).not_to_be_visible()
            self.assertEqual(
                db(
                    lambda: list(
                        ConfirmedAnswer.objects.order_by("direction").values_list(
                            "answer", flat=True
                        )
                    )
                ),
                ["זבגדהוז", "זבגדה"],
            )
            # A stale version is rejected without losing the local draft.
            page.locator("#across .clue").first.click()
            page.locator("#entry").fill("אבגדהוז")
            db(lambda: ConfirmedAnswer.objects.filter(direction="across").update(version=99))
            page.locator("#confirm-answer").click()
            expect(page.locator("#status")).to_contain_text("מכשיר אחר")
            self.assertEqual(page.locator(".cell").nth(10).locator(".letter").inner_text(), "א")
            page.locator("#confirm-answer").click()
            expect(page.locator("#confirmation-state")).to_have_text("התשובה אושרה")
            self.assertEqual(
                db(lambda: ConfirmedAnswer.objects.get(direction="across").version), 100
            )
            self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            Path("/tmp/higayon-qa").mkdir(exist_ok=True)
            page.screenshot(path="/tmp/higayon-qa/shared-phone.png", full_page=True)
            page.set_viewport_size({"width": 1280, "height": 900})
            self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            page.wait_for_timeout(150)
            page.screenshot(path="/tmp/higayon-qa/shared-desktop.png")
            # A new session for the same puzzle starts with a separate draft.
            fresh = contexts[0].new_page()
            fresh.goto(self.live_server_url)
            fresh.wait_for_selector(".clue")
            fresh.locator(".site-menu summary").click()
            fresh.locator("#solve-together").click()
            fresh.wait_for_url("**/sessions/*/")
            fresh.wait_for_selector(".clue")
            self.assertTrue(
                all(not letter for letter in fresh.locator(".letter").all_text_contents())
            )
            fresh.locator(".site-menu summary").click()
            expect(fresh.locator("#invite-link")).to_have_value(
                self.live_server_url
                + "/join/"
                + str(db(lambda: SolvingSession.objects.exclude(pk=session.pk).get().invite_token))
                + "/"
            )
            self.assertEqual(errors, [])
            browser.close()
