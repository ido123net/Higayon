import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import connections, transaction
from django.test import (
    Client,
    TestCase,
    TransactionTestCase,
    override_settings,
    skipUnlessDBFeature,
)
from prometheus_client import REGISTRY

from .domain import save_puzzle
from .models import AuthorizedEmail, ConfirmedAnswer, SessionMember, SolvingSession
from .tests import AppTests, payload


@override_settings(
    DEBUG=True,
    SECURE_SSL_REDIRECT=False,
    OWNER_EMAIL="owner@example.com",
    OWNER_API_TOKEN="a" * 64,
    STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
)
class SessionTests(TestCase):
    def setUp(self):
        self.owner = AppTests.user("owner@example.com")
        self.friend = AppTests.user("friend@example.com")
        AuthorizedEmail.objects.create(email=self.friend.email)
        self.puzzle = save_puzzle(payload())
        self.client.force_login(self.owner)
        response = self.post("/api/v1/sessions/", {"puzzle_id": str(self.puzzle.id)})
        self.assertEqual(response.status_code, 201)
        self.session = SolvingSession.objects.get(pk=response.json()["id"])
        self.url = f"/api/v1/sessions/{self.session.pk}/"
        self.join_url = f"/join/{self.session.invite_token}/"

    def post(self, path, data, client=None):
        return (client or self.client).post(path, json.dumps(data), content_type="application/json")

    def submit(self, answer="אבגדהוז", version=0, client=None):
        return self.post(
            self.url + "answers/",
            {
                "changes": [
                    {"direction": "across", "number": 1, "answer": answer, "version": version}
                ]
            },
            client,
        )

    def test_usage_metrics_count_only_committed_new_activity(self):
        def totals():
            return [
                REGISTRY.get_sample_value(name, labels) or 0
                for name, labels in (
                    ("higayon_groups_total", {}),
                    ("higayon_joins_total", {"kind": "registered"}),
                    ("higayon_joins_total", {"kind": "guest"}),
                    ("higayon_clue_edits_total", {"action": "completion"}),
                    ("higayon_clue_edits_total", {"action": "revision"}),
                    ("higayon_clue_edits_total", {"action": "withdrawal"}),
                )
            ]

        before = totals()
        with self.captureOnCommitCallbacks(execute=True):
            self.post("/api/v1/sessions/", {"puzzle_id": str(self.puzzle.id)})
            guest = Client()
            guest.post(self.join_url, {"name": "נועה"})
            guest.post(self.join_url, {"name": "נועה"})
            self.client.force_login(self.friend)
            self.client.post(self.join_url)
            self.client.post(self.join_url)
            self.submit()
            self.submit("חבגדהוז", 1)
            self.submit(None, 2)
            with transaction.atomic():
                self.submit("טבגדהוז", 3)
                transaction.set_rollback(True)
            self.assertEqual(totals(), before)
        self.assertEqual([a - b for a, b in zip(totals(), before, strict=True)], [1, 2, 1, 1, 1, 1])

    def test_explicit_join_and_membership_isolation(self):
        self.client.force_login(self.friend)
        self.assertEqual(self.client.get(self.join_url).status_code, 200)
        self.assertEqual(SessionMember.objects.count(), 1)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.submit().status_code, 404)
        self.assertEqual(self.client.post(self.join_url).status_code, 302)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        other = SolvingSession.objects.create(puzzle=self.puzzle, creator=self.owner)
        self.assertEqual(self.client.get(f"/api/v1/sessions/{other.pk}/").status_code, 404)
        self.assertEqual(ConfirmedAnswer.objects.count(), 0)

    @override_settings(
        SOCIALACCOUNT_PROVIDERS={"google": {"APPS": [{"client_id": "", "secret": ""}]}}
    )
    def test_unconfigured_invitation_offers_guest_only(self):
        guest = Client()
        for response in (guest.get(self.join_url), guest.post(self.join_url, {"name": ""})):
            self.assertNotContains(
                response, "/accounts/google/login/", status_code=response.status_code
            )
            self.assertContains(response, "הצטרפות כאורח", status_code=response.status_code)

    def test_guest_is_scoped_to_invitation_and_browser(self):
        guest = Client()
        self.assertContains(guest.get(self.join_url), "הצטרפות כאורח")
        self.assertEqual(guest.post(self.join_url, {"name": " "}).status_code, 400)
        guest.post(self.join_url, {"name": "נועה"})
        guest.post(self.join_url, {"name": "נועה"})
        self.assertEqual(SessionMember.objects.filter(guest_name="נועה").count(), 1)
        self.assertEqual(guest.get(self.url + "puzzle/").status_code, 200)
        self.assertEqual(self.submit(client=guest).status_code, 200)
        self.assertEqual(self.client.get(self.url).json()["counts"], {"across:1": 1})
        self.assertIsNone(guest.get(self.url).json()["invite_url"])
        self.assertEqual(guest.post(self.url + "revoke/").status_code, 403)
        self.assertEqual(guest.post("/api/v1/sessions/").status_code, 401)
        self.assertEqual(guest.get("/api/v1/puzzles/").status_code, 401)
        other = SolvingSession.objects.create(puzzle=self.puzzle, creator=self.owner)
        self.assertEqual(guest.get(f"/api/v1/sessions/{other.pk}/puzzle/").status_code, 401)
        second = Client()
        second.post(self.join_url, {"name": "נועה"})
        self.assertEqual(second.get(self.url).json()["own"], {})
        self.client.post(self.url + "revoke/")
        self.assertEqual(Client().post(self.join_url, {"name": "אור"}).status_code, 410)
        self.assertEqual(guest.get(self.url).status_code, 200)
        SessionMember.objects.filter(guest_name="נועה").delete()
        self.assertEqual(guest.get(self.url + "puzzle/").status_code, 404)
        self.assertEqual(self.submit(client=guest).status_code, 404)

    def test_counts_and_own_answers_do_not_disclose_others(self):
        self.assertEqual(self.submit("ךםןףץאב").status_code, 200)
        self.assertEqual(self.client.get(self.url).json()["counts"], {})
        self.client.force_login(self.friend)
        self.client.post(self.join_url)
        data = self.client.get(self.url).json()
        self.assertEqual(data["counts"], {"across:1": 1})
        self.assertEqual(data["own"], {})
        self.assertIsNone(data["invite_url"])
        self.assertNotIn("כמנפצאב", json.dumps(data, ensure_ascii=False))
        self.client.force_login(self.owner)
        self.assertEqual(self.submit(None, 1).status_code, 200)
        self.assertEqual(self.submit(version=0).status_code, 409)
        self.client.force_login(self.friend)
        self.assertEqual(self.client.get(self.url).json()["counts"], {})

    def test_invalid_or_conflicting_batch_is_atomic(self):
        self.submit()
        original = ConfirmedAnswer.objects.get().answer
        for change in [
            {"direction": "across", "number": 5, "answer": "א", "version": 0},
            {"direction": "across", "number": 5, "answer": "abc", "version": 0},
            {"direction": "across", "number": True, "answer": None, "version": 0},
            {"direction": "across", "number": 5, "version": 0},
        ]:
            response = self.post(
                self.url + "answers/",
                {
                    "changes": [
                        {"direction": "across", "number": 1, "answer": "זוהדגבא", "version": 1},
                        change,
                    ]
                },
            )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(ConfirmedAnswer.objects.get().answer, original)
        response = self.post(
            self.url + "answers/",
            {
                "changes": [
                    {"direction": "across", "number": 5, "answer": "אבג", "version": 0},
                    {"direction": "across", "number": 1, "answer": None, "version": 0},
                ]
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(ConfirmedAnswer.objects.count(), 1)
        self.assertEqual(self.submit("זוהדגבא", 1).status_code, 200)
        self.assertEqual(self.submit("אבגדהוז", 1).status_code, 409)
        self.assertEqual(ConfirmedAnswer.objects.get().answer, "זוהדגבא")

    def test_revoke_and_authorization(self):
        self.client.force_login(self.friend)
        self.client.post(self.join_url)
        self.assertEqual(self.client.post(self.url + "revoke/").status_code, 403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(self.url + "revoke/").status_code, 200)
        self.assertEqual(self.client.get(self.join_url).status_code, 410)
        self.client.force_login(self.friend)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        AuthorizedEmail.objects.filter(email=self.friend.email).delete()
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(self.submit().status_code, 401)

    def test_csrf_and_token_cannot_submit_player_answers(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(self.submit(client=client).status_code, 403)
        self.assertEqual(client.post(self.join_url).status_code, 403)
        self.assertEqual(
            self.client.get(self.url, HTTP_AUTHORIZATION="Bearer " + "a" * 64).status_code, 401
        )
        client.get(f"/sessions/{self.session.pk}/")
        response = client.post(
            self.url + "answers/",
            json.dumps(
                {
                    "changes": [
                        {"direction": "across", "number": 1, "answer": "אבגדהוז", "version": 0}
                    ]
                }
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        )
        self.assertEqual(response.status_code, 200)

    def test_invalid_creation_and_read_requests_do_not_write(self):
        for value in ["bad", [], {}, 123]:
            self.assertEqual(self.post("/api/v1/sessions/", {"puzzle_id": value}).status_code, 400)
        self.client.get(self.url)
        self.client.get(f"/sessions/{self.session.pk}/")
        self.assertEqual(ConfirmedAnswer.objects.count(), 0)


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False, OWNER_EMAIL="owner@example.com")
class ConcurrentSessionTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_simultaneous_first_confirmations_cannot_overwrite(self):
        user = AppTests.user("owner@example.com")
        session = SolvingSession.objects.create(puzzle=save_puzzle(payload()), creator=user)
        SessionMember.objects.create(session=session, user=user)
        clients = [Client(), Client()]
        for client in clients:
            client.force_login(user)
        barrier = Barrier(2)

        def submit(client):
            try:
                barrier.wait(timeout=10)
                return client.post(
                    f"/api/v1/sessions/{session.pk}/answers/",
                    json.dumps(
                        {
                            "changes": [
                                {
                                    "direction": "across",
                                    "number": 1,
                                    "answer": "אבגדהוז",
                                    "version": 0,
                                }
                            ]
                        }
                    ),
                    content_type="application/json",
                ).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(submit, clients))
        self.assertEqual(sorted(statuses), [200, 409])
        self.assertEqual(ConfirmedAnswer.objects.get().version, 1)
