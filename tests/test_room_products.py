import importlib
import pytest
from decimal import Decimal
from pretix.base.models import Event

from pretix_roomsharing.models import OrderRoom, RoomProduct
from pretix_roomsharing.signals import order_info
from pretix_roomsharing.utils import requires_room
from pretix_roomsharing.views import RoomsharingSettingsForm

migration_0003 = importlib.import_module(
    "pretix_roomsharing.migrations.0003_room_products"
)


@pytest.fixture
def historical_apps(settings):
    """The models as migration 0003 sees them, e.g. without custom managers."""
    from django.db import connection
    from django.db.migrations.loader import MigrationLoader

    # pretix's test settings disable migrations outside of GitHub Actions.
    settings.MIGRATION_MODULES = {}
    loader = MigrationLoader(connection, ignore_no_migrations=True)
    return loader.project_state(("pretix_roomsharing", "0003_room_products")).apps


@pytest.fixture
def variation_item(event):
    item = event.items.create(name="Hotel", default_price=Decimal("100.00"))
    item.variations.create(value="Single")
    item.variations.create(value="Double")
    return item


def test_requires_room_without_room_products(event, order):
    assert not requires_room(event, order.positions.all())


def test_requires_room_with_room_product(event, item, order):
    event.room_products.create(item=item)
    assert requires_room(event, order.positions.all())


def test_requires_room_with_other_product(event, order):
    other = event.items.create(name="Parking", default_price=Decimal("5.00"))
    event.room_products.create(item=other)
    assert not requires_room(event, order.positions.all())


def test_requires_room_per_variation(event, order, variation_item):
    single, double = variation_item.variations.order_by("pk")
    event.room_products.create(item=variation_item, variation=double)
    order.positions.create(
        item=variation_item, variation=single, price=Decimal("100.00")
    )
    assert not requires_room(event, order.positions.all())

    order.positions.create(
        item=variation_item, variation=double, price=Decimal("100.00")
    )
    assert requires_room(event, order.positions.all())


def test_order_info_without_room_products(event, order):
    html = order_info(event, order=order)
    assert "Change details" not in html


def test_order_info_with_room_product(event, item, order):
    event.room_products.create(item=item)
    html = order_info(event, order=order)
    assert "Change details" in html


def test_settings_form_rows(event, item, variation_item):
    form = RoomsharingSettingsForm(event=event)
    rows = [(i, v) for i, v, _, _ in form.row_fields()]
    single, double = variation_item.variations.order_by("pk")
    assert (item, None) in rows
    assert (variation_item, single) in rows
    assert (variation_item, double) in rows
    assert (variation_item, None) not in rows


def test_settings_form_save(event, item, variation_item):
    single, double = variation_item.variations.order_by("pk")
    data = {
        f"enabled_{item.pk}": "on",
        f"enabled_{variation_item.pk}_{double.pk}": "on",
        f"max_{variation_item.pk}_{double.pk}": "2",
        f"max_{variation_item.pk}_{single.pk}": "4",  # ignored, not enabled
        "same_product_only": "on",
    }
    form = RoomsharingSettingsForm(event=event, data=data)
    assert form.is_valid(), form.errors
    form.save()

    products = {
        (rp.item_id, rp.variation_id): rp.max_people for rp in event.room_products.all()
    }
    assert products == {(item.pk, None): None, (variation_item.pk, double.pk): 2}
    assert event.settings.roomsharing__same_product_only is True

    # Unchecking a product removes it again.
    form = RoomsharingSettingsForm(
        event=event, data={f"enabled_{variation_item.pk}_{double.pk}": "on"}
    )
    assert form.is_valid(), form.errors
    form.save()
    assert list(event.room_products.values_list("item_id", flat=True)) == [
        variation_item.pk
    ]
    assert event.settings.roomsharing__same_product_only is False


def test_settings_form_rejects_zero_max(event, item):
    form = RoomsharingSettingsForm(
        event=event, data={f"enabled_{item.pk}": "on", f"max_{item.pk}": "0"}
    )
    assert not form.is_valid()


@pytest.mark.django_db
def test_settings_page(client, organizer, event, item):
    from pretix.base.models import Team, User

    user = User.objects.create_user("staff@example.com", "staff")
    team = Team.objects.create(
        organizer=organizer, name="Staff", all_events=True, all_event_permissions=True
    )
    team.members.add(user)
    client.login(email="staff@example.com", password="staff")

    url = "/control/event/dummy/dummy/roomsharing/"
    assert client.get(url).status_code == 200
    r = client.post(url, {f"enabled_{item.pk}": "on", f"max_{item.pk}": "3"})
    assert r.status_code == 302
    assert event.room_products.get().max_people == 3
    assert event.all_logentries().filter(action_type="pretix.event.settings").exists()


def test_migration_converts_old_setting(event, item, variation_item, historical_apps):
    event.settings.set("roomsharing__products", [str(item.pk), str(variation_item.pk)])
    migration_0003.convert_room_products(historical_apps, None)

    products = set(event.room_products.values_list("item_id", "variation_id"))
    single, double = variation_item.variations.order_by("pk")
    assert products == {
        (item.pk, None),
        (variation_item.pk, single.pk),
        (variation_item.pk, double.pk),
    }
    event.settings.flush()
    assert event.settings.get("roomsharing__products") is None


def test_migration_backfills_room_type(event, item, order, historical_apps):
    event.room_products.create(item=item)
    room = event.rooms.create(name="Room", password="secret")
    OrderRoom.objects.create(order=order, room=room, is_admin=True)

    migration_0003.backfill_room_types(historical_apps, None)
    room.refresh_from_db()
    assert room.item == item
    assert room.variation is None


def test_event_copy_copies_room_products(organizer, event, item, variation_item):
    single, double = variation_item.variations.order_by("pk")
    event.room_products.create(item=item, max_people=2)
    event.room_products.create(item=variation_item, variation=double, max_people=4)

    copy = Event.objects.create(
        organizer=organizer, name="Copy", slug="copy", date_from=event.date_from
    )
    copy.copy_data_from(event)

    copied = {
        (
            str(rp.item.name),
            str(rp.variation.value) if rp.variation else None,
            rp.max_people,
        )
        for rp in RoomProduct.objects.filter(event=copy)
    }
    assert copied == {("Ticket", None, 2), ("Hotel", "Double", 4)}
    assert all(rp.item.event == copy for rp in copy.room_products.all())
