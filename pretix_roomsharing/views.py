import base64
import hmac
import logging
from collections import defaultdict
from django import forms
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Exists, OuterRef
from django.forms.widgets import CheckboxSelectMultiple, RadioSelect
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import DeleteView, FormView, ListView, TemplateView
from django_scopes import scopes_disabled
from i18nfield.forms import I18nFormField, I18nTextInput
from pretix import settings
from pretix.base.forms import SettingsForm
from pretix.base.models import (
    Event,
    Order,
    OrderPosition,
    OrderRefund,
    Question,
    SubEvent,
)
from pretix.base.views.metrics import unauthed_response
from pretix.base.views.tasks import AsyncAction
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.views import UpdateView
from pretix.control.views.event import EventSettingsFormView, EventSettingsViewMixin
from pretix.control.views.orders import OrderView
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.views import EventViewMixin
from pretix.presale.views.order import OrderDetailMixin

logger = logging.getLogger(__name__)


class RoomsharingSettingsForm(SettingsForm):
    roomsharing__products = forms.MultipleChoiceField(
        choices=[],
        label=_("Roomsharing products"),
        required=False,
        widget=CheckboxSelectMultiple,
    )

    roomsharing__questions = forms.ChoiceField(
        choices=[],
        label=_("What is the Roomsharing name question?"),
        required=False,
        widget=RadioSelect,
    )

    def __init__(self, *args, **kwargs):
        event = kwargs.get("obj")
        super().__init__(*args, **kwargs)

        choices = (
            (str(i["id"]), i["name"]) for i in event.items.values("name", "id").all()
        )
        self.fields["roomsharing__products"].choices = choices
        questionChoices = (
            (str(i["identifier"]), i["question"])
            for i in Question.objects.filter(event=event).values("question", "identifier").all()
        )
        self.fields["roomsharing__questions"].choices = questionChoices


class SettingsView(EventSettingsViewMixin, EventSettingsFormView):
    model = Event
    form_class = RoomsharingSettingsForm
    template_name = "pretix_roomsharing/settings.html"
    permission = "can_change_settings"
    # TODO: Set user public name field

    def get_success_url(self):
        return reverse(
            "plugins:pretix_roomsharing:control.room.settings",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )


from .checkoutflow import RoomCreateForm, RoomJoinForm
from .models import OrderRoom, Room


