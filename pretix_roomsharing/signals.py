# Register your receivers here
from django.dispatch import receiver
from django.urls import resolve, reverse
from django.utils.translation import gettext_lazy as _
from pretix.base.i18n import LazyI18nString
from pretix.base.services.cart import CartError
from pretix.base.settings import settings_hierarkey
from pretix.base.signals import order_approved, validate_cart
from pretix.control.signals import nav_event_settings
from pretix.base.models import Event, Question, QuestionAnswer
import logging
import json

logger = logging.getLogger(__name__)

@receiver(nav_event_settings, dispatch_uid="pretix_roomsharing")
def navbar_settings(sender, request, **kwargs):
    url = resolve(request.path_info)
    return [
        {
            "label": _("Roomsharing"),
            "url": reverse(
                "plugins:pretix_roomsharing:roomsharing__settings",
                kwargs={
                    "event": request.event.slug,
                    "organizer": request.organizer.slug,
                },
            ),
            "active": url.namespace == "plugins:pretix_roomsharing"
            and url.url_name == "roomsharing__settings",
        }
    ]

# Once the order gets approved, add a registration ID to the order
#@receiver(order_approved, dispatch_uid="pretix_roomsharing")
#def order_approved(request, *args, **kwargs):
    # TODO Set order's reg ID
    # max(QuestionAnswer.objects.get(question = )) # TODO Get highest current ID or 1
#    logger.info("order_approved: ")
