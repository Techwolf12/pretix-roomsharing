# Register your receivers here
import logging
from django import forms
from django.db import transaction
from django.dispatch import receiver
from django.http import HttpRequest
from django.template.loader import get_template
from django.urls import resolve, reverse
from django.utils.translation import gettext_lazy as _
from pretix.api.signals import order_api_details, orderposition_api_details
from pretix.base.logentrytypes import (
    EventLogEntryType,
    OrderLogEntryType,
    log_entry_types,
)
from pretix.base.models import Event, Order
from pretix.base.settings import settings_hierarkey
from pretix.base.signals import event_copy_data, layout_text_variables, order_placed
from pretix.control.forms.filter import FilterForm
from pretix.control.signals import (
    nav_event,
    nav_event_settings,
    order_info as control_order_info,
)
from pretix.presale.signals import (
    checkout_confirm_page_content,
    checkout_flow_steps,
    order_info,
    order_meta_from_request,
)
from pretix.presale.views.cart import cart_session

from .api import order_room_data
from .checkoutflow import RoomStep
from .models import OrderRoom, Room
from .utils import (
    can_change_room,
    join_error,
    member_details,
    requires_room,
    room_capacity,
    room_members,
    room_occupancy,
    room_type,
)

logger = logging.getLogger(__name__)


@receiver(signal=checkout_flow_steps, dispatch_uid="room_checkout_step")
def signal_checkout_flow_steps(sender, **kwargs):
    return RoomStep


@receiver(nav_event_settings, dispatch_uid="pretix_roomsharing")
def navbar_settings(sender, request, **kwargs):
    url = resolve(request.path_info)
    return [
        {
            "label": _("Roomsharing"),
            "url": reverse(
                "plugins:pretix_roomsharing:control.room.settings",
                kwargs={
                    "event": request.event.slug,
                    "organizer": request.organizer.slug,
                },
            ),
            "active": url.namespace == "plugins:pretix_roomsharing"
            and url.url_name == "control.room.settings",
        }
    ]


@receiver(order_meta_from_request, dispatch_uid="room_order_meta")
def order_meta_signal(sender: Event, request: HttpRequest, **kwargs):
    cs = cart_session(request)
    return {
        "room_mode": cs.get("room_mode"),
        "room_join": cs.get("room_join"),
        "room_create": cs.get("room_create"),
    }


@receiver(order_placed, dispatch_uid="room_order_placed")
def placed_order(sender: Event, order: Order, **kwargs):
    if order.meta_info_data and order.meta_info_data.get("room_mode") == "create":
        try:
            c = sender.rooms.get(pk=order.meta_info_data["room_create"])
        except Room.DoesNotExist:
            logger.error("Room did not exist in room creation, can't add user to room")
            return
        else:
            # The final order is authoritative for the room type.
            c.item, c.variation = room_type(sender, order.positions.all())
            c.save(update_fields=["item", "variation"])
            c.orderrooms.create(order=order, is_admin=True)
    elif order.meta_info_data and order.meta_info_data.get("room_mode") == "join":
        with transaction.atomic():
            try:
                # Lock the room so concurrent checkouts can't both take the last spot.
                c = sender.rooms.select_for_update().get(
                    pk=order.meta_info_data["room_join"]
                )
            except Room.DoesNotExist:
                return
            error = join_error(c, order.positions.all(), exclude_order=order)
            if error:
                # The order can't be refused at this point, so leave it without a
                # room and let staff sort it out.
                order.log_action(
                    "pretix_roomsharing.order.join_failed",
                    data={"room": c.pk, "room_name": c.name, "reason": str(error)},
                )
                return
            c.orderrooms.create(order=order, is_admin=False)


@receiver(checkout_confirm_page_content, dispatch_uid="room_confirm")
def confirm_page(sender: Event, request: HttpRequest, **kwargs):
    cs = cart_session(request)

    template = get_template("pretix_roomsharing/checkout_confirm.html")
    ctx = {
        "mode": cs.get("room_mode"),
        "request": request,
    }
    if cs.get("room_mode") == "join":
        try:
            ctx["room"] = sender.rooms.get(pk=cs.get("room_join"))
        except Room.DoesNotExist:
            return
    elif cs.get("room_mode") == "create":
        try:
            ctx["room"] = sender.rooms.get(pk=cs.get("room_create"))
        except Room.DoesNotExist:
            return
    return template.render(ctx)


@receiver(order_info, dispatch_uid="room_order_info")
def order_info(sender: Event, order: Order, **kwargs):
    template = get_template("pretix_roomsharing/order_info.html")

    ctx = {
        "order": order,
        "event": sender,
    }

    # Show link for user to change room
    ctx["order_has_room"] = requires_room(sender, order.positions.all()) and (
        can_change_room(order)
    )

    # Show current room details
    try:
        c = order.orderroom
        fields = sender.settings.roomsharing__member_fields
        ctx["room"] = c.room
        ctx["is_admin"] = c.is_admin
        ctx["show_room_number"] = sender.settings.roomsharing__show_room_number
        ctx["fellows"] = [
            " – ".join(member_details(p, fields)) or _("Room member")
            for p in room_members(c.room, exclude_order=order)
        ]
        ctx["occupancy"] = room_occupancy(c.room)
        ctx["capacity"] = room_capacity(c.room)
    except OrderRoom.DoesNotExist:
        pass

    return template.render(ctx)


