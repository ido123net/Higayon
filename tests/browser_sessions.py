"""Exercise sharing with two isolated browser contexts and real HTTP requests."""

import json
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
    SOCIALACCOUNT_PROVIDERS={
        "google": {"APPS": [{"client_id": "test-client", "secret": "test-secret"}]}
    },
    ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"],
    STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
)
class SharedBrowserTests(StaticLiveServerTestCase):
    def test_timed_completion_sync_and_desktop_scrolling(self):
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
                page.clock.install(time="2026-01-01T00:00:00Z")
                page.clock.pause_at("2026-01-01T00:00:01Z")
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

            def tick(tab, *, write=False):
                suffix = "/answers/" if write else f"/{session.pk}/"
                with tab.expect_response(lambda r: r.url.endswith(suffix)):
                    tab.clock.fast_forward(10000)

            active_mark = page.locator("#completion-mark")
            across = page.locator("#across .clue").first
            down = page.locator("#down .clue").first
            entry = page.locator("#entry")
            across.click()
            entry.fill("אב")
            tick(page)
            expect(active_mark).to_be_hidden()
            self.assertEqual(writes, [])
            entry.fill("גדהוז")
            expect(active_mark).to_be_visible()
            expect(across.locator(".completion-mark")).to_be_visible()
            down.click()
            entry.fill("אבגדה")
            expect(active_mark).to_be_visible()
            self.assertEqual(writes, [])
            self.assertEqual(db(lambda: ConfirmedAnswer.objects.count()), 0)
            tick(page, write=True)
            self.assertEqual(len(json.loads(writes[0])["changes"]), 2)
            self.assertEqual(db(lambda: ConfirmedAnswer.objects.count()), 2)
            tick(other)
            for badge in (
                other.locator("#active-count"),
                other.locator("#across .answer-count").first,
            ):
                expect(badge.locator(".count-value")).to_have_text("1")
                expect(badge).to_have_accessible_name("מספר המשתתפים האחרים שהשלימו את ההגדרה: 1")
            self.assertFalse(any(other.locator(".letter").all_text_contents()))
            expect(other.locator("#completion-mark")).to_be_hidden()
            tick(page)
            self.assertEqual(len(writes), 1)

            # A deletion at the intersection withdraws both clues, even across reload.
            across.click()
            entry.press("Delete")
            expect(across.locator(".completion-mark")).to_be_hidden()
            expect(down.locator(".completion-mark")).to_be_hidden()
            page.reload()
            page.wait_for_selector(".clue")
            self.assertEqual(len(writes), 1)
            tick(page, write=True)
            self.assertEqual([c["answer"] for c in json.loads(writes[-1])["changes"]], [None, None])
            tick(other)
            expect(other.locator("#active-count .count-value")).to_have_text("0")

            # Network failure leaves the batch queued. Retry the latest revision.
            across.click()
            entry.fill("ז")
            answer_url = f"**/api/v1/sessions/{session.pk}/answers/"
            page.route(answer_url, lambda route: route.abort())
            page.clock.fast_forward(10000)
            expect(page.locator("#sync-status")).to_contain_text("אין חיבור")
            page.unroute(answer_url)
            across.click()
            entry.fill("ח")
            expect(active_mark).to_be_visible()
            tick(page, write=True)
            expect(page.locator("#sync-status")).to_be_hidden()
            self.assertEqual(
                db(lambda: ConfirmedAnswer.objects.get(direction="across").answer), "חבגדהוז"
            )

            # A newer remote version cannot be overwritten by a stale queued edit.
            across.click()
            entry.fill("ת")
            db(
                lambda: ConfirmedAnswer.objects.filter(direction="across").update(
                    answer="שבגדהוז", version=99
                )
            )
            tick(page)
            expect(page.locator("#sync-status")).to_contain_text("מכשיר אחר")
            self.assertEqual(
                db(lambda: ConfirmedAnswer.objects.get(direction="across").version), 99
            )
            across.click()
            entry.fill("ל")
            tick(page, write=True)
            expect(page.locator("#sync-status")).to_be_hidden()
            self.assertEqual(
                db(lambda: ConfirmedAnswer.objects.get(direction="across").version), 100
            )
            # An edit made while a batch is in flight belongs to the following tick.
            held = []
            page.route(answer_url, lambda route: held.append(route))
            across.click()
            entry.fill("ק")
            with page.expect_request(lambda request: request.url.endswith("/answers/")):
                page.clock.fast_forward(10000)
            across.click()
            entry.fill("ר")
            with page.expect_response(lambda response: response.url.endswith("/answers/")):
                held[0].continue_()
            page.unroute(answer_url)
            tick(page, write=True)
            self.assertEqual(
                db(lambda: ConfirmedAnswer.objects.get(direction="across").answer), "רבגדהוז"
            )
            # Read another device's update into unchanged cells without an echo write.
            db(
                lambda: ConfirmedAnswer.objects.filter(direction="across").update(
                    answer="רבגדהוח", version=110
                )
            )
            write_count = len(writes)
            tick(page)
            expect(page.locator(".cell").nth(4).locator(".letter")).to_have_text("ח")
            self.assertEqual(len(writes), write_count)
            self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            Path("/tmp/higayon-qa").mkdir(exist_ok=True)
            page.screenshot(path="/tmp/higayon-qa/shared-phone.png", full_page=True)
            page.set_viewport_size({"width": 1280, "height": 700})
            clues = page.locator(".clues")
            board = page.locator("#board")
            before = board.bounding_box()
            clues.evaluate("el => { el.scrollTop = el.scrollHeight; }")
            self.assertGreater(clues.evaluate("el => el.scrollTop"), 0)
            self.assertEqual(board.bounding_box(), before)
            self.assertTrue(page.evaluate("document.documentElement.scrollHeight <= innerHeight"))
            page.screenshot(path="/tmp/higayon-qa/shared-desktop.png")
            # A new session for the same puzzle starts with a separate draft.
            fresh = contexts[0].new_page()
            fresh.goto(self.live_server_url)
            fresh.wait_for_selector(".clue")
            fresh.locator("#open-menu").click()
            fresh.locator("#solve-together").click()
            fresh.wait_for_url("**/sessions/*/share/")
            invite = fresh.locator("#share-url").input_value()
            contexts[0].grant_permissions(["clipboard-read", "clipboard-write"])
            fresh.locator("#copy-share").click()
            expect(fresh.locator("#share-status")).to_have_text("הקישור הועתק.")
            self.assertEqual(fresh.evaluate("navigator.clipboard.readText()"), invite)
            guest_context = browser.new_context()
            guest = guest_context.new_page()
            guest.on("pageerror", lambda e: errors.append(str(e)))
            guest.goto(invite)
            expect(guest.get_by_role("button", name="כניסה עם Google")).to_be_visible()
            guest.get_by_label("השם שלך במפגש").fill("נועה")
            guest.get_by_role("button", name="הצטרפות כאורח").click()
            guest.wait_for_selector(".clue")
            guest.locator("#across .clue").first.click()
            guest.locator("#entry").fill("אבגדהוז")
            expect(guest.locator("#completion-mark")).to_be_visible()
            expect(guest.locator("#solve-together")).to_have_count(0)
            fresh.get_by_role("link", name="מעבר לתשבץ").click()
            fresh.wait_for_selector(".clue")
            self.assertTrue(
                all(not letter for letter in fresh.locator(".letter").all_text_contents())
            )
            fresh.locator("#open-menu").click()
            expect(fresh.locator("#invite-link")).to_have_value(
                self.live_server_url
                + "/join/"
                + str(db(lambda: SolvingSession.objects.exclude(pk=session.pk).get().invite_token))
                + "/"
            )
            self.assertEqual(errors, [])
            browser.close()
