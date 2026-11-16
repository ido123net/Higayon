from django.utils.cache import patch_cache_control, patch_vary_headers


class PrivateResponsesMiddleware:
    """Do not leave account-specific pages or definitions in shared/browser caches."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith(("/static/", "/health/")):
            patch_cache_control(response, private=True, no_store=True, max_age=0)
            patch_vary_headers(response, ["Cookie"])
        return response
