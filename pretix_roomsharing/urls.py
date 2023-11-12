from django.urls import path, re_path

from .views import (
    ControlRoomChange,
    MetricsView,
    OrderRoomChange,
    RoomDelete,
    RoomDetail,
    RoomList,
    SettingsView,
    StatsView,
)

urlpatterns = [
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/roomsharing/",
        SettingsView.as_view(),
        name="control.room.settings",
    ),
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/orders/(?P<code>[0-9A-Z]+)/room$",
        ControlRoomChange.as_view(),
        name="control.order.room.modify",
    ),
    url(
        r"control/event/<str:organizer>/<str:event>/rooms/stats/",
        StatsView.as_view(),
        name="event.stats",
    ),
    url(
        r"control/event/<str:organizer>/<str:event>/rooms/",
        RoomList.as_view(),
        name="event.room.list",
    ),
    url(
        r"control/event/<str:organizer>/<str:event>/rooms/<int:pk>/",
        RoomDetail.as_view(),
        name="event.room.detail",
    ),
    url(
        r"control/event/<str:organizer>/<str:event>/rooms/<int:pk>/delete",
        RoomDelete.as_view(),
        name="event.room.delete",
    ),
    url(
        r"metrics/rooms/<str:organizer>/<str:event>/",
        MetricsView.as_view(),
        name="metrics",
    ),
]

event_patterns = [
    re_path(
        r"^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/room/modify$",
        OrderRoomChange.as_view(),
        name="event.order.room.modify",
    ),
]
