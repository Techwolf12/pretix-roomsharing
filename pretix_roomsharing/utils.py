from pretix.base.models import Order
from pretix.base.timemachine import time_machine_now


def requires_room(event, items) -> bool:
    """Return whether any of the given products takes part in roomsharing."""
    room_products = event.settings.roomsharing__products or []
    return any(str(item.pk) in room_products for item in items)


def can_change_room(order) -> bool:
    """Return whether the attendee may still change the room of this order."""
    if order.status not in (Order.STATUS_PENDING, Order.STATUS_PAID):
        return False
    deadline = order.modify_deadline
    return deadline is None or time_machine_now() <= deadline
