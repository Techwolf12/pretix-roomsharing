import pytest
from datetime import timedelta
from decimal import Decimal
from django.utils.timezone import now
from pretix.base.models import CartPosition, Order
from pretix.testutils.sessions import get_cart_session_key

from pretix_roomsharing.models import OrderRoom, Room
from pretix_roomsharing.signals import placed_order
from pretix_roomsharing.utils import create_error, join_error, room_occupancy, room_type

FULL = "This room is full"
MISMATCH = "This room is only for people with"
MIXED = "Your order contains different ticket types"
TOO_BIG = "Your order contains more tickets than fit in one room"


@pytest.fixture
def hotel(event):
    item = event.items.create(name="Hotel", default_price=Decimal("100.00"))
    single = item.variations.create(value="Single")
    double = item.variations.create(value="Double")
    event.room_products.create(item=item, variation=single, max_people=2)
    event.room_products.create(item=item, variation=double, max_people=3)
    return item, single, double


def make_order(event, *tickets, status=Order.STATUS_PENDING):
    order = Order.objects.create(
        event=event,
        email="dummy@example.com",
        status=status,
        datetime=now(),
        expires=now() + timedelta(days=10),
        total=Decimal("0.00"),
        sales_channel=event.organizer.sales_channels.get(identifier="web"),
    )
    for item, variation in tickets:
        order.positions.create(item=item, variation=variation, price=Decimal("0.00"))
    return order


def make_room(event, item, variation, *orders):
    room = event.rooms.create(
        name=f"Room {event.rooms.count()}",
        password="secret",
        item=item,
        variation=variation,
    )
    for i, order in enumerate(orders):
        OrderRoom.objects.create(order=order, room=room, is_admin=i == 0)
    return room


def positions(order):
    return list(order.positions.all())


def test_join_full_room(event, hotel):
    item, single, _ = hotel
    room = make_room(
        event,
        item,
        single,
        make_order(event, (item, single)),
        make_order(event, (item, single)),
    )
    joiner = make_order(event, (item, single))
    assert FULL in join_error(room, positions(joiner))


def test_join_counts_every_ticket(event, hotel):
    item, single, _ = hotel
    room = make_room(event, item, single, make_order(event, (item, single)))
    joiner = make_order(event, (item, single), (item, single))
    assert FULL in join_error(room, positions(joiner))


def test_occupancy_ignores_canceled_orders(event, hotel):
    item, single, _ = hotel
    room = make_room(
        event,
        item,
        single,
        make_order(event, (item, single)),
        make_order(event, (item, single), status=Order.STATUS_CANCELED),
    )
    assert room_occupancy(room) == 1
    assert join_error(room, positions(make_order(event, (item, single)))) is None


def test_unlimited_room_product(event, item, hotel):
    event.room_products.create(item=item)
    room = make_room(event, item, None, make_order(event, (item, None)))
    for _ in range(5):
        OrderRoom.objects.create(order=make_order(event, (item, None)), room=room)
    assert join_error(room, positions(make_order(event, (item, None)))) is None


def test_type_mismatch_only_with_setting(event, hotel):
    item, single, double = hotel
    room = make_room(event, item, single, make_order(event, (item, single)))
    joiner = make_order(event, (item, double))

    assert join_error(room, positions(joiner)) is None
    event.settings.roomsharing__same_product_only = True
    error = join_error(room, positions(joiner))
    assert MISMATCH in error
    assert "Hotel – Single" in error


def test_mixed_order_only_with_setting(event, hotel):
    item, single, double = hotel
    room = make_room(event, item, double, make_order(event, (item, double)))
    mixed = make_order(event, (item, single), (item, double))

    assert join_error(room, positions(mixed)) is None
    assert create_error(event, positions(mixed)) is None
    event.settings.roomsharing__same_product_only = True
    assert MIXED in join_error(room, positions(mixed))
    assert MIXED in create_error(event, positions(mixed))


def test_non_room_tickets_are_ignored(event, item, hotel):
    hotel_item, single, _ = hotel
    event.settings.roomsharing__same_product_only = True
    room = make_room(event, hotel_item, single, make_order(event, (hotel_item, single)))
    # The ticket isn't a room product, so it neither mixes types nor takes a spot.
    joiner = make_order(event, (hotel_item, single), (item, None))
    assert join_error(room, positions(joiner)) is None


def test_legacy_room_without_type(event, hotel):
    item, single, double = hotel
    event.settings.roomsharing__same_product_only = True
    room = make_room(event, None, None, make_order(event, (item, single)))
    joiner = make_order(event, (item, double), (item, double), (item, double))
    assert join_error(room, positions(joiner)) is None


def test_create_too_big(event, hotel):
    item, single, _ = hotel
    order = make_order(event, (item, single), (item, single), (item, single))
    assert TOO_BIG in create_error(event, positions(order))
    assert create_error(event, positions(make_order(event, (item, single)))) is None


