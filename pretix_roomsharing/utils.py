def requires_room(event, items) -> bool:
    """Return whether any of the given products takes part in roomsharing."""
    room_products = event.settings.roomsharing__products or []
    return any(str(item.pk) in room_products for item in items)
