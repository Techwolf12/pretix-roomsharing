import pytest
from datetime import timedelta
from decimal import Decimal
from django.utils.timezone import now
from pretix.base.models import CartPosition
from pretix.testutils.sessions import get_cart_session_key

from pretix_roomsharing.models import OrderRoom
from pretix_roomsharing.views import RoomsharingSettingsForm

RANDOM_OPTION = "I want to be assigned a random room"
ERROR = "Please create a new room or join an existing one."


@pytest.fixture
def live_event(event, item):
    event.live = True
    event.save()
    event.room_products.create(item=item)
    return event


@pytest.fixture
def cart(client, live_event, item):
    session_key = get_cart_session_key(client, live_event)
    CartPosition.objects.create(
        event=live_event,
        cart_id=session_key,
        item=item,
        price=Decimal("23.00"),
        expires=now() + timedelta(minutes=10),
    )
    session = client.session
    session["carts"][session_key]["email"] = "dummy@example.com"
    session.save()
    return session_key


def _disable_random_room(event):
    event.settings.roomsharing__allow_random_room = False


@pytest.mark.django_db
def test_checkout_random_room_allowed_by_default(client, live_event, cart):
    assert RANDOM_OPTION in client.get("/dummy/dummy/checkout/room/").content.decode()
    r = client.post("/dummy/dummy/checkout/room/", {"room_mode": "none"})
    assert r.status_code == 302


@pytest.mark.django_db
def test_checkout_random_room_disabled(client, live_event, cart):
    _disable_random_room(live_event)
    assert (
        RANDOM_OPTION not in client.get("/dummy/dummy/checkout/room/").content.decode()
    )
    r = client.post("/dummy/dummy/checkout/room/", {"room_mode": "none"})
    assert r.status_code == 200
    assert ERROR in r.content.decode()


@pytest.mark.django_db
def test_checkout_without_room_tickets_still_passes(client, live_event, item, cart):
    _disable_random_room(live_event)
    live_event.room_products.all().delete()
    r = client.post("/dummy/dummy/checkout/room/", {"room_mode": "none"})
    assert r.status_code == 302


@pytest.mark.django_db
def test_checkout_rechecks_earlier_random_choice(client, live_event, cart):
    r = client.post("/dummy/dummy/checkout/room/", {"room_mode": "none"})
    assert r.status_code == 302

    _disable_random_room(live_event)
    r = client.get("/dummy/dummy/checkout/confirm/", follow=True)
    assert r.redirect_chain[-1][0].endswith("/checkout/room/")
    assert ERROR in r.content.decode()


@pytest.mark.django_db
def test_after_purchase_random_room_disabled(client, live_event, order):
    _disable_random_room(live_event)
    url = f"/dummy/dummy/order/{order.code}/{order.secret}/room/modify"
    assert RANDOM_OPTION not in client.get(url).content.decode()

    r = client.post(url, {"room_mode": "none"})
    assert r.status_code == 200
    assert ERROR in r.content.decode()
    assert not OrderRoom.objects.filter(order=order).exists()


@pytest.mark.django_db
def test_after_purchase_random_room_allowed(client, live_event, order):
    url = f"/dummy/dummy/order/{order.code}/{order.secret}/room/modify"
    assert RANDOM_OPTION in client.get(url).content.decode()
    assert client.post(url, {"room_mode": "none"}).status_code == 302


def test_settings_form_saves_allow_random_room(event):
    assert event.settings.roomsharing__allow_random_room is True
    assert RoomsharingSettingsForm(event=event).fields["allow_random_room"].initial

    form = RoomsharingSettingsForm(event=event, data={})
    assert form.is_valid(), form.errors
    form.save()
    assert event.settings.roomsharing__allow_random_room is False

    form = RoomsharingSettingsForm(event=event, data={"allow_random_room": "on"})
    assert form.is_valid(), form.errors
    form.save()
    assert event.settings.roomsharing__allow_random_room is True
