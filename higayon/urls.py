from django.urls import include, path

from puzzles import sessions, views
from puzzles.admin import owner_admin_site

urlpatterns = [
    path("", views.home),
    path("join/<uuid:token>/", sessions.join),
    path("sessions/<uuid:session_id>/", sessions.solver),
    path("sessions/<uuid:session_id>/share/", sessions.share),
    path("api/v1/sessions/<uuid:session_id>/puzzle/", sessions.session_puzzle),
    path("api/v1/sessions/", sessions.create),
    path("api/v1/sessions/<uuid:session_id>/", sessions.state),
    path("api/v1/sessions/<uuid:session_id>/answers/", sessions.confirm),
    path("api/v1/sessions/<uuid:session_id>/revoke/", sessions.revoke),
    path("editor/", views.home, {"editor": True}),
    path("login/", views.login),
    path("admin/", owner_admin_site.urls),
    path("accounts/", include("allauth.urls")),
    path("api/v1/template/", views.template_api),
    path("api/v1/puzzles/", views.puzzles_api),
    path("api/v1/puzzles/latest/", views.puzzles_api, {"latest": True}),
    path("api/v1/puzzles/<uuid:puzzle_id>/", views.puzzles_api),
    path("api/v1/puzzles/<uuid:puzzle_id>/solutions/", views.puzzles_api, {"solutions": True}),
    path("health/live/", views.health),
    path("health/ready/", views.health, {"ready": True}),
]


def handler404(request, exception):
    return views.render(request, "message.html", {"message": "הדף לא נמצא."}, status=404)


def handler500(request):
    return views.render(
        request, "message.html", {"message": "אירעה תקלה. אפשר לנסות שוב מאוחר יותר."}, status=500
    )
