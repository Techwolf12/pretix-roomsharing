from django.utils.translation import gettext_lazy

try:
    from pretix.base.plugins import PluginConfig
except ImportError:
    raise RuntimeError("Please use pretix 2.7 or above to run this plugin!")

__version__ = "0.1.2"


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
        compatibility = "pretix>=2.7.0"

    def ready(self):
        from . import signals  # NOQA


default_app_config = "pretix_roomsharing.PluginApp"
