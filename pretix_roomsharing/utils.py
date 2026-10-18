from django.utils.translation import gettext as _
from pretix.base.models import Order, OrderPosition
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


def room_type(event, positions) -> tuple:
    """Return ``(item, variation)`` of the first room ticket."""
    eligible = room_positions(event, positions)
    if not eligible:
        return None, None
    return eligible[0].item, eligible[0].variation


def room_type_label(room) -> str:
    if room.variation_id:
        return f"{room.item} – {room.variation}"
    return str(room.item)


def room_capacity(room):
    """Return the maximum number of people in this room, or ``None``."""
    if not room.item_id:
        return None
    rp = room.event.room_products.filter(
        item_id=room.item_id, variation_id=room.variation_id
    ).first()
    return rp.max_people if rp else None


def room_occupancy(room, exclude_order=None) -> int:
    """Return the number of room tickets in active orders in this room."""
    positions = OrderPosition.objects.filter(
        order__orderroom__room=room,
        order__status__in=(Order.STATUS_PENDING, Order.STATUS_PAID),
    )
    if exclude_order:
        positions = positions.exclude(order=exclude_order)
    return len(room_positions(room.event, positions))


def _mixed_types_error(event, eligible):
    if not event.settings.roomsharing__same_product_only:
        return None
    if len({(p.item_id, p.variation_id) for p in eligible}) > 1:
        return _(
            "Your order contains different ticket types. Rooms can only be shared by "
            "people with the same ticket type, so you can't create or join a room "
            "with this order."
        )


def create_error(event, positions):
    """Return why these positions can't create a room, or ``None``."""
    eligible = room_positions(event, positions)
    error = _mixed_types_error(event, eligible)
    if error:
        return error
    if eligible:
        first = eligible[0]
        rp = room_products(event)[(first.item_id, first.variation_id)]
        if rp.max_people is not None and len(eligible) > rp.max_people:
            return _(
                "Your order contains more tickets than fit in one room "
                "(at most {max_people} people)."
            ).format(max_people=rp.max_people)


def join_error(room, positions, exclude_order=None):
    """Return why these positions can't join the room, or ``None``."""
    event = room.event
    eligible = room_positions(event, positions)
    error = _mixed_types_error(event, eligible)
    if error:
        return error

    if event.settings.roomsharing__same_product_only and room.item_id:
        if any(
            (p.item_id, p.variation_id) != (room.item_id, room.variation_id)
            for p in eligible
        ):
            return _(
                'This room is only for people with a "{room_type}" ticket.'
            ).format(room_type=room_type_label(room))

    capacity = room_capacity(room)
    if capacity is not None:
        if room_occupancy(room, exclude_order) + len(eligible) > capacity:
            return _("This room is full. Please choose a different room.")


def can_change_room(order) -> bool:
    """Return whether the attendee may still change the room of this order."""
    if order.status not in (Order.STATUS_PENDING, Order.STATUS_PAID):
        return False
    deadline = order.modify_deadline
    return deadline is None or time_machine_now() <= deadline
