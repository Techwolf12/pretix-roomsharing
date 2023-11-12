from django.apps import AppConfig
from django.utils.translation import gettext_lazy
from . import __version__


class PluginApp(PluginConfig):
    name = "pretix_roomsharing"
    verbose_name = "Roomsharing"

    class PretixPluginMeta:
        name = gettext_lazy("Roomsharing")
        author = "Christiaan de Die le Clercq (techwolf12)"
        description = gettext_lazy(
            "Pretix roomsharing allows attendees to setup with which people they'd like to share a room"
        )
        visible = True
        version = __version__
        category = "FEATURE"

    def ready(self):
        from . import signals  # NOQA