Changelog
=========

0.3.1 (2026-10-20)
------------------

- Add Dutch translations, and German translations (formal and informal).

0.3.0 (2026-10-20)
------------------

- Give rooms a room number, e.g. the hotel room. Staff set it in the backend,
  and attendees can see it on their order page if enabled in the settings.
- Let staff create rooms and add orders to them from the backend. Room changes
  by staff are logged on the order.
- Add a read-only ``/rooms/`` API endpoint with room details, occupancy and
  member tickets, and include the order's room in the order API's
  ``plugin_data``.
- Add room name and room number placeholders for ticket and badge layouts.
  They are also available in the check-in API's ``pdf_data``.

0.2.1 (2026-10-18)
------------------

- Fix the 0.2.0 database migration failing on installations that already had
  rooms with members.

0.2.0 (2026-10-18)
------------------

**Upgrade note:** the room products setting is replaced by per-product
settings. Existing settings are migrated automatically: a product with
variations becomes one entry per variation.

- Select room products per variation, and set a maximum number of people per
  room for each.
- Optionally only let people with the same ticket share a room. Rooms take
  their type from the ticket of the person who created them.
- Enforce the room size and ticket type when attendees create, join or change
  rooms, and again when the order is placed.
- Show the room type and how many places are taken in the backend and on the
  attendee's order page. Staff can change a room's type.
- Let staff choose what room members see about each other: order code,
  attendee name and/or answers to questions.
- Make the "assign me a random room" option configurable.
- Fix a crash on the order page and in checkout when no room products were
  configured.
- Fix changing an order's room from the backend.
- Fix attendees being able to change rooms on canceled or expired orders, or
  after the modification deadline.
- Fix room statistics: "All tickets, total" only counted tickets awaiting
  approval. The statistics page now has its own menu entry.
- Fix the "room changed" and "room deleted" log messages being swapped.
- Hide the room password when creating a room.
- Only show the Rooms page to users who can change orders.
- Use pretix's new permission names and log entry types, and link to the
  settings from the plugin list.
- Requires pretix 2026.3.0 or newer and Python 3.11 or newer.

0.1.13 and earlier (2022-09-07 to 2024-03-10)
---------------------------------------------

- Let attendees create or join a room with friends during checkout, or be
  assigned a random room.
- Choose which products include a room.
- Manage rooms and see room statistics in the backend.