class RoomChangePasswordForm(forms.Form):
    password = forms.CharField(
        max_length=190,
        label=_("New room password"),
        help_text=_("Optional"),
        min_length=3,
        required=False,
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop("event")
        super().__init__(*args, **kwargs)


@method_decorator(xframe_options_exempt, "dispatch")
class OrderRoomChange(EventViewMixin, OrderDetailMixin, TemplateView):
    template_name = "pretix_roomsharing/order_room_change.html"

    def dispatch(self, request, *args, **kwargs):
        self.request = request

        if not self.order:
            raise Http404(
                _("Unknown order code or not authorized to access this order.")
            )

        if not self.order.can_modify_answers:
            messages.error(request, _("The room for this order cannot be changed."))
            return redirect(self.get_order_url())

        if self.order.status not in (Order.STATUS_CANCELED, Order.STATUS_EXPIRED):
            messages.error(request, _("The room for this order cannot be changed."))
            return redirect(self.get_order_url())

        return super().dispatch(request, *args, **kwargs)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        self.request = request

        mode = request.POST.get("room_mode")
        if mode == "leave":
            try:
                c = self.order.orderroom
                c.delete()
                self.order.log_action(
                    "pretix_roomsharing.order.left", data={"room": c.pk}
                )
                messages.success(
                    request,
                    _(
                        "Okay, you left your room successfully. How do you want to continue?"
                    ),
                )
                return redirect(
                    eventreverse(
                        self.request.event,
                        "plugins:pretix_roomsharing:event.order.room.modify",
                        kwargs={
                            "order": self.order.code,
                            "secret": self.order.secret,
                        },
                    )
                )
            except OrderRoom.DoesNotExist:
                pass

        elif mode == "change":
            if self.change_form.is_valid():
                try:
                    c = self.order.orderroom
                    if c.is_admin:
                        c.room.password = self.change_form.cleaned_data["password"]
                        c.room.save()
                    self.order.log_action(
                        "pretix_roomsharing.order.changed", data={"room": c.pk}
                    )
                    messages.success(
                        request,
                        _(
                            "Okay, we changed the password. Make sure to tell your friends!"
                        ),
                    )
                    return redirect(self.get_order_url())
                except OrderRoom.DoesNotExist:
                    pass

        elif mode == "join":
            if self.join_form.is_valid():
                room = self.join_form.cleaned_data["room"]
                OrderRoom.objects.create(room=room, order=self.order)
                self.order.log_action(
                    "pretix_roomsharing.order.joined", data={"room": room.pk}
                )
                messages.success(request, _("Great, we saved your changes!"))
                return redirect(self.get_order_url())

        elif mode == "create":
            if self.create_form.is_valid():
                room = Room(event=self.request.event)
                room.name = self.create_form.cleaned_data["name"]
                room.password = self.create_form.cleaned_data["password"]
                room.save()
                OrderRoom.objects.create(room=room, order=self.order, is_admin=True)
                self.order.log_action(
                    "pretix_roomsharing.order.created", data={"room": room.pk}
                )
                messages.success(request, _("Great, we saved your changes!"))
                return redirect(self.get_order_url())
        elif mode == "none":
            messages.success(request, _("Great, we saved your changes!"))
            return redirect(self.get_order_url())

        messages.error(
            self.request,
            _("We could not handle your input. See below for more information."),
        )
        return self.get(request, *args, **kwargs)

    @cached_property
    def change_form(self):
        return RoomChangePasswordForm(
            event=self.request.event,
            prefix="change",
            data=self.request.POST
            if self.request.method == "POST"
            and self.request.POST.get("room_mode") == "change"
            else None,
        )

    @cached_property
    def create_form(self):
        return RoomCreateForm(
            event=self.request.event,
            prefix="create",
            data=self.request.POST
            if self.request.method == "POST"
            and self.request.POST.get("room_mode") == "create"
            else None,
        )

    @cached_property
    def join_form(self):
        return RoomJoinForm(
            event=self.request.event,
            prefix="join",
            data=self.request.POST
            if self.request.method == "POST"
            and self.request.POST.get("room_mode") == "join"
            else None,
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["order"] = self.order
        ctx["join_form"] = self.join_form
        ctx["create_form"] = self.create_form
        ctx["change_form"] = self.change_form

        try:
            c = self.order.orderroom
            ctx["room"] = c.room
            ctx["is_admin"] = c.is_admin
        except OrderRoom.DoesNotExist:
            ctx["selected"] = self.request.POST.get("room_mode", "none")

        return ctx

    def dispatch(self, request, *args, **kwargs):
        self.request = request

        return super().dispatch(request, *args, **kwargs)


class ControlRoomForm(forms.ModelForm):
    class Meta:
        model = OrderRoom
        fields = ["room", "is_admin"]

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop("event")
        super().__init__(*args, **kwargs)
        self.fields["room"].queryset = self.event.room.all()


class ControlRoomChange(OrderView):
    permission = "can_change_orders"
    template_name = "pretix_roomsharing/control_order_room_change.html"

    @cached_property
    def form(self):
        try:
            instance = self.order.orderroom
        except OrderRoom.DoesNotExist:
            instance = OrderRoom(order=self.order)
        return ControlRoomForm(
            data=self.request.POST if self.request.method == "POST" else None,
            instance=instance,
            event=self.request.event,
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx["form"] = self.form
        return ctx

    def post(self, request, *args, **kwargs):
        if self.form.is_valid():
            self.form.save()
            messages.success(request, _("Great, we saved your changes!"))
            return redirect(self.get_order_url())
        messages.error(
            self.request,
            _("We could not handle your input. See below for more information."),
        )
        return self.get(request, *args, **kwargs)


class RoomList(EventPermissionRequiredMixin, ListView):
    permission = "can_change_orders"
    template_name = "pretix_roomsharing/control_list.html"
    context_object_name = "rooms"
    paginate_by = 25

    def get_queryset(self):
        return self.request.event.rooms.all()


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ["name", "password"]

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop("event")
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if (
            Room.objects.filter(event=self.event, name=name)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError(_("Duplicate room name"), code="duplicate_name")
        return name


class RoomDetail(EventPermissionRequiredMixin, UpdateView):
    permission = "can_change_orders"
    template_name = "pretix_roomsharing/control_detail.html"
    context_object_name = "rooms"
    form_class = RoomForm

    def get_queryset(self):
        return self.request.event.rooms.all()

    def form_valid(self, form):
        form.save()
        form.instance.log_action(
            "pretix_roomsharing.room.changed",
            data=form.cleaned_data,
            user=self.request.user,
        )
        messages.success(self.request, _("Great, we saved your changes!"))
        return redirect(
            reverse(
                "plugins:pretix_roomsharing:event.room.list",
                kwargs={
                    "organizer": self.request.organizer.slug,
                    "event": self.request.event.slug,
                },
            )
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["orders"] = self.object.orderrooms.select_related("order")
        return ctx


class RoomDelete(EventPermissionRequiredMixin, DeleteView):
    permission = "can_change_orders"
    template_name = "pretix_roomsharing/control_delete.html"
    context_object_name = "rooms"

    def get_queryset(self):
        return self.request.event.rooms.all()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["orders"] = self.object.orderrooms.select_related("order")
        return ctx

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        o = self.object = self.get_object()
        o.log_action(
            "pretix_roomsharing.room.deleted", data={"name": o.name}, user=request.user
        )
        for oc in self.object.orderrooms.select_related("order"):
            oc.order.log_action(
                "pretix_roomsharing.order.deleted",
                data={"room": o.pk},
                user=request.user,
            )
            oc.delete()
        o.delete()
        messages.success(self.request, _("The room has been deleted."))
        return redirect(
            reverse(
                "plugins:pretix_roomsharing:event.room.list",
                kwargs={
                    "organizer": self.request.organizer.slug,
                    "event": self.request.event.slug,
                },
            )
        )


class StatsMixin:
    def get_ticket_stats(self, event):
        qs = OrderPosition.objects.filter(order__event=event,).annotate(
            has_room=Exists(OrderRoom.objects.filter(order_id=OuterRef("order_id")))
        )
        return [
            {
                "id": "tickets_total",
                "label": _("All tickets, total"),
                "qs": qs.filter(
                    order__status=Order.STATUS_PENDING, order__require_approval=True
                ),
                "qs_cliq": True,
            },
            {
                "id": "tickets_registered",
                "label": _("Tickets Pending"),
                "qs": qs.filter(
                    order__status=Order.STATUS_PENDING, order__require_approval=True
                ),
                "qs_cliq": True,
            },
            {
                "id": "tickets_approved",
                "label": _("Tickets in approved orders (regardless of payment status)"),
                "qs": qs.filter(order__require_approval=False),
                "qs_cliq": True,
            },
            {
                "id": "tickets_paid",
                "label": _("Tickets in paid orders"),
                "qs": qs.filter(
                    order__require_approval=False, order__status=Order.STATUS_PAID
                ),
            },
            {
                "id": "tickets_pending",
                "label": _("Tickets in pending orders"),
                "qs": qs.filter(
                    order__require_approval=False, order__status=Order.STATUS_PENDING
                ),
            },
            {
                "id": "tickets_canceled",
                "label": _(
                    "Tickets in canceled orders (except the ones not chosen in raffle)"
                ),
                "qs": qs.filter(
                    order__require_approval=False, order__status=Order.STATUS_CANCELED
                ),
            },
            {
                "id": "tickets_canceled_refunded",
                "label": _(
                    "Tickets in canceled and at least partially refunded orders"
                ),
                "qs": qs.annotate(
                    has_refund=Exists(
                        OrderRefund.objects.filter(
                            order_id=OuterRef("order_id"),
                            state__in=[OrderRefund.REFUND_STATE_DONE],
                        )
                    )
                ).filter(
                    price__gt=0, order__status=Order.STATUS_CANCELED, has_refund=True
                ),
            },
            {
                "id": "tickets_denied",
                "label": _("Tickets denied (not chosen in raffle)"),
                "qs": qs.filter(
                    order__require_approval=True, order__status=Order.STATUS_CANCELED
                ),
                "qs_cliq": True,
            },
        ]


class StatsView(StatsMixin, EventPermissionRequiredMixin, TemplateView):
    template_name = "pretix_roomsharing/control_stats.html"
    permission = "can_view_orders"

    def get_context_data(self, **kwargs):
        def qs_by_item(qs):
            d = defaultdict(lambda: defaultdict(lambda: 0))
            for r in qs:
                d[r["item"]][r["subevent"]] = r["c"]
            return d

        def qs_by_room(qs):
            d = defaultdict(lambda: defaultdict(lambda: 0))
            for r in qs:
                d[r["has_room"]][r["subevent"]] = r["c"]
            return d

        def qs_by_unique_room(qs):
            d = defaultdict(lambda: defaultdict(lambda: 0))
            for r in qs:
                d[r["has_room"]][r["subevent"]] = r["cc"]
            return d

        def qs_by_subevent(qs):
            d = defaultdict(lambda: defaultdict(lambda: 0))
            for r in qs:
                d[r["subevent"]][r["item"]] = r["c"]
            return d

        ctx = super().get_context_data()
        ctx["subevents"] = self.request.event.subevents.all()
        ctx["items"] = self.request.event.items.all()
        ctx["ticket_stats"] = []
        for d in self.get_ticket_stats(self.request.event):
            qs = list(
                d["qs"].order_by().values("subevent", "item").annotate(c=Count("*"))
            )
            if d.get("qs_cliq"):
                qsc = list(
                    d["qs"]
                    .order_by()
                    .values("subevent", "has_room")
                    .annotate(
                        c=Count("*"), cc=Count("order__orderroom__room", distinct=True)
                    )
                )
                c1 = qs_by_room(qsc)
                c2 = qs_by_unique_room(qsc)
            else:
                c1 = c2 = None

            ctx["ticket_stats"].append(
                (d["label"], qs_by_item(qs), qs_by_subevent(qs), c1, c2)
            )
        return ctx


class MetricsView(StatsMixin, View):
    @scopes_disabled()
    def get(self, request, organizer, event):
        event = get_object_or_404(Event, slug=event, organizer__slug=organizer)
        if not settings.METRICS_ENABLED:
            return unauthed_response()

        # check if the user is properly authorized:
        if "Authorization" not in request.headers:
            return unauthed_response()

        method, credentials = request.headers["Authorization"].split(" ", 1)
        if method.lower() != "basic":
            return unauthed_response()

        user, passphrase = base64.b64decode(credentials.strip()).decode().split(":", 1)

        if not hmac.compare_digest(user, settings.METRICS_USER):
            return unauthed_response()
        if not hmac.compare_digest(passphrase, settings.METRICS_PASSPHRASE):
            return unauthed_response()

        # ok, the request passed the authentication-barrier, let's hand out the metrics:
        m = defaultdict(dict)
        for d in self.get_ticket_stats(event):
            if d.get("qs_cliq"):
                qs = (
                    d["qs"]
                    .order_by()
                    .values("subevent", "item", "has_room")
                    .annotate(
                        c=Count("*"), cc=Count("order__orderroom__room", distinct=True)
                    )
                )
                for r in qs:
                    m[d["id"]][
                        '{item="%s",subevent="%s",hasroom="%s"}'
                        % (r["item"], r["subevent"], r["has_room"])
                    ] = r["c"]
                    if r["cc"]:
                        m[d["id"] + "_unique_rooms"][
                            '{item="%s",subevent="%s"}' % (r["item"], r["subevent"])
                        ] = r["cc"]
            else:
                qs = (
                    d["qs"].order_by().values("subevent", "item").annotate(c=Count("*"))
                )
                for r in qs:
                    m[d["id"]][
                        '{item="%s",subevent="%s"}' % (r["item"], r["subevent"])
                    ] = r["c"]

        output = []
        for metric, sub in m.items():
            for label, value in sub.items():
                output.append("{}{} {}".format(metric, label, str(value)))

        content = "\n".join(output) + "\n"

        return HttpResponse(content)
