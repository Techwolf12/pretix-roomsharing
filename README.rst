Roomsharing
==========================

This is a plugin for `pretix`_. 

Let attendees choose who they share a room with. Perfect for events with included accommodation, like conferences, camps, retreats and conventions.

During checkout, attendees with a room ticket create a room and share its name and password with their friends, who then join it. They can also ask to be assigned a random room. Attendees can change their room later from their order page.

Features
--------

* Choose which products, or individual product variations, include a room
* Set a maximum number of people per room for each product or variation. Full rooms can't be joined.
* Optionally only let people with the same ticket share a room, e.g. keep "Single" and "Double" rooms apart
* Decide whether attendees may be assigned a random room, or must create or join one
* Choose what roommates see about each other: order code, attendee name and/or answers to your own questions
* Manage rooms in the backend: see who is in which room and how full it is, move orders between rooms, and change or delete rooms
* Give rooms a room number (e.g. the hotel room), visible to staff and optionally to attendees
* Room statistics per product and date, with a metrics endpoint for monitoring
* REST API and ticket placeholders with each attendee's room, e.g. for check-in apps or badges
* Respects your order modification deadline, and works with event series

Requires pretix 2026.3 or newer.


API
---

All endpoints need an API token or user with the ``event.orders:read`` permission.

``GET /api/v1/organizers/{organizer}/events/{event}/rooms/``
    Lists the event's rooms, paginated like pretix's other endpoints. ``GET .../rooms/{id}/`` returns a single room.
    Filter with ``?order={order code}``, ``?room_number=`` or ``?name=``. Each room looks like this::

        {
            "id": 1,
            "name": "Room 1",
            "room_number": "101",
            "item": 12,
            "variation": 34,
            "capacity": 4,
            "occupancy": 2,
            "members": [
                {"order": "ABC12", "position": 56, "positionid": 1,
                 "attendee_name": "Alex Example", "is_admin": true}
            ]
        }

    ``item`` and ``variation`` are the room type, ``capacity`` is ``null`` for rooms without a maximum, and
    ``members`` lists the room tickets of pending and paid orders. Room passwords are never included.

Order and order position API (``plugin_data``)
    pretix's own order and order position endpoints include the order's room, or ``null``::

        "plugin_data": {"roomsharing": {"room": {"id": 1, "name": "Room 1", "room_number": "101"}}}

Check-in API and ticket layouts
    pretix's check-in endpoints don't include ``plugin_data``. Instead, the plugin adds the ticket placeholders
    ``roomsharing_room_name`` and ``roomsharing_room_number``, which appear in the check-in API's ``pdf_data`` when you
    pass ``?pdf_data=true`` (for example when redeeming a ticket). You can also print them on tickets and badges.


Development setup
-----------------

1. Make sure that you have a working `pretix development setup`_.

2. Clone this repository.

3. Activate the virtual environment you use for pretix development.

4. Execute ``pip install -e .`` within this directory to register this application with pretix's plugin registry.

5. Execute ``make`` within this directory to compile translations.

6. Restart your local pretix server. You can now use the plugin from this repository for your events by enabling it in
   the 'plugins' tab in the settings.

This plugin has CI set up to enforce a few code style rules. To check locally, you need these packages installed::

    pip install flake8 isort black docformatter

To check your plugin for rule violations, run::

    docformatter --check -r .
    black --check .
    isort -c .
    flake8 .

You can auto-fix some of these issues by running::

    docformatter -r .
    isort .
    black .

To automatically check for these issues before you commit, you can run ``.install-hooks``.


License
-------


Copyright 2022-2026 Christiaan de Die le Clercq (techwolf12)

Released under the terms of the Apache License 2.0



.. _pretix: https://github.com/pretix/pretix
.. _pretix development setup: https://docs.pretix.eu/en/latest/development/setup.html
