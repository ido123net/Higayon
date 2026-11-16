from django.urls import include, path

from puzzles import views

urlpatterns = [
    path("", views.home),
    path("editor/", views.home, {"editor": True}),
    path("login/", views.login),
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