def test_room_type(event, item, hotel):
    hotel_item, _, double = hotel
    order = make_order(event, (item, None), (hotel_item, double))
    assert room_type(event, positions(order)) == (hotel_item, double)
    assert room_type(event, []) == (None, None)


def test_placed_order_create_sets_room_type(event, hotel):
    item, _, double = hotel
    room = event.rooms.create(name="Room", password="secret")
    order = make_order(event, (item, double))
    order.meta_info = '{"room_mode": "create", "room_create": %d}' % room.pk
    order.save()

    placed_order(event, order=order)
    room.refresh_from_db()
    assert (room.item, room.variation) == (item, double)
    assert OrderRoom.objects.get(order=order).is_admin


def test_placed_order_join_full_room(event, hotel):
    item, single, _ = hotel
    room = make_room(
        event,
        item,
        single,
        make_order(event, (item, single)),
        make_order(event, (item, single)),
    )
    order = make_order(event, (item, single))
    order.meta_info = '{"room_mode": "join", "room_join": %d}' % room.pk
    order.save()

    placed_order(event, order=order)
    assert not OrderRoom.objects.filter(order=order).exists()
    entry = order.all_logentries().get(
        action_type="pretix_roomsharing.order.join_failed"
    )
    assert FULL in entry.display()
    assert room.name in entry.display()


def test_placed_order_join(event, hotel):
    item, single, _ = hotel
    room = make_room(event, item, single, make_order(event, (item, single)))
    order = make_order(event, (item, single))
    order.meta_info = '{"room_mode": "join", "room_join": %d}' % room.pk
    order.save()

    placed_order(event, order=order)
    assert OrderRoom.objects.get(order=order).room == room


@pytest.fixture
def live_event(event):
    event.live = True
    event.save()
    return event


@pytest.mark.django_db
def test_after_purchase_join_full_room(client, live_event, hotel):
    item, single, _ = hotel
    room = make_room(
        live_event,
        item,
        single,
        make_order(live_event, (item, single)),
        make_order(live_event, (item, single)),
    )
    order = make_order(live_event, (item, single))
    r = client.post(
        f"/dummy/dummy/order/{order.code}/{order.secret}/room/modify",
        {"room_mode": "join", "join-name": room.name, "join-password": "secret"},
    )
    assert r.status_code == 200
    assert FULL in r.content.decode()
    assert not OrderRoom.objects.filter(order=order).exists()


@pytest.mark.django_db
def test_after_purchase_create_sets_room_type(client, live_event, hotel):
    item, _, double = hotel
    order = make_order(live_event, (item, double))
    r = client.post(
        f"/dummy/dummy/order/{order.code}/{order.secret}/room/modify",
        {"room_mode": "create", "create-name": "New", "create-password": "secret"},
    )
    assert r.status_code == 302
    room = Room.objects.get(name="New")
    assert (room.item, room.variation) == (item, double)


@pytest.fixture
def cart(client, live_event, hotel):
    item, single, _ = hotel
    session_key = get_cart_session_key(client, live_event)
    CartPosition.objects.create(
        event=live_event,
        cart_id=session_key,
        item=item,
        variation=single,
        price=Decimal("100.00"),
        expires=now() + timedelta(minutes=10),
    )
    session = client.session
    session["carts"][session_key]["email"] = "dummy@example.com"
    session.save()
    return session_key


@pytest.mark.django_db
def test_checkout_join_full_room(client, live_event, hotel, cart):
    item, single, _ = hotel
    room = make_room(
        live_event,
        item,
        single,
        make_order(live_event, (item, single)),
        make_order(live_event, (item, single)),
    )
    r = client.post(
        "/dummy/dummy/checkout/room/",
        {"room_mode": "join", "join-name": room.name, "join-password": "secret"},
    )
    assert r.status_code == 200
    assert FULL in r.content.decode()


@pytest.mark.django_db
def test_checkout_create_sets_room_type(client, live_event, hotel, cart):
    item, single, _ = hotel
    r = client.post(
        "/dummy/dummy/checkout/room/",
        {"room_mode": "create", "create-name": "New", "create-password": "secret"},
    )
    assert r.status_code == 302
    room = Room.objects.get(name="New")
    assert (room.item, room.variation) == (item, single)


@pytest.mark.django_db
def test_checkout_rechecks_room_after_room_step(client, live_event, hotel, cart):
    item, single, _ = hotel
    room = make_room(live_event, item, single, make_order(live_event, (item, single)))
    r = client.post(
        "/dummy/dummy/checkout/room/",
        {"room_mode": "join", "join-name": room.name, "join-password": "secret"},
    )
    assert r.status_code == 302

    # Someone else takes the last spot before this checkout is confirmed.
    OrderRoom.objects.create(order=make_order(live_event, (item, single)), room=room)
    r = client.get("/dummy/dummy/checkout/confirm/", follow=True)
    assert r.redirect_chain[-1][0].endswith("/checkout/room/")
    assert FULL in r.content.decode()
