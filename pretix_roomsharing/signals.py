# Register your receivers here
import logging
from django import forms
from django.dispatch import receiver
from django.http import HttpRequest
from django.template.loader import get_template
from django.urls import resolve, reverse
from django.utils.translation import gettext_lazy as _
from pretix.base.i18n import LazyI18nString
from pretix.base.models import Event, Order, OrderPosition, Question, QuestionAnswer
from pretix.base.services.cart import CartError
from pretix.base.settings import settings_hierarkey
from pretix.base.signals import (
    logentry_display,
    order_approved,
    order_placed,
    validate_cart,
)
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
from django.core import serializers

from .checkoutflow import RoomStep
from .models import OrderRoom, Room

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
            c.orderrooms.create(order=order, is_admin=True)
    elif order.meta_info_data and order.meta_info_data.get("room_mode") == "join":
        try:
            c = sender.rooms.get(pk=order.meta_info_data["room_join"])
        except Room.DoesNotExist:
            return
        else:
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
    
    try:
        c = order.orderroom
        fellows_orders = OrderPosition.objects.filter(
            order__status__in=(Order.STATUS_PENDING, Order.STATUS_PAID),
            order__orderroom__room=c.room,
            item__admission=True,
        ).exclude(order=order)

        ctx["room"] = c.room
        ctx["is_admin"] = c.is_admin
        ctx["fellows"] = fellows_orders
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


@receiver(signal=logentry_display, dispatch_uid="room_logentry_display")
def shipping_logentry_display(sender, logentry, **kwargs):
    if not logentry.action_type.startswith("pretix_roomsharing"):
        return

    plains = {
        "pretix_roomsharing.order.left": _("The user left a room."),
        "pretix_roomsharing.order.joined": _("The user joined a room."),
        "pretix_roomsharing.order.created": _("The user created a new room."),
        "pretix_roomsharing.order.changed": _("The user changed a room password."),
        "pretix_roomsharing.order.deleted": _("The room has been deleted."),
        "pretix_roomsharing.room.deleted": _("The room has been changed."),
        "pretix_roomsharing.room.changed": _("The room has been deleted."),
    }

    if logentry.action_type in plains:
        return plains[logentry.action_type]


@receiver(nav_event, dispatch_uid="room_nav")
def control_nav_event(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    if not request.user.has_event_permission(
        request.organizer, request.event, "can_view_orders", request=request
    ):
        return []
    return [
        {
            "label": _("Rooms"),
            "url": reverse(
                "plugins:pretix_roomsharing:event.room.list",
                kwargs={
                    "event": request.event.slug,
                    "organizer": request.event.organizer.slug,
                },
            ),
            "active": (
                url.namespace == "plugins:pretix_roomsharing"
                and "rooms" in url.url_name
            ),
            "icon": "group",
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
