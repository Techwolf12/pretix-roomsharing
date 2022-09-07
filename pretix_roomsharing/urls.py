from django.conf.urls import url

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
    url(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/roomsharing/",
        SettingsView.as_view(),
        name="control.room.settings",
    ),
    url(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/orders/(?P<code>[0-9A-Z]+)/room$",
        ControlRoomChange.as_view(),
        name="control.order.room.modify",
    ),
    url(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/rooms/stats/$",
        StatsView.as_view(),
        name="event.stats",
    ),
    url(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/rooms/$",
        RoomList.as_view(),
        name="event.room.list",
    ),
    url(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/rooms/(?P<pk>\d+)/$",
        RoomDetail.as_view(),
        name="event.room.detail",
    ),
    url(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/rooms/(?P<pk>\d+)/delete$",
        RoomDelete.as_view(),
        name="event.room.delete",
    ),
    url(
        r"^metrics/rooms/(?P<organizer>[^/]+)/(?P<event>[^/]+)/$",
        MetricsView.as_view(),
        name="metrics",
    ),
]

event_patterns = [
    url(
        r"^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/room/modify$",
        OrderRoomChange.as_view(),
        name="event.order.room.modify",
    ),
]
