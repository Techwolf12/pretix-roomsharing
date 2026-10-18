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
