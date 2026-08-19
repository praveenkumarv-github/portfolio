from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from dashboard.views import update_metal_prices


def _with_messages(request):
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


def test_metal_refresh_does_not_mutate_state_over_get():
    request = _with_messages(RequestFactory().get("/metal-prices/?refresh=1"))
    with patch("dashboard.views.refresh_prices") as refresh:
        response = update_metal_prices(request)
    assert response.status_code == 302
    refresh.assert_not_called()


def test_metal_refresh_uses_post_action():
    request = _with_messages(RequestFactory().post("/metal-prices/", {"action": "refresh"}))
    with patch(
        "dashboard.views.refresh_prices",
        return_value={"gold": (9000.0, "Live"), "silver": (110.0, "Live")},
    ) as refresh:
        response = update_metal_prices(request)
    assert response.status_code == 302
    refresh.assert_called_once_with()