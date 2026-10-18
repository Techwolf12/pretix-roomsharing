import pytest
from datetime import timedelta
from decimal import Decimal
from django.utils.timezone import now
from django_scopes import scopes_disabled
from pretix.base.models import Event, Order, Organizer


@pytest.fixture(autouse=True)
def no_scopes():
    with scopes_disabled():
        yield


@pytest.fixture
def organizer(db):
    return Organizer.objects.create(name="Dummy", slug="dummy")


@pytest.fixture
def event(organizer):
    return Event.objects.create(
        organizer=organizer,
        name="Dummy",
        slug="dummy",
        date_from=now() + timedelta(days=30),
        plugins="pretix_roomsharing",
    )


@pytest.fixture
def item(event):
    return event.items.create(
        name="Ticket", default_price=Decimal("23.00"), admission=True
    )


@pytest.fixture
def order(event, item):
    o = Order.objects.create(
        event=event,
        email="dummy@example.com",
        status=Order.STATUS_PENDING,
        datetime=now(),
        expires=now() + timedelta(days=10),
        total=Decimal("23.00"),
        sales_channel=event.organizer.sales_channels.get(identifier="web"),
    )
    o.positions.create(item=item, price=Decimal("23.00"))
    return o
