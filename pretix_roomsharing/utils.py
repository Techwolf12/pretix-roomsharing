from pretix.base.models import Order
from pretix.base.timemachine import time_machine_now


def room_products(event) -> dict:
    """Return the room products, keyed by ``(item_id, variation_id)``."""
    return {(rp.item_id, rp.variation_id): rp for rp in event.room_products.all()}


def room_positions(event, positions) -> list:
    """Return the cart or order positions that take part in roomsharing."""
    products = room_products(event)
    return [p for p in positions if (p.item_id, p.variation_id) in products]


def requires_room(event, positions) -> bool:
    """Return whether any of the given positions takes part in roomsharing."""
    return bool(room_positions(event, positions))


def can_change_room(order) -> bool:
    """Return whether the attendee may still change the room of this order."""
    if order.status not in (Order.STATUS_PENDING, Order.STATUS_PAID):
        return False
    deadline = order.modify_deadline
    return deadline is None or time_machine_now() <= deadline
