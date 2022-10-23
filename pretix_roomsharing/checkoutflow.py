from django import forms
from django.contrib import messages
from django.db.transaction import atomic
from django.shortcuts import redirect
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from pretix.base.models import SubEvent
from pretix.presale.checkoutflow import TemplateFlowStep
from pretix.presale.views import CartMixin, get_cart
from pretix.presale.views.cart import cart_session

from .models import Room

# TODO Only show form if a roomshare available product is bought

class RoomCreateForm(forms.Form):
    error_messages = {
        "duplicate_name": _(
            "There already is a room with that name. If you want to join a room already created "
            "by your friends, please choose to join a room instead of creating a new one."
        ),
        "required": _("This field is required."),
    }

    name = forms.CharField(
        max_length=190,
        label=_("Room name"),
        required=False,
    )
    password = forms.CharField(
        max_length=190, label=_("Room password"), min_length=3, required=False
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop("event")
        self.room = kwargs.pop("current", None)
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if not name:
            raise forms.ValidationError(
                self.error_messages["required"], code="required"
            )

        if (
            Room.objects.filter(event=self.event, name=name)
            .exclude(pk=(self.room.pk if self.room else 0))
            .exists()
        ):
            raise forms.ValidationError(
                self.error_messages["duplicate_name"], code="duplicate_name"
            )
        return name

    def clean_password(self):
        password = self.cleaned_data.get("password")

        if not password:
            raise forms.ValidationError(
                self.error_messages["required"], code="required"
            )

        return password


class RoomJoinForm(forms.Form):
    error_messages = {
        "room_not_found": _(
            "This room does not exist. Are you sure you entered the name correctly?"
        ),
        "required": _("This field is required."),
        "pw_mismatch": _(
            "The password does not match. Please enter the password exactly as your friends send it."
        ),
    }

    name = forms.CharField(
        max_length=190,
        label=_("Room name"),
        required=False,
    )
    password = forms.CharField(
        max_length=190,
        label=_("Room password"),
        min_length=3,
        widget=forms.PasswordInput,
        required=False,
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop("event")
        super().__init__(*args, **kwargs)

    def clean(self):
        name = self.cleaned_data.get("name")
        password = self.cleaned_data.get("password")

        if not name:
            raise forms.ValidationError(
                {
                    "name": self.error_messages["required"],
                },
                code="required",
            )

        if not password:
            raise forms.ValidationError(
                {
                    "name": self.error_messages["required"],
                },
                code="required",
            )

        try:
            room = Room.objects.get(event=self.event, name=name)
        except Room.DoesNotExist:
            raise forms.ValidationError(
                {
                    "name": self.error_messages["room_not_found"],
                },
                code="room_not_found",
            )
        else:
            if room.password != password:
                raise forms.ValidationError(
                    {
                        "password": self.error_messages["pw_mismatch"],
                    },
                    code="pw_mismatch",
                )

        self.cleaned_data["room"] = room
        return self.cleaned_data


class RoomStep(CartMixin, TemplateFlowStep):
    priority = 180
    identifier = "room"
    template_name = "pretix_roomsharing/checkout_room.html"
    icon = "group"
    label = pgettext_lazy("checkoutflow", "Room")

    @atomic
    def post(self, request):
        self.request = request

        self.cart_session["room_mode"] = request.POST.get("room_mode", "")

        if self.cart_session["room_mode"] == "join":
            if self.join_form.is_valid():
                self.cart_session["room_join"] = self.join_form.cleaned_data["room"].pk
                return redirect(self.get_next_url(request))

        elif self.cart_session["room_mode"] == "create":
            if self.create_form.is_valid():
                room = Room(
                    event=self.event,
                )
                if self.cart_session.get("room_create"):
                    try:
                        room = Room.objects.get(
                            event=self.event, pk=self.cart_session["room_create"]
                        )
                    except Room.DoesNotExist:
                        pass

                room.name = self.create_form.cleaned_data["name"]
                room.password = self.create_form.cleaned_data["password"]
                room.save()
                self.cart_session["room_create"] = room.pk
                return redirect(self.get_next_url(request))
        elif self.cart_session["room_mode"] == "none":
            return redirect(self.get_next_url(request))

        messages.error(
            self.request,
            _("We couldn't handle your input, please check below for errors."),
        )
        return self.render()

    @cached_property
    def create_form(self):
        initial = {}
        current = None
        if (
            self.cart_session.get("room_mode") == "create"
            and "room_create" in self.cart_session
        ):
            try:
                current = Room.objects.get(
                    event=self.event, pk=self.cart_session["room_create"]
                )
            except Room.DoesNotExist:
                pass
            else:
                initial["name"] = current.name
                initial["password"] = current.password

        return RoomCreateForm(
            event=self.event,
            prefix="create",
            initial=initial,
            current=current,
            data=self.request.POST
            if self.request.method == "POST"
            and self.request.POST.get("room_mode") == "create"
            else None,
        )

    @cached_property
    def join_form(self):
        initial = {}
        if (
            self.cart_session.get("room_mode") == "join"
            and "room_join" in self.cart_session
        ):
            try:
                room = Room.objects.get(
                    event=self.event, pk=self.cart_session["room_join"]
                )
            except Room.DoesNotExist:
                pass
            else:
                initial["name"] = room.name
                initial["password"] = room.password

        return RoomJoinForm(
            event=self.event,
            prefix="join",
            initial=initial,
            data=self.request.POST
            if self.request.method == "POST"
            and self.request.POST.get("room_mode") == "join"
            else None,
        )

    @cached_property
    def cart_session(self):
        return cart_session(self.request)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["create_form"] = self.create_form
        ctx["join_form"] = self.join_form
        ctx["cart"] = self.get_cart()
        ctx["selected"] = self.cart_session.get("room_mode", "")
        return ctx

    def is_completed(self, request, warn=False):
        if (
            request.event.has_subevents
            and cart_session(request).get("room_mode") == "join"
            and "room_join" in cart_session(request)
        ):
            try:
                room = Room.objects.get(
                    event=self.event, pk=cart_session(request)["room_join"]
                )
                room_subevents = set(
                    c["order__all_positions__subevent"]
                    for c in room.orderrooms.filter(
                        order__all_positions__canceled=False
                    )
                    .values("order__all_positions__subevent")
                    .distinct()
                )
                # TODO: Validation of same room type
                # TODO: Validation of max room quantity?
                if room_subevents:
                    cart_subevents = set(
                        c["subevent"]
                        for c in get_cart(request).values("subevent").distinct()
                    )
                    if any(c not in room_subevents for c in cart_subevents):
                        if warn:
                            messages.warning(
                                request,
                                _(
                                    'You requested to join a room that participates in "{subevent_room}", while you chose to participate in "{subevent_cart}". Please choose a different room.'
                                ).format(
                                    subevent_room=SubEvent.objects.get(
                                        pk=list(room_subevents)[0]
                                    ).name,
                                    subevent_cart=SubEvent.objects.get(
                                        pk=list(cart_subevents)[0]
                                    ).name,
                                ),
                            )
                        return False
            except Room.DoesNotExist:
                pass

        return "room_mode" in cart_session(request)

    def is_applicable(self, request):
        return True
