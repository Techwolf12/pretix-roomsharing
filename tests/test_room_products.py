from decimal import Decimal

from pretix_roomsharing.signals import order_info
from pretix_roomsharing.utils import requires_room


def test_room_products_default_is_empty(event):
    assert event.settings.roomsharing__products == []


def test_requires_room_without_configured_products(event, item):
    assert not requires_room(event, [item])


def test_requires_room_with_configured_product(event, item):
    event.settings.roomsharing__products = [str(item.pk)]
    assert requires_room(event, [item])


def test_requires_room_with_other_product(event, item):
    other = event.items.create(name="Parking", default_price=Decimal("5.00"))
    event.settings.roomsharing__products = [str(other.pk)]
    assert not requires_room(event, [item])


def test_order_info_without_configured_products(event, order):
    html = order_info(event, order=order)
    assert "Change details" not in html


def test_order_info_with_configured_product(event, item, order):
    event.settings.roomsharing__products = [str(item.pk)]
    html = order_info(event, order=order)
    assert "Change details" in html
