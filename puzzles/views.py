import json
import secrets
from functools import wraps

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, RequestDataTooBig
from django.db import connection, transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt, csrf_protect, ensure_csrf_cookie

from .auth import google_configured, invited, owner
from .domain import Invalid, metadata, save_puzzle, save_solutions, serialize
from .models import Puzzle


def error(message, status):
    return JsonResponse({"error": message}, status=status)


def api_auth(view):
    @csrf_exempt
    @wraps(view)
    def dispatch(request, *args, **kwargs):
        authorization = request.headers.get("Authorization")
        if authorization is not None:
            token = authorization.removeprefix("Bearer ")
            if (
                not authorization.startswith("Bearer ")
                or not settings.OWNER_API_TOKEN
                or not settings.OWNER_EMAIL
                or not invited_owner_config()
                or not secrets.compare_digest(token.encode(), settings.OWNER_API_TOKEN.encode())
            ):
                return error("פרטי ההזדהות אינם תקינים.", 401)
            request.api_owner = True
            return view(request, *args, **kwargs)
        if not invited(request.user):
            return error("נדרשת כניסה באמצעות חשבון מוזמן.", 401)
        request.api_owner = owner(request.user)
        return csrf_protect(view)(request, *args, **kwargs)

    return dispatch


def invited_owner_config():
    return settings.OWNER_EMAIL in settings.ALLOWED_EMAILS


def body(request):
    if request.content_type != "application/json":
        raise Invalid("יש לשלוח תוכן JSON.")
    try:
        return json.loads(request.body)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise Invalid("תוכן JSON אינו תקין.") from None


@api_auth
def puzzles_api(request, puzzle_id=None, latest=False, solutions=False):
    try:
        if request.method not in (
            ["PUT"]
            if solutions
            else ["GET", "PATCH"]
            if puzzle_id
            else ["GET"]
            if latest
            else ["GET", "POST"]
        ):
            return error("פעולה זו אינה נתמכת.", 405)
        if request.method != "GET" and not request.api_owner:
            return error("הפעולה מותרת לבעלים בלבד.", 403)
        if request.method == "GET":
            if latest:
                puzzle = Puzzle.objects.first()
                return JsonResponse(serialize(puzzle) if puzzle else {"puzzle": None})
            if puzzle_id:
                return JsonResponse(serialize(Puzzle.objects.get(pk=puzzle_id)))
            return JsonResponse({"puzzles": [metadata(p) for p in Puzzle.objects.all()]})
        with transaction.atomic():
            puzzle = Puzzle.objects.select_for_update().get(pk=puzzle_id) if puzzle_id else None
            if solutions:
                save_solutions(puzzle, body(request))
                return JsonResponse({"message": "הפתרונות נשמרו."})
            puzzle = save_puzzle(body(request), puzzle)
            return JsonResponse(serialize(puzzle), status=201 if request.method == "POST" else 200)
    except RequestDataTooBig:
        return error("הבקשה גדולה מדי. הגודל המרבי הוא 128 קילובייט.", 413)
    except ObjectDoesNotExist:
        return error("התשבץ לא נמצא.", 404)
    except Invalid as exc:
        return error(str(exc), 400)


@ensure_csrf_cookie
def home(request, editor=False):
    if not invited(request.user):
        return redirect("/login/")
    if editor and not owner(request.user):
        return render(request, "message.html", {"message": "העריכה מותרת לבעלים בלבד."}, status=403)
    return render(
        request, "editor.html" if editor else "solver.html", {"is_owner": owner(request.user)}
    )


def login(request):
    return render(
        request,
        "login.html",
        {"google_configured": google_configured()},
    )


def csrf_failure(request, reason=""):
    if request.path.startswith("/api/"):
        return error("אימות האבטחה נכשל. יש לרענן את הדף ולנסות שוב.", 403)
    return render(
        request, "message.html", {"message": "אימות האבטחה נכשל. יש לרענן את הדף."}, status=403
    )


def health(request, ready=False):
    if ready:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            return error("מסד הנתונים אינו זמין.", 503)
    return JsonResponse({"status": "תקין"})


@api_auth
def template_api(request):
    from .grid import TEMPLATE

    if request.method != "GET":
        return error("פעולה זו אינה נתמכת.", 405)
    return JsonResponse(TEMPLATE)
