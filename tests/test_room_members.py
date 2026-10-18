import pytest
from datetime import timedelta
from decimal import Decimal
from django.utils.timezone import now
from pretix.base.models import Order, Question

from pretix_roomsharing.models import OrderRoom
from pretix_roomsharing.signals import order_info
from pretix_roomsharing.utils import member_field_choices
from pretix_roomsharing.views import RoomsharingSettingsForm


@pytest.fixture
def question(event, item):
    q = event.questions.create(question="Pronouns", type=Question.TYPE_STRING)
    q.items.add(item)
    return q


def make_member(event, item, room, name, answer=None, question=None, **kwargs):
    order = Order.objects.create(
        event=event,
        email="dummy@example.com",
        status=kwargs.pop("status", Order.STATUS_PAID),
        datetime=now(),
        expires=now() + timedelta(days=10),
        total=Decimal("0.00"),
        sales_channel=event.organizer.sales_channels.get(identifier="web"),
    )
    position = order.positions.create(
        item=item, price=Decimal("0.00"), attendee_name_parts={"full_name": name}
    )
    if answer is not None:
        position.answers.create(question=question, answer=answer)
    OrderRoom.objects.create(
        order=order, room=room, is_admin=kwargs.get("admin", False)
    )
    return order


@pytest.fixture
def room(event, item):
    event.room_products.create(item=item)
    return event.rooms.create(name="Room", password="secret", item=item)


def test_default_shows_order_code(event, item, room):
    me = make_member(event, item, room, "Me", admin=True)
    other = make_member(event, item, room, "Alex Example")
    html = order_info(event, order=me)
    assert other.code in html
    assert "Alex Example" not in html


def test_shows_selected_fields(event, item, room, question):
    event.settings.roomsharing__member_fields = [
        "attendee_name",
        f"question:{question.pk}",
    ]
    me = make_member(event, item, room, "Me", admin=True)
    other = make_member(event, item, room, "Alex Example", "they/them", question)
    html = order_info(event, order=me)
    assert "Alex Example – they/them" in html
    assert other.code not in html
    # The attendee's own ticket isn't listed as a fellow member.
    assert "<li>Me</li>" not in html


def test_empty_details_fall_back_to_placeholder(event, item, room, question):
    event.settings.roomsharing__member_fields = [f"question:{question.pk}"]
    me = make_member(event, item, room, "Me", admin=True)
    make_member(event, item, room, "Alex Example")
    assert "<li>Room member</li>" in order_info(event, order=me)


def test_canceled_orders_are_not_listed(event, item, room):
    event.settings.roomsharing__member_fields = ["attendee_name"]
    me = make_member(event, item, room, "Me", admin=True)
    make_member(event, item, room, "Gone Person", status=Order.STATUS_CANCELED)
    assert "Gone Person" not in order_info(event, order=me)


def test_member_field_choices(event, question):
    event.questions.create(question="Passport scan", type=Question.TYPE_FILE)
    choices = dict(member_field_choices(event))
    assert choices["code"] == "Order code"
    assert choices["attendee_name"] == "Attendee name"
    assert choices[f"question:{question.pk}"] == "Pronouns"
    assert "Passport scan" not in choices.values()


def test_settings_form_saves_member_fields(event, question):
    form = RoomsharingSettingsForm(
        event=event,
        data={"member_fields": ["attendee_name", f"question:{question.pk}"]},
    )
    assert form.is_valid(), form.errors
    form.save()
    assert event.settings.roomsharing__member_fields == [
        "attendee_name",
        f"question:{question.pk}",
    ]
    assert RoomsharingSettingsForm(event=event).fields["member_fields"].initial == [
        "attendee_name",
        f"question:{question.pk}",
    ]
