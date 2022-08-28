from django.conf.urls import url

from .views import SettingsView

urlpatterns = [
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/roomsharing/',
        SettingsView.as_view(),
        name="roomsharing__settings",),
]