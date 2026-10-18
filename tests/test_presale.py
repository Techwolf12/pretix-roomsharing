import pytest
from datetime import timedelta
from django.utils.timezone import now
from pretix.base.models import Order

from pretix_roomsharing.models import OrderRoom, Room
from pretix_roomsharing.signals import order_info
from pretix_roomsharing.utils import can_change_room


@pytest.fixture
def room_order(event, item, order):
    event.live = True
    event.save()
    event.settings.roomsharing__products = [str(item.pk)]
    return order


def _change_url(order, secret=None):
    return f"/dummy/dummy/order/{order.code}/{secret or order.secret}/room/modify"


@pytest.mark.django_db
def test_change_page_wrong_secret(client, room_order):
    r = client.get(_change_url(room_order, secret="wrongsecret"))
    assert r.status_code == 404


@pytest.mark.django_db
def test_change_page_wrong_secret_post(client, room_order):
    r = client.post(
        _change_url(room_order, secret="wrongsecret"),
        {"room_mode": "create", "create-name": "Room", "create-password": "secret"},
    )
    assert r.status_code == 404
    assert not Room.objects.exists()


@pytest.mark.django_db
def test_change_page_create_room(client, room_order):
    r = client.get(_change_url(room_order))
    assert r.status_code == 200

    r = client.post(
        _change_url(room_order),
        {"room_mode": "create", "create-name": "Room", "create-password": "secret"},
    )
    assert r.status_code == 302
    orderroom = OrderRoom.objects.get(order=room_order)
    assert orderroom.room.name == "Room"
    assert orderroom.is_admin


@pytest.mark.django_db
@pytest.mark.parametrize("status", [Order.STATUS_CANCELED, Order.STATUS_EXPIRED])
def test_change_page_blocked_for_inactive_order(client, room_order, status):
    room_order.status = status
    room_order.save()
    r = client.post(
        _change_url(room_order),
        {"room_mode": "create", "create-name": "Room", "create-password": "secret"},
    )
    assert r.status_code == 302
    assert not OrderRoom.objects.filter(order=room_order).exists()


@pytest.mark.django_db
def test_change_page_blocked_after_modification_deadline(client, event, room_order):
    event.settings.last_order_modification_date = now() - timedelta(days=1)
    r = client.post(
        _change_url(room_order),
        {"room_mode": "create", "create-name": "Room", "create-password": "secret"},
    )
    assert r.status_code == 302
    assert not OrderRoom.objects.filter(order=room_order).exists()


@pytest.mark.django_db
def test_can_change_room(event, room_order):
    assert can_change_room(room_order)
    room_order.status = Order.STATUS_PAID
    assert can_change_room(room_order)
    room_order.status = Order.STATUS_CANCELED
    assert not can_change_room(room_order)


@pytest.mark.django_db
def test_order_info_hides_change_link_for_canceled_order(event, room_order):
    room_order.status = Order.STATUS_CANCELED
    room_order.save()
    assert "Change details" not in order_info(event, order=room_order)


@pytest.mark.django_db
def test_join_form_missing_password_error_on_password_field(event):
    from pretix_roomsharing.checkoutflow import RoomJoinForm

    event.rooms.create(name="Room", password="secret")
    form = RoomJoinForm(
        event=event, prefix="join", data={"join-name": "Room", "join-password": ""}
    )
    assert not form.is_valid()
    assert "password" in form.errors
    assert "name" not in form.errors
