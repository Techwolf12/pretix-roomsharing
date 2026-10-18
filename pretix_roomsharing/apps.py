from django.utils.translation import gettext_lazy

from . import __version__

try:
    from pretix.base.plugins import PLUGIN_LEVEL_EVENT, PluginConfig
except ImportError:
    raise RuntimeError("Please use pretix 2026.3 or above to run this plugin!")


class PluginApp(PluginConfig):
    name = "pretix_roomsharing"
    verbose_name = "Roomsharing"
    # Keep integer primary keys; pretix's BigAutoField default would rewrite existing tables.
    default_auto_field = "django.db.models.AutoField"

    class PretixPluginMeta:
        name = gettext_lazy("Roomsharing")
        author = "Christiaan de Die le Clercq (techwolf12)"
        description = gettext_lazy(
            "Pretix roomsharing allows attendees to setup with which people they'd like to share a room"
        )
        visible = True
        version = __version__
        category = "FEATURE"
        level = PLUGIN_LEVEL_EVENT
        compatibility = "pretix>=2026.3.0"
        settings_links = [
            (
                (gettext_lazy("Settings"), gettext_lazy("Roomsharing")),
                "plugins:pretix_roomsharing:control.room.settings",
                {},
            ),
        ]
        navigation_links = [
            (
                (gettext_lazy("Rooms"),),
                "plugins:pretix_roomsharing:event.room.list",
                {},
            ),
        ]

    def ready(self):
        from . import signals  # NOQA
