import pytest
from datetime import timedelta
from decimal import Decimal
from django.utils.timezone import now
from pretix.base.models import Order, Team, User

from pretix_roomsharing.models import OrderRoom
from pretix_roomsharing.signals import order_info
from pretix_roomsharing.views import RoomForm


@pytest.fixture
def hotel(event):
    item = event.items.create(name="Hotel", default_price=Decimal("100.00"))
    single = item.variations.create(value="Single")
    double = item.variations.create(value="Double")
    event.room_products.create(item=item, variation=single, max_people=2)
    event.room_products.create(item=item, variation=double)
    return item, single, double


@pytest.fixture
def room(event, hotel):
    item, single, _ = hotel
    room = event.rooms.create(
        name="Room 1", password="secret", item=item, variation=single
    )
    order = Order.objects.create(
        event=event,
        email="dummy@example.com",
        status=Order.STATUS_PAID,
        datetime=now(),
        expires=now() + timedelta(days=10),
        total=Decimal("0.00"),
        sales_channel=event.organizer.sales_channels.get(identifier="web"),
    )
    order.positions.create(item=item, variation=single, price=Decimal("0.00"))
    OrderRoom.objects.create(order=order, room=room, is_admin=True)
    return room


@pytest.fixture
def staff_client(client, organizer):
    user = User.objects.create_user("staff@example.com", "staff")
    team = Team.objects.create(
        organizer=organizer, name="Staff", all_events=True, all_event_permissions=True
    )
    team.members.add(user)
    client.login(email="staff@example.com", password="staff")
    return client


def _form_data(room, room_type):
    return {"name": room.name, "password": room.password, "room_type": room_type}


def test_room_form_choices(event, room, hotel):
    item, single, double = hotel
    form = RoomForm(event=event, instance=room)
    choices = dict(form.fields["room_type"].choices)
    assert choices[f"{item.pk}_{single.pk}"] == "Hotel – Single"
    assert choices[f"{item.pk}_{double.pk}"] == "Hotel – Double"
    assert "" in choices
    assert form.fields["room_type"].initial == f"{item.pk}_{single.pk}"


def test_room_form_changes_type(event, room, hotel):
    item, _, double = hotel
    form = RoomForm(
        event=event, instance=room, data=_form_data(room, f"{item.pk}_{double.pk}")
    )
    assert form.is_valid(), form.errors
    form.save()
    room.refresh_from_db()
    assert (room.item, room.variation) == (item, double)

    form = RoomForm(event=event, instance=room, data=_form_data(room, ""))
    assert form.is_valid(), form.errors
    form.save()
    room.refresh_from_db()
    assert room.item is None and room.variation is None


def test_room_form_product_without_variation(event, item, room):
    event.room_products.create(item=item)
    form = RoomForm(event=event, instance=room, data=_form_data(room, f"{item.pk}_"))
    assert form.is_valid(), form.errors
    form.save()
    room.refresh_from_db()
    assert (room.item, room.variation) == (item, None)


def test_room_form_keeps_type_that_is_no_longer_a_room_product(event, room, hotel):
    item, single, _ = hotel
    event.room_products.filter(variation=single).delete()
    form = RoomForm(event=event, instance=room)
    assert f"{item.pk}_{single.pk}" in dict(form.fields["room_type"].choices)


@pytest.mark.django_db
def test_room_list_shows_type_and_occupancy(staff_client, room):
    content = staff_client.get("/control/event/dummy/dummy/rooms/").content.decode()
    assert "Hotel – Single" in content
    assert "1 / 2" in content


@pytest.mark.django_db
def test_room_detail_shows_occupancy(staff_client, room):
    r = staff_client.get(f"/control/event/dummy/dummy/rooms/{room.pk}/")
    assert "1 of 2 places in this room are taken." in r.content.decode()


@pytest.mark.django_db
def test_room_detail_saves_type(staff_client, room, hotel):
    item, _, double = hotel
    r = staff_client.post(
        f"/control/event/dummy/dummy/rooms/{room.pk}/",
        _form_data(room, f"{item.pk}_{double.pk}"),
    )
    assert r.status_code == 302
    room.refresh_from_db()
    assert room.variation == double


def test_order_info_shows_occupancy(event, room):
    order = room.orderrooms.get().order
    assert "1 of 2 places in this room are taken." in order_info(event, order=order)


def test_order_info_without_capacity(event, room, hotel):
    item, _, double = hotel
    room.variation = double  # unlimited
    room.save()
    order = room.orderrooms.get().order
    assert "places in this room are taken" not in order_info(event, order=order)