@receiver(control_order_info, dispatch_uid="room_control_order_info")
def control_order_info(sender: Event, request, order: Order, **kwargs):
    template = get_template("pretix_roomsharing/control_order_info.html")

    ctx = {
        "order": order,
        "event": sender,
        "request": request,
    }
    try:
        c = order.orderroom
        ctx["room"] = c.room
        ctx["is_admin"] = c.is_admin
    except OrderRoom.DoesNotExist:
        pass

    return template.render(ctx, request=request)


@log_entry_types.new_from_dict(
    {
        "pretix_roomsharing.order.left": _("The user left a room."),
        "pretix_roomsharing.order.joined": _("The user joined a room."),
        "pretix_roomsharing.order.created": _("The user created a new room."),
        "pretix_roomsharing.order.changed": _("The user changed a room password."),
        "pretix_roomsharing.order.deleted": _("The room has been deleted."),
        "pretix_roomsharing.order.join_failed": _(
            'The order could not be added to the room "{room_name}": {reason}'
        ),
    }
)
class RoomOrderLogEntryType(OrderLogEntryType):
    pass


@log_entry_types.new_from_dict(
    {
        "pretix_roomsharing.room.changed": _("The room has been changed."),
        "pretix_roomsharing.room.deleted": _("The room has been deleted."),
    }
)
class RoomLogEntryType(EventLogEntryType):
    object_link_wrapper = _("Room {val}")
    object_link_viewname = "plugins:pretix_roomsharing:event.room.detail"
    object_link_argname = "pk"
    content_type = Room


@receiver(nav_event, dispatch_uid="room_nav")
def control_nav_event(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    if not request.user.has_event_permission(
        request.organizer, request.event, "event.orders:write", request=request
    ):
        return []
    kwargs = {
        "event": request.event.slug,
        "organizer": request.event.organizer.slug,
    }
    in_plugin = url.namespace == "plugins:pretix_roomsharing"
    return [
        {
            "label": _("Rooms"),
            "url": reverse("plugins:pretix_roomsharing:event.room.list", kwargs=kwargs),
            "active": in_plugin and url.url_name.startswith("event.room."),
            "icon": "group",
            "children": [
                {
                    "label": _("Rooms"),
                    "url": reverse(
                        "plugins:pretix_roomsharing:event.room.list", kwargs=kwargs
                    ),
                    "active": in_plugin
                    and url.url_name
                    in ("event.room.list", "event.room.detail", "event.room.delete"),
                },
                {
                    "label": _("Statistics"),
                    "url": reverse(
                        "plugins:pretix_roomsharing:event.room.stats", kwargs=kwargs
                    ),
                    "active": in_plugin and url.url_name == "event.room.stats",
                },
            ],
        }
    ]


class RoomSearchForm(FilterForm):
    room_name = forms.CharField(
        label=_("Room name"), required=False, help_text=_("Exact matches only")
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop("event")
        super().__init__(*args, **kwargs)
        del self.fields["ordering"]

    def filter_qs(self, qs):
        fdata = self.cleaned_data
        qs = super().filter_qs(qs)
        if fdata.get("room_name"):
            qs = qs.filter(orderroom__room__name__iexact=fdata.get("room_name"))
        return qs


try:
    from pretix.control.signals import order_search_forms

    @receiver(order_search_forms, dispatch_uid="room_order_search")
    def control_order_search(sender, request, **kwargs):
        return RoomSearchForm(
            data=request.GET,
            event=sender,
            prefix="rooms",
        )

except ImportError:
    pass


def _order_room(order):
    try:
        return order.orderroom.room
    except OrderRoom.DoesNotExist:
        return None


@receiver(layout_text_variables, dispatch_uid="room_layout_text_variables")
def room_layout_text_variables(sender, **kwargs):
    # Usable on tickets and badges, and included in the check-in API's pdf_data.
    return {
        "roomsharing_room_name": {
            "label": _("Room name (Roomsharing)"),
            "editor_sample": _("Room 1"),
            "evaluate": lambda op, order, ev: getattr(_order_room(order), "name", ""),
        },
        "roomsharing_room_number": {
            "label": _("Room number (Roomsharing)"),
            "editor_sample": "101",
            "evaluate": lambda op, order, ev: getattr(
                _order_room(order), "room_number", ""
            ),
        },
    }


@receiver(order_api_details, dispatch_uid="room_order_api_details")
def order_api_room(sender, order, **kwargs):
    return {"roomsharing": {"room": order_room_data(order)}}


@receiver(orderposition_api_details, dispatch_uid="room_orderposition_api_details")
def orderposition_api_room(sender, orderposition, **kwargs):
    return {"roomsharing": {"room": order_room_data(orderposition.order)}}


@receiver(event_copy_data, dispatch_uid="room_copy_data")
def copy_room_products(sender, other, item_map, variation_map, **kwargs):
    for rp in other.room_products.all():
        sender.room_products.create(
            item=item_map[rp.item_id],
            variation=variation_map[rp.variation_id] if rp.variation_id else None,
            max_people=rp.max_people,
        )


settings_hierarkey.add_default("roomsharing__same_product_only", "False", bool)
settings_hierarkey.add_default("roomsharing__allow_random_room", "True", bool)
settings_hierarkey.add_default("roomsharing__member_fields", ["code"], list)
settings_hierarkey.add_default("roomsharing__show_room_number", "False", bool)
