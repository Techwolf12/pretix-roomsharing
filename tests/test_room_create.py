import pytest
from pretix.base.models import Order, Team, User

from pretix_roomsharing.models import OrderRoom, Room

ROOMS = "/control/event/dummy/dummy/rooms"


def _login(client, organizer, **permissions):
    user = User.objects.create_user("staff@example.com", "staff")
    team = Team.objects.create(organizer=organizer, name="Staff", all_events=True)
    for k, v in permissions.items():
        setattr(team, k, v)
    team.save()
    team.members.add(user)
    client.login(email="staff@example.com", password="staff")


@pytest.fixture
def staff(client, organizer):
    _login(client, organizer, all_event_permissions=True)
    return client


@pytest.fixture
def paid_order(order):
    order.status = Order.STATUS_PAID
    order.save()
    return order


@pytest.mark.django_db
def test_room_list_links_to_create(staff, event):
    assert f"{ROOMS}/add/" in staff.get(f"{ROOMS}/").content.decode()


@pytest.mark.django_db
def test_create_empty_room(staff, event, item):
    event.room_products.create(item=item, max_people=2)
    assert staff.get(f"{ROOMS}/add/").status_code == 200

    r = staff.post(
        f"{ROOMS}/add/",
        {
            "name": "Overflow",
            "password": "",
            "room_number": "205",
            "room_type": f"{item.pk}_",
        },
    )
    room = Room.objects.get(name="Overflow")
    assert r.status_code == 302
    assert r["Location"] == f"{ROOMS}/{room.pk}/"
    assert room.event == event
    assert room.room_number == "205"
    assert room.item == item
    assert not room.orderrooms.exists()
    assert room.all_logentries().get().action_type == "pretix_roomsharing.room.created"


@pytest.mark.django_db
def test_create_room_rejects_duplicate_name(staff, event):
    event.rooms.create(name="Overflow", password="secret")
    r = staff.post(
        f"{ROOMS}/add/", {"name": "Overflow", "password": "", "room_type": ""}
    )
    assert r.status_code == 200
    assert "Duplicate room name" in r.content.decode()
    assert event.rooms.count() == 1


@pytest.mark.django_db
def test_create_room_requires_write_permission(client, organizer, event):
    _login(client, organizer, limit_event_permissions={"event.orders:read": True})
    assert client.get(f"{ROOMS}/add/").status_code == 403


@pytest.mark.django_db
def test_add_order_moves_it_from_other_room(staff, event, paid_order):
    old = event.rooms.create(name="Old", password="secret")
    OrderRoom.objects.create(order=paid_order, room=old, is_admin=True)
    new = event.rooms.create(name="New", password="")

    r = staff.post(f"{ROOMS}/{new.pk}/add-order", {"order": paid_order.code.lower()})
    assert r.status_code == 302
    orderroom = OrderRoom.objects.get(order=paid_order)
    assert orderroom.room == new
    assert not orderroom.is_admin
    entry = paid_order.all_logentries().get(
        action_type="pretix_roomsharing.order.moved"
    )
    assert entry.display() == 'The order has been moved to the room "New".'


@pytest.mark.django_db
def test_add_order_accepts_full_order_code(staff, event, paid_order):
    room = event.rooms.create(name="New", password="")
    staff.post(f"{ROOMS}/{room.pk}/add-order", {"order": f"DUMMY-{paid_order.code}"})
    assert OrderRoom.objects.get(order=paid_order).room == room


@pytest.mark.django_db
def test_add_unknown_order(staff, event):
    room = event.rooms.create(name="New", password="")
    r = staff.post(f"{ROOMS}/{room.pk}/add-order", {"order": "NOPE1"}, follow=True)
    assert "There is no order with this code." in r.content.decode()
    assert not room.orderrooms.exists()


@pytest.mark.django_db
def test_add_order_warns_when_over_capacity(staff, event, item, paid_order):
    event.room_products.create(item=item, max_people=1)
    room = event.rooms.create(name="Full", password="", item=item)
    other = Order.objects.create(
        event=event,
        email="other@example.com",
        status=Order.STATUS_PAID,
        datetime=paid_order.datetime,
        expires=paid_order.expires,
        total=paid_order.total,
        sales_channel=paid_order.sales_channel,
    )
    other.positions.create(item=item, price=paid_order.total)
    OrderRoom.objects.create(order=other, room=room)

    r = staff.post(
        f"{ROOMS}/{room.pk}/add-order", {"order": paid_order.code}, follow=True
    )
    assert OrderRoom.objects.get(order=paid_order).room == room
    assert "more people than its maximum of 1" in r.content.decode()


@pytest.mark.django_db
def test_add_order_requires_write_permission(client, organizer, event, paid_order):
    _login(client, organizer, limit_event_permissions={"event.orders:read": True})
    room = event.rooms.create(name="New", password="")
    r = client.post(f"{ROOMS}/{room.pk}/add-order", {"order": paid_order.code})
    assert r.status_code == 403
    assert not OrderRoom.objects.exists()


@pytest.mark.django_db
def test_order_page_room_change_is_logged(staff, event, paid_order):
    room = event.rooms.create(name="New", password="")
    staff.post(
        f"/control/event/dummy/dummy/orders/{paid_order.code}/room",
        {"room": room.pk},
    )
    assert (
        paid_order.all_logentries()
        .filter(action_type="pretix_roomsharing.order.moved")
        .exists()
    )
