"""Session-only sharing: no browser draft endpoint and no other users' answers."""

from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, RequestDataTooBig, ValidationError
from django.db import transaction
from django.db.models import Count, F, Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie

from .auth import invited, owner
from .domain import Invalid, normalize, object_fields
from .grid import LENGTHS, SLOTS
from .models import AuthorizedEmail, ConfirmedAnswer, Puzzle, SessionMember, SolvingSession
from .views import body, error


def member_api(view):
    @wraps(view)
    @csrf_protect
    def dispatch(request, *args, **kwargs):
        if request.headers.get("Authorization") is not None or not invited(request.user):
            return error("נדרשת כניסה באמצעות חשבון Google מורשה.", 401)
        try:
            return view(request, *args, **kwargs)
        except ObjectDoesNotExist:
            return error("המפגש או התשבץ לא נמצאו, או שאין לך גישה אליהם.", 404)
        except RequestDataTooBig:
            return error("הבקשה גדולה מדי.", 413)
        except Invalid as exc:
            return error(str(exc), 400)

    return dispatch


def membership(request, session_id):
    return SessionMember.objects.select_related("session__puzzle").get(
        session_id=session_id, user=request.user
    )


def session_info(request, session):
    manager = session.creator_id == request.user.pk or owner(request.user)
    return {
        "id": str(session.id),
        "puzzle_id": str(session.puzzle_id),
        "can_manage": manager,
        "invite_active": session.invite_active,
        "invite_url": request.build_absolute_uri(f"/join/{session.invite_token}/")
        if manager and session.invite_active
        else None,
    }


@member_api
def create(request):
    if request.method != "POST":
        return error("פעולה זו אינה נתמכת.", 405)
    data = body(request)
    object_fields(data, ["puzzle_id"])
    if set(data) != {"puzzle_id"} or not isinstance(data.get("puzzle_id"), str):
        raise Invalid("יש לציין את התשבץ.")
    try:
        puzzle = Puzzle.objects.get(pk=data.get("puzzle_id"))
    except (ValueError, TypeError, ValidationError):
        raise Invalid("מזהה התשבץ אינו תקין.") from None
    with transaction.atomic():
        session = SolvingSession.objects.create(puzzle=puzzle, creator=request.user)
        SessionMember.objects.create(session=session, user=request.user)
    return JsonResponse(session_info(request, session), status=201)


@ensure_csrf_cookie
def join(request, token):
    if not invited(request.user):
        return redirect("/accounts/google/login/?" + urlencode({"next": request.path}))
    try:
        with transaction.atomic():
            session = (
                SolvingSession.objects.select_for_update()
                .select_related("puzzle")
                .get(invite_token=token)
            )
            if not session.invite_active:
                return render(
                    request, "message.html", {"message": "קישור ההצטרפות בוטל."}, status=410
                )
            if request.method == "POST":
                SessionMember.objects.get_or_create(session=session, user=request.user)
                return redirect(f"/sessions/{session.id}/")
            if request.method != "GET":
                return error("פעולה זו אינה נתמכת.", 405)
            return render(request, "sessions/join.html", {"session": session})
    except ObjectDoesNotExist:
        return render(request, "message.html", {"message": "קישור ההצטרפות לא נמצא."}, status=404)


@ensure_csrf_cookie
def solver(request, session_id):
    if not invited(request.user):
        return redirect("/accounts/google/login/?" + urlencode({"next": request.path}))
    try:
        member = membership(request, session_id)
    except ObjectDoesNotExist:
        return render(
            request, "message.html", {"message": "יש להצטרף למפגש דרך קישור ההזמנה."}, status=403
        )
    return render(
        request,
        "solver.html",
        {
            "is_owner": owner(request.user),
            "session_id": str(member.session_id),
        },
    )


@member_api
def state(request, session_id):
    if request.method != "GET":
        return error("פעולה זו אינה נתמכת.", 405)
    member = membership(request, session_id)
    authorized = AuthorizedEmail.objects.values("email")
    answers = ConfirmedAnswer.objects.filter(member__session_id=session_id)
    counts = (
        answers.exclude(member=member)
        .exclude(answer="")
        .filter(
            Q(member__user__email__in=authorized) | Q(member__user__email=settings.OWNER_EMAIL),
            member__user__is_active=True,
            member__user__socialaccount__provider="google",
            member__user__emailaddress__verified=True,
            member__user__emailaddress__email__iexact=F("member__user__email"),
        )
        .values("direction", "number")
        .annotate(count=Count("id", distinct=True))
    )
    own = {
        f"{a.direction}:{a.number}": {"answer": a.answer, "version": a.version}
        for a in answers.filter(member=member)
    }
    return JsonResponse(
        {
            **session_info(request, member.session),
            "counts": {f"{c['direction']}:{c['number']}": c["count"] for c in counts},
            "own": own,
        }
    )


@member_api
def confirm(request, session_id):
    if request.method != "POST":
        return error("פעולה זו אינה נתמכת.", 405)
    data = body(request)
    object_fields(data, ["changes"])
    changes = data.get("changes")
    if not isinstance(changes, list) or not 1 <= len(changes) <= len(SLOTS):
        raise Invalid("יש לכלול לפחות הגדרה אחת לסנכרון.")
    seen = set()
    cleaned = []
    for change in changes:
        object_fields(change, ["direction", "number", "answer", "version"])
        if set(change) != {"direction", "number", "answer", "version"}:
            raise Invalid("חסרים פרטי התשובה או הגרסה.")
        d, n, answer, version = (
            change.get(k) for k in ("direction", "number", "answer", "version")
        )
        if (
            not isinstance(d, str)
            or type(n) is not int
            or n not in LENGTHS.get(d, {})
            or (d, n) in seen
            or type(version) is not int
            or version < 0
        ):
            raise Invalid("פרטי ההגדרה או הגרסה אינם תקינים.")
        if answer is not None:
            if not isinstance(answer, str):
                raise Invalid("התשובה אינה תקינה.")
            answer = normalize(answer)
            if len(answer) != LENGTHS[d][n] or not all("א" <= c <= "ת" for c in answer):
                raise Invalid("יש למלא אות עברית אחת בכל משבצת של ההגדרה.")
        cleaned.append((d, n, answer or "", version))
        seen.add((d, n))
    with transaction.atomic():
        # Serialize all submissions by this member, including creation of new answers.
        member = SessionMember.objects.select_for_update().get(
            session_id=session_id, user=request.user
        )
        current = {
            (a.direction, a.number): a for a in ConfirmedAnswer.objects.filter(member=member)
        }
        if any((current[d, n].version if (d, n) in current else 0) != v for d, n, _, v in cleaned):
            return error("התשובות עודכנו בכרטיסייה או במכשיר אחר.", 409)
        result = {}
        for d, n, answer, version in cleaned:
            ConfirmedAnswer.objects.update_or_create(
                member=member,
                direction=d,
                number=n,
                defaults={"answer": answer, "version": version + 1},
            )
            result[f"{d}:{n}"] = {"answer": answer, "version": version + 1}
    return JsonResponse({"own": result})


@member_api
def revoke(request, session_id):
    if request.method != "POST":
        return error("פעולה זו אינה נתמכת.", 405)
    member = membership(request, session_id)
    if member.session.creator_id != request.user.pk and not owner(request.user):
        return error("רק יוצר המפגש או הבעלים יכולים לבטל קישור.", 403)
    SolvingSession.objects.filter(pk=session_id).update(invite_active=False)
    return JsonResponse({"message": "קישור ההצטרפות בוטל. המשתתפים הקיימים נשארו במפגש."})
