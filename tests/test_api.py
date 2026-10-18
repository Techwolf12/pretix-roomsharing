import pytest
from django.test import Client
from pretix.base.models import Order, Team

from pretix_roomsharing.models import OrderRoom

API = "/api/v1/organizers/dummy/events/dummy"


def token_client(organizer, **permissions):
    team = Team.objects.create(organizer=organizer, name="API", all_events=True)
    for k, v in permissions.items():
        setattr(team, k, v)
    team.save()
    token = team.tokens.create(name="Test token")
    return Client(HTTP_AUTHORIZATION=f"Token {token.token}")


@pytest.fixture
def room(event, item, order):
    event.room_products.create(item=item, max_people=4)
    room = event.rooms.create(
        name="Room 1", password="secret", room_number="101", item=item
    )
    OrderRoom.objects.create(order=order, room=room, is_admin=True)
    order.status = Order.STATUS_PAID
    order.save()
    return room


@pytest.fixture
def reader(organizer):
    return token_client(organizer, limit_event_permissions={"event.orders:read": True})


@pytest.mark.django_db
def test_list_rooms(reader, room, order, item):
    r = reader.get(f"{API}/rooms/")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    position = order.positions.get()
    assert data["results"][0] == {
        "id": room.pk,
        "name": "Room 1",
        "room_number": "101",
        "item": item.pk,
        "variation": None,
        "capacity": 4,
        "occupancy": 1,
        "members": [
            {
                "order": order.code,
                "position": position.pk,
                "positionid": position.positionid,
                "attendee_name": None,
                "is_admin": True,
            }
        ],
    }
    assert "password" not in data["results"][0]


@pytest.mark.django_db
def test_room_detail(reader, room):
    r = reader.get(f"{API}/rooms/{room.pk}/")
    assert r.status_code == 200
    assert r.json()["room_number"] == "101"


@pytest.mark.django_db
def test_filter_rooms(reader, event, room, order):
    event.rooms.create(name="Room 2", password="secret", room_number="102")
    assert reader.get(f"{API}/rooms/").json()["count"] == 2
    by_order = reader.get(f"{API}/rooms/?order={order.code}").json()
    assert [r["name"] for r in by_order["results"]] == ["Room 1"]
    by_number = reader.get(f"{API}/rooms/?room_number=102").json()
    assert [r["name"] for r in by_number["results"]] == ["Room 2"]
    by_name = reader.get(f"{API}/rooms/?name=Room 2").json()
    assert [r["room_number"] for r in by_name["results"]] == ["102"]


@pytest.mark.django_db
def test_rooms_require_order_permission(organizer, room):
    client = token_client(
        organizer, limit_event_permissions={"event.vouchers:read": True}
    )
    assert client.get(f"{API}/rooms/").status_code == 403


@pytest.mark.django_db
def test_rooms_not_available_when_plugin_disabled(reader, event, room):
    event.plugins = ""
    event.save()
    assert reader.get(f"{API}/rooms/").status_code == 404


@pytest.mark.django_db
def test_order_api_contains_room(reader, room, order):
    expected = {"id": room.pk, "name": "Room 1", "room_number": "101"}
    data = reader.get(f"{API}/orders/{order.code}/").json()
    assert data["plugin_data"]["roomsharing"] == {"room": expected}
    assert data["positions"][0]["plugin_data"]["roomsharing"] == {"room": expected}


@pytest.mark.django_db
def test_order_api_without_room(reader, event, order):
    data = reader.get(f"{API}/orders/{order.code}/").json()
    assert data["plugin_data"]["roomsharing"] == {"room": None}


@pytest.mark.django_db
def test_checkin_redeem_contains_room(organizer, event, room, order):
    # The check-in API doesn't include plugin_data, but it includes the ticket
    # placeholders in pdf_data.
    clist = event.checkin_lists.create(name="Main", all_products=True)
    client = token_client(organizer, all_event_permissions=True)
    r = client.post(
        "/api/v1/organizers/dummy/checkinrpc/redeem/?pdf_data=true",
        {"secret": order.positions.get().secret, "lists": [clist.pk]},
        content_type="application/json",
    )
    assert r.status_code == 201, r.content
    pdf_data = r.json()["position"]["pdf_data"]
    assert pdf_data["roomsharing_room_name"] == "Room 1"
    assert pdf_data["roomsharing_room_number"] == "101"


@pytest.mark.django_db
def test_checkin_list_positions_contain_room(organizer, event, room, order):
    clist = event.checkin_lists.create(name="Main", all_products=True)
    client = token_client(organizer, all_event_permissions=True)
    r = client.get(f"{API}/checkinlists/{clist.pk}/positions/?pdf_data=true")
    assert r.status_code == 200, r.content
    pdf_data = r.json()["results"][0]["pdf_data"]
    assert pdf_data["roomsharing_room_number"] == "101"


def test_placeholders_without_room(event, order):
    from pretix_roomsharing.signals import room_layout_text_variables

    variables = room_layout_text_variables(event)
    position = order.positions.get()
    for key in ("roomsharing_room_name", "roomsharing_room_number"):
        assert variables[key]["evaluate"](position, order, event) == ""
