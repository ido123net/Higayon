import json
from datetime import timedelta
from types import SimpleNamespace

from allauth.account.models import EmailAddress
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .auth import GoogleAdapter
from .domain import save_puzzle
from .grid import LENGTHS, NUMBERS, ROWS, SLOTS, normalize
from .models import Clue, Puzzle, Solution


def payload(title="דוגמה"):
    return {
        "title": title,
        "clues": [
            {
                "number": s["number"],
                "direction": s["direction"],
                "text": 'הגדרה, עם "פיסוק"!',
                "enumeration": [s["length"]],
            }
            for s in SLOTS
        ],
    }


@override_settings(
    DEBUG=True,
    SECURE_SSL_REDIRECT=False,
    OWNER_EMAIL="owner@example.com",
    ALLOWED_EMAILS={"owner@example.com", "friend@example.com"},
    OWNER_API_TOKEN="a" * 64,
    STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
)
class AppTests(TestCase):
    def setUp(self):
        self.owner = self.user("owner@example.com")
        self.friend = self.user("friend@example.com")
        self.client.force_login(self.owner)

    @staticmethod
    def user(email, verified=True):
        user = get_user_model().objects.create_user(username=email, email=email)
        EmailAddress.objects.create(user=user, email=email, verified=verified, primary=True)
        SocialAccount.objects.create(user=user, provider="google", uid=email)  # ty: ignore[missing-attribute]  # Django adds the manager at runtime.
        return user

    def send(self, method, path="/api/v1/puzzles/", data=None, client=None, **headers):
        return getattr(client or self.client, method)(
            path, data=json.dumps(data), content_type="application/json", **headers
        )

    def test_grid(self):
        self.assertEqual(len(ROWS), 11)
        self.assertEqual(len(NUMBERS), 21)
        self.assertEqual(len(SLOTS), 24)
        covered = set()
        for s in SLOTS:
            self.assertEqual(len(s["cells"]), LENGTHS[s["direction"]][s["number"]])
            self.assertEqual(tuple(s["cells"][0]), NUMBERS[s["number"]])
            for r, c in s["cells"]:
                self.assertTrue(0 <= r < 11 and 0 <= c < 11)
                self.assertEqual(ROWS[r][c], ".")
                covered.add((r, c))
            r, c = s["cells"][-1]
            r, c = (r + 1, c) if s["direction"] == "down" else (r, c - 1)
            self.assertTrue(r == 11 or c == -1 or ROWS[r][c] == "#")
        self.assertEqual(
            covered, {(r, c) for r in range(11) for c in range(11) if ROWS[r][c] == "."}
        )
        self.assertEqual(normalize("ךםןףץ"), "כמנפצ")
        self.assertEqual(SLOTS[0]["cells"], [[0, c] for c in range(10, 3, -1)])

    def test_create_roundtrip_and_full_validation(self):
        response = self.send("post", data=payload())
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()["clues"]), 24)
        for mutate in [
            lambda p: p["clues"].pop(),
            lambda p: p["clues"].__setitem__(0, p["clues"][1]),
            lambda p: p["clues"][0].update(enumeration=[4, 4]),
            lambda p: p["clues"][0].update(number=True),
            lambda p: p["clues"][0].update(text=3),
            lambda p: p.update(unexpected=1),
        ]:
            bad = payload()
            mutate(bad)
            self.assertEqual(self.send("post", data=bad).status_code, 400)
        self.assertEqual(Puzzle.objects.count(), 1)
        self.assertEqual(Clue.objects.count(), 24)

    def test_malformed_and_oversized_requests_are_hebrew_json(self):
        for raw in ["{", "[" * 1200 + "]" * 1200, "null", "[]"]:
            response = self.client.post(
                "/api/v1/puzzles/", data=raw, content_type="application/json"
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn("error", response.json())
        response = self.client.post(
            "/api/v1/puzzles/", data=" " * 131073, content_type="application/json"
        )
        self.assertEqual(response.status_code, 413)
        self.assertIn("גדולה מדי", response.json()["error"])
        self.assertEqual(Puzzle.objects.count(), 0)

    def test_patch_atomic_and_latest_immutable(self):
        older = save_puzzle(payload("ישן"))
        newer = save_puzzle(payload("חדש"))
        original = older.created_at
        path = f"/api/v1/puzzles/{older.id}/"
        bad = payload("שינוי")
        bad["clues"][0]["enumeration"] = [999]
        self.assertEqual(self.send("patch", path, bad).status_code, 400)
        older.refresh_from_db()
        self.assertEqual(older.title, "ישן")
        self.assertEqual(older.clues.count(), 24)
        self.assertEqual(self.send("patch", path, {"title": "עודכן"}).status_code, 200)
        older.refresh_from_db()
        self.assertEqual(older.created_at, original)
        self.assertEqual(self.client.get("/api/v1/puzzles/latest/").json()["id"], str(newer.id))
        same = timezone.now() - timedelta(days=1)
        Puzzle.objects.update(created_at=same)
        self.assertEqual(
            self.client.get("/api/v1/puzzles/").json()["puzzles"][0]["id"],
            str(max([older.id, newer.id])),
        )

    def test_read_access(self):
        self.client.logout()
        self.assertEqual(self.client.get("/").status_code, 302)
        self.assertEqual(self.client.get("/api/v1/puzzles/").status_code, 401)
        for email, verified in [("stranger@example.com", True), ("friend@example.com", False)]:
            if email == "friend@example.com":
                EmailAddress.objects.filter(user=self.friend).update(verified=False)
                user = self.friend
            else:
                user = self.user(email, verified)
            self.client.force_login(user)
            self.assertEqual(self.client.get("/api/v1/puzzles/").status_code, 401)

    def test_owner_only_writes_and_solutions_hidden(self):
        p = save_puzzle(payload())
        path = f"/api/v1/puzzles/{p.id}/"
        answers = {
            "answers": [
                {"number": s["number"], "direction": s["direction"], "answer": "ם" * s["length"]}
                for s in SLOTS
            ]
        }
        self.assertEqual(self.send("put", path + "solutions/", answers).status_code, 200)
        self.assertTrue(all(set(a["answer"]) == {"מ"} for a in Solution.objects.get().answers))
        for endpoint in [path, "/api/v1/puzzles/latest/", "/api/v1/puzzles/"]:
            self.assertNotIn("answer", self.client.get(endpoint).content.decode())
            self.assertNotIn("solution", self.client.get(endpoint).content.decode())
        answers["answers"][0]["answer"] = "א"
        self.assertEqual(self.send("put", path + "solutions/", answers).status_code, 400)
        self.client.force_login(self.friend)
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get("/editor/").status_code, 403)
        for method, url, data in [
            ("post", "/api/v1/puzzles/", payload()),
            ("patch", path, {"title": "x"}),
            ("put", path + "solutions/", answers),
        ]:
            self.assertEqual(self.send(method, url, data).status_code, 403)
        self.assertEqual(self.client.get(path + "solutions/").status_code, 405)

    def test_tokens_and_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(
            self.send(
                "post", data=payload(), client=client, HTTP_AUTHORIZATION="Bearer " + "a" * 64
            ).status_code,
            201,
        )
        for value in ["Bearer wrong", "Basic " + "a" * 64, "Bearer "]:
            self.assertEqual(
                client.get("/api/v1/puzzles/", HTTP_AUTHORIZATION=value).status_code, 401
            )
        with override_settings(OWNER_API_TOKEN=""):
            self.assertEqual(
                client.get("/api/v1/puzzles/", HTTP_AUTHORIZATION="Bearer " + "a" * 64).status_code,
                401,
            )
        client.force_login(self.owner)
        self.assertEqual(self.send("post", data=payload(), client=client).status_code, 403)
        client.get("/")
        token = client.cookies["csrftoken"].value
        self.assertEqual(
            self.send("post", data=payload(), client=client, HTTP_X_CSRFTOKEN=token).status_code,
            201,
        )

    def test_empty_and_google_verified(self):
        self.assertEqual(self.client.get("/api/v1/puzzles/latest/").json(), {"puzzle": None})
        adapter = GoogleAdapter()
        for provider, email, verified in [
            ("google", "owner@example.com", False),
            ("google", "stranger@example.com", True),
            ("other", "owner@example.com", True),
        ]:
            social = SimpleNamespace(
                account=SimpleNamespace(provider=provider),
                user=SimpleNamespace(email=email),
                email_addresses=[SimpleNamespace(email=email, verified=verified)],
            )
            with self.assertRaises(ImmediateHttpResponse):
                adapter.pre_social_login(self.client.request().wsgi_request, social)
        social = SimpleNamespace(
            account=SimpleNamespace(provider="google"),
            user=SimpleNamespace(email="owner@example.com"),
            email_addresses=[SimpleNamespace(email="owner@example.com", verified=True)],
        )
        adapter.pre_social_login(None, social)

    def test_old_preview_sessions_have_no_access(self):
        preview = get_user_model().objects.create_user(
            username="higayon-local-preview", email="local-preview@localhost.invalid"
        )
        self.client.force_login(preview)
        with override_settings(ALLOWED_EMAILS={preview.email}, OWNER_EMAIL=preview.email):
            self.assertEqual(self.client.get("/").status_code, 302)
            self.assertEqual(self.client.get("/editor/").status_code, 302)
            self.assertEqual(self.client.get("/api/v1/puzzles/").status_code, 401)
            self.assertEqual(self.send("post", data=payload()).status_code, 401)
        self.assertEqual(self.client.get("/login/local/").status_code, 404)
        self.assertNotContains(self.client.get("/login/"), "/login/local/")
