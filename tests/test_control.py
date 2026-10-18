import pytest
from pretix.base.models import Team, User

from pretix_roomsharing.models import OrderRoom


@pytest.fixture
def room(event):
    return event.rooms.create(name="Room 1", password="secret")


def _login(client, organizer, **permissions):
    user = User.objects.create_user("staff@example.com", "staff")
    team = Team.objects.create(organizer=organizer, name="Staff", all_events=True)
    for k, v in permissions.items():
        setattr(team, k, v)
    team.save()
    team.members.add(user)
    client.login(email="staff@example.com", password="staff")


def _change_url(order):
    return f"/control/event/{order.event.organizer.slug}/{order.event.slug}/orders/{order.code}/room"


@pytest.mark.django_db
def test_order_page_shows_change_link(client, organizer, order):
    _login(client, organizer, all_event_permissions=True)
    r = client.get(f"/control/event/dummy/dummy/orders/{order.code}/")
    assert r.status_code == 200
    assert _change_url(order) in r.content.decode()


@pytest.mark.django_db
def test_order_page_hides_change_link_without_permission(client, organizer, order):
    _login(client, organizer, limit_event_permissions={"event.orders:read": True})
    r = client.get(f"/control/event/dummy/dummy/orders/{order.code}/")
    assert r.status_code == 200
    assert _change_url(order) not in r.content.decode()


@pytest.mark.django_db
def test_control_room_change(client, organizer, order, room):
    _login(client, organizer, all_event_permissions=True)
    r = client.get(_change_url(order))
    assert r.status_code == 200

    r = client.post(_change_url(order), {"room": room.pk, "is_admin": "on"})
    assert r.status_code == 302
    orderroom = OrderRoom.objects.get(order=order)
    assert orderroom.room == room
    assert orderroom.is_admin


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url,permission,status",
    [
        ("/control/event/dummy/dummy/rooms/", "event.orders:read", 403),
        ("/control/event/dummy/dummy/rooms/", "event.orders:write", 200),
        ("/control/event/dummy/dummy/rooms/stats/", "event.orders:read", 200),
        ("/control/event/dummy/dummy/roomsharing/", "event.orders:write", 403),
        (
            "/control/event/dummy/dummy/roomsharing/",
            "event.settings.general:write",
            200,
        ),
    ],
)
def test_control_permissions(client, organizer, event, url, permission, status):
    _login(client, organizer, limit_event_permissions={permission: True})
    assert client.get(url).status_code == status


@pytest.mark.django_db
def test_rooms_nav_hidden_without_permission(client, organizer, event):
    _login(client, organizer, limit_event_permissions={"event.orders:read": True})
    r = client.get("/control/event/dummy/dummy/")
    assert "/control/event/dummy/dummy/rooms/" not in r.content.decode()


@pytest.mark.django_db
def test_plugin_page_links(client, organizer, event):
    _login(client, organizer, all_event_permissions=True)
    content = client.get("/control/event/dummy/dummy/settings/plugins").content.decode()
    assert "/control/event/dummy/dummy/roomsharing/" in content
    assert "/control/event/dummy/dummy/rooms/" in content


@pytest.mark.django_db
def test_room_log_entries(event, room, order):
    room.log_action("pretix_roomsharing.room.changed", data={})
    order.log_action("pretix_roomsharing.order.joined", data={"room": room.pk})
    room_entry, order_entry = (
        room.all_logentries().get(),
        order.all_logentries().get(),
    )
    assert room_entry.display() == "The room has been changed."
    assert f"/control/event/dummy/dummy/rooms/{room.pk}/" in room_entry.display_object
    assert order_entry.display() == "The user joined a room."


@pytest.mark.django_db
def test_rooms_nav(client, organizer, event):
    _login(client, organizer, all_event_permissions=True)
    content = client.get("/control/event/dummy/dummy/rooms/").content.decode()
    assert "/control/event/dummy/dummy/rooms/stats/" in content


@pytest.mark.django_db
def test_stats_page(client, organizer, event, order):
    _login(client, organizer, all_event_permissions=True)
    r = client.get("/control/event/dummy/dummy/rooms/stats/")
    assert r.status_code == 200
    content = r.content.decode()
    assert "Room statistics" in content
    # Rendered inside the backend layout, so the event navigation is present.
    assert "/control/event/dummy/dummy/rooms/" in content
    total = next(
        row for row in r.context["ticket_stats"] if row[0] == "All tickets, total"
    )
    assert sum(sum(v.values()) for v in total[1].values()) == 1


@pytest.mark.django_db
def test_delete_page_cancel_link(client, organizer, room):
    _login(client, organizer, all_event_permissions=True)
    r = client.get(f"/control/event/dummy/dummy/rooms/{room.pk}/delete")
    assert (
        'href="/control/event/dummy/dummy/rooms/" class="btn btn-default btn-cancel"'
        in (r.content.decode())
    )
