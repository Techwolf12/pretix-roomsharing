from rest_framework import serializers, viewsets
from rest_framework.exceptions import NotFound

from .models import OrderRoom, Room
from .utils import room_capacity, room_members, room_occupancy


def order_room_data(order):
    """Return the order's room as shown in pretix's API, or ``None``."""
    try:
        room = order.orderroom.room
    except OrderRoom.DoesNotExist:
        return None
    return {"id": room.pk, "name": room.name, "room_number": room.room_number}


class RoomSerializer(serializers.ModelSerializer):
    item = serializers.IntegerField(source="item_id", read_only=True)
    variation = serializers.IntegerField(source="variation_id", read_only=True)
    capacity = serializers.SerializerMethodField()
    occupancy = serializers.SerializerMethodField()
    members = serializers.SerializerMethodField()

    class Meta:
        model = Room
        fields = [
            "id",
            "name",
            "room_number",
            "item",
            "variation",
            "capacity",
            "occupancy",
            "members",
        ]

    def get_capacity(self, room):
        return room_capacity(room)

    def get_occupancy(self, room):
        return room_occupancy(room)

    def get_members(self, room):
        admin_orders = set(
            room.orderrooms.filter(is_admin=True).values_list("order_id", flat=True)
        )
        return [
            {
                "order": p.order.code,
                "position": p.pk,
                "positionid": p.positionid,
                "attendee_name": p.attendee_name,
                "is_admin": p.order_id in admin_orders,
            }
            for p in room_members(room)
        ]


class RoomViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RoomSerializer
    queryset = Room.objects.none()
    permission = "event.orders:read"

    def get_queryset(self):
        event = self.request.event
        if "pretix_roomsharing" not in event.get_plugins():
            raise NotFound("Roomsharing is not enabled for this event.")
        qs = event.rooms.select_related("item", "variation")
        params = self.request.query_params
        if params.get("order"):
            qs = qs.filter(orderrooms__order__code=params["order"])
        if params.get("room_number"):
            qs = qs.filter(room_number=params["room_number"])
        if params.get("name"):
            qs = qs.filter(name=params["name"])
        return qs
