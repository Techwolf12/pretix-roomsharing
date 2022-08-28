from django import forms
from django.forms.widgets import CheckboxSelectMultiple, RadioSelect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from i18nfield.forms import I18nFormField, I18nTextInput
from pretix.base.forms import SettingsForm
from pretix.base.models import Event
from pretix.control.views.event import EventSettingsFormView, EventSettingsViewMixin
import logging
import json

logger = logging.getLogger(__name__)


class RoomsharingSettingsForm(SettingsForm):
    roomsharing__list = forms.MultipleChoiceField(
        choices=[],
        label=_("Roomsharing products"),
        required=False,
        widget=CheckboxSelectMultiple,
    )

    def __init__(self, *args, **kwargs):
        event = kwargs.get("obj")
        super().__init__(*args, **kwargs)

        choices = (
            (str(i["id"]), i["name"]) for i in event.items.values("name", "id").all()
        )
        self.fields["roomsharing__list"].choices = choices
        logger.info('room' + json.dumps(dir(event)))



class SettingsView(EventSettingsViewMixin, EventSettingsFormView):
    model = Event
    form_class = RoomsharingSettingsForm
    template_name = "pretix_roomsharing/settings.html"
    permission = "can_change_settings"

    def get_success_url(self):
        return reverse(
            "plugins:pretix_roomsharing:roomsharing__settings",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )
