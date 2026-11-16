"""Run with DEBUG=true uv run python tests/browser_smoke.py; requires installed Chrome."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "higayon.settings")
os.environ.setdefault("DEBUG", "true")
import django

django.setup()
from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from playwright.sync_api import sync_playwright

from puzzles.domain import save_puzzle
from puzzles.tests import AppTests, payload


@override_settings(
    DEBUG=True,
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"],
    OWNER_EMAIL="owner@example.com",
    ALLOWED_EMAILS={"owner@example.com", "friend@example.com"},
    STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
)
class BrowserTests(StaticLiveServerTestCase):
    def test_browser(self):
        owner = AppTests.user("owner@example.com")
        friend = AppTests.user("friend@example.com")
        puzzle = save_puzzle(payload())
        grouped = payload("עוד תשבץ")
        grouped["clues"][0]["enumeration"] = [4, 3]
        old = save_puzzle(grouped)
        client = Client()
        client.force_login(owner)
        session = client.cookies[settings.SESSION_COOKIE_NAME].value
        friend_client = Client()
        friend_client.force_login(friend)
        friend_session = friend_client.cookies[settings.SESSION_COOKIE_NAME].value
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(
                viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True
            )
            context.add_cookies(
                [
                    {
                        "name": settings.SESSION_COOKIE_NAME,
                        "value": session,
                        "url": self.live_server_url,
                    }
                ]
            )
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(self.live_server_url)
            page.wait_for_selector(".clue")
            self.assertEqual(page.locator(".cell").count(), 121)
            self.assertEqual(page.locator(".number").count(), 21)
            self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            # Physical top-right cell and intersection toggle.
            page.locator(".cell").nth(10).click()
            self.assertIn("מאונך", page.locator("#active-clue").inner_text())
            page.locator(".cell").nth(10).click()
            self.assertIn("מאוזן", page.locator("#active-clue").inner_text())
            page.locator("#entry").fill("ךםןףץ")
            self.assertEqual(page.locator(".cell").nth(10).locator(".letter").inner_text(), "כ")
            self.assertEqual(page.locator(".cell").nth(6).locator(".letter").inner_text(), "צ")
            page.reload()
            page.wait_for_selector(".clue")
            self.assertEqual(page.locator(".cell").nth(10).locator(".letter").inner_text(), "כ")
            # An in-flight puzzle switch cannot write letters into the old puzzle.
            pending = []
            target = f"**/api/v1/puzzles/{puzzle.id}/"
            page.route(target, lambda route: pending.append(route))
            before = page.evaluate("JSON.stringify(localStorage)")
            page.locator(".site-menu summary").click()
            page.select_option("#puzzles", str(puzzle.id))
            page.wait_for_function("document.querySelector('.workspace').inert")
            self.assertTrue(page.locator("#entry").is_disabled())
            page.evaluate("""() => {
              const entry = document.querySelector('#entry');
              entry.value = 'ד'; entry.dispatchEvent(new InputEvent('input', {bubbles:true}));
            }""")
            self.assertEqual(page.evaluate("JSON.stringify(localStorage)"), before)
            # A failed request restores the selector and the previous playable board.
            self.assertEqual(len(pending), 1)
            pending.pop().abort()
            page.wait_for_function("!document.querySelector('.workspace').inert")
            self.assertEqual(page.locator("#puzzles").input_value(), str(old.id))
            self.assertFalse(page.locator("#entry").is_disabled())
            page.unroute(target)
            # Different puzzle starts empty; switching back restores.
            page.locator(".site-menu summary").click()
            page.select_option("#puzzles", str(puzzle.id))
            page.wait_for_function("document.querySelector('.cell .letter').textContent === ''")
            page.wait_for_timeout(100)
            self.assertEqual(page.locator(".cell").nth(10).locator(".letter").inner_text(), "")
            page.locator(".site-menu summary").click()
            page.select_option("#puzzles", str(old.id))
            page.wait_for_function(
                "document.querySelectorAll('.cell')[10].querySelector('.letter').textContent === 'כ'"
            )
            # Native composition commits once; desktop deletion stays in this word.
            page.locator("#across .clue").first.click()
            page.evaluate("""() => {
              const input=document.querySelector('#entry');
              input.value='אב';
              input.dispatchEvent(new InputEvent('input',{data:'אב',isComposing:true,bubbles:true}));
              input.dispatchEvent(new CompositionEvent('compositionend',{data:'אב',bubbles:true}));
              input.dispatchEvent(new InputEvent('input',{data:'אב',bubbles:true}));
            }""")
            self.assertEqual(page.locator(".cell").nth(10).locator(".letter").inner_text(), "א")
            self.assertEqual(page.locator(".cell").nth(9).locator(".letter").inner_text(), "ב")
            page.locator("#entry").press("Backspace")
            self.assertEqual(page.locator(".cell").nth(8).locator(".letter").inner_text(), "")
            self.assertEqual(page.locator("#active-clue .enumeration").inner_text(), "(4, 3)")
            self.assertEqual(
                page.locator("#active-clue .enumeration").evaluate(
                    "el=>getComputedStyle(el).direction"
                ),
                "ltr",
            )
            page.set_viewport_size({"width": 320, "height": 400})
            self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            box = page.locator("#active-clue").bounding_box()
            assert box is not None
            self.assertGreaterEqual(box["y"], 0)
            page.set_viewport_size({"width": 375, "height": 812})
            Path("/tmp/higayon-qa").mkdir(exist_ok=True)
            page.screenshot(path="/tmp/higayon-qa/phone.png", full_page=True)
            page.set_viewport_size({"width": 1280, "height": 900})
            page.screenshot(path="/tmp/higayon-qa/desktop.png", full_page=True)
            page.goto(self.live_server_url + "/editor/")
            page.wait_for_selector("textarea")
            self.assertEqual(page.locator("textarea").count(), 24)
            page.fill("#title", "תשבץ מהדפדפן")
            for textarea in page.locator("textarea").all():
                textarea.fill("הגדרה לדוגמה!")
            # A rejected save preserves input and gives Hebrew feedback.
            page.locator('[id="groups-across:1"]').fill("99")
            page.get_by_text("שמירת תשבץ", exact=True).click()
            page.wait_for_function("document.querySelector('#status').textContent.includes('סכום')")
            self.assertEqual(page.locator("#title").input_value(), "תשבץ מהדפדפן")
            page.locator('[id="groups-across:1"]').fill("4,3")
            saves = []
            page.route(
                "**/api/v1/puzzles/",
                lambda route: (
                    saves.append(route) if route.request.method == "POST" else route.continue_()
                ),
            )
            page.get_by_text("שמירת תשבץ", exact=True).click()
            self.assertTrue(page.locator("#title").is_disabled())
            self.assertTrue(page.locator("#puzzles").is_disabled())
            self.assertTrue(page.locator("#new").is_disabled())
            self.assertTrue(page.locator("textarea").first.is_disabled())
            self.assertEqual(len(saves), 1)
            saves.pop().continue_()
            page.unroute("**/api/v1/puzzles/")
            page.wait_for_function(
                "document.querySelector('#status').textContent === 'התשבץ נשמר.'"
            )
            # Another account cannot see this account's progress.
            context.add_cookies(
                [
                    {
                        "name": settings.SESSION_COOKIE_NAME,
                        "value": friend_session,
                        "url": self.live_server_url,
                    }
                ]
            )
            page.goto(self.live_server_url)
            page.wait_for_selector(".clue")
            page.locator(".site-menu summary").click()
            page.select_option("#puzzles", str(old.id))
            page.wait_for_timeout(200)
            self.assertEqual(page.locator(".cell").nth(10).locator(".letter").inner_text(), "")
            self.assertFalse(errors, errors)
            browser.close()


if __name__ == "__main__":
    from django.test.utils import get_runner

    failures = get_runner(settings)(verbosity=1).run_tests(["tests.browser_smoke.BrowserTests"])
    sys.exit(bool(failures))
