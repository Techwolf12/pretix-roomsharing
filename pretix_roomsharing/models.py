from django.db import models
from django.utils.translation import gettext_lazy as _
from pretix.base.models import LoggedModel


class Room(LoggedModel):
    event = models.ForeignKey(
        "pretixbase.Event", on_delete=models.CASCADE, related_name="rooms"
    )
    name = models.CharField(max_length=190)
    password = models.CharField(max_length=190, blank=True)
    created = models.DateTimeField(auto_now_add=True)

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
