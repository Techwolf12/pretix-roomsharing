from django.db import models
from django.utils.translation import gettext_lazy as _
from pretix.base.models import LoggedModel


class RoomProduct(models.Model):
    """A product or variation whose buyers take part in roomsharing."""

    event = models.ForeignKey(
        "pretixbase.Event", on_delete=models.CASCADE, related_name="room_products"
    )
    item = models.ForeignKey(
        "pretixbase.Item", on_delete=models.CASCADE, related_name="+"
    )
    variation = models.ForeignKey(
        "pretixbase.ItemVariation",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    max_people = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_("Maximum number of people per room")
    )

    def __str__(self):
        if self.variation_id:
            return f"{self.item} – {self.variation}"
        return str(self.item)


class Room(LoggedModel):
    event = models.ForeignKey(
        "pretixbase.Event", on_delete=models.CASCADE, related_name="rooms"
    )
    name = models.CharField(max_length=190)
    password = models.CharField(max_length=190, blank=True)
    room_number = models.CharField(
        max_length=190,
        blank=True,
        default="",
        verbose_name=_("Room number"),
        help_text=_("For example the hotel room number. Set by staff."),
    )
    created = models.DateTimeField(auto_now_add=True)
    # The room type, taken from the ticket of the person who created the room.
    item = models.ForeignKey(
        "pretixbase.Item",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Product"),
    )
    variation = models.ForeignKey(
        "pretixbase.ItemVariation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Variation"),
    )

    class Meta:
        unique_together = (("event", "name"),)
        ordering = ("name",)

    def __str__(self):
        return self.name


class OrderRoom(models.Model):
    order = models.OneToOneField(
        "pretixbase.Order", related_name="orderroom", on_delete=models.CASCADE
    )
    room = models.ForeignKey(
        Room,
        related_name="orderrooms",
        on_delete=models.CASCADE,
        verbose_name=_("Room"),
    )
    is_admin = models.BooleanField(default=False, verbose_name=_("Room administrator"))
