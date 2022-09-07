from collections import defaultdict

from django.db.models import OuterRef, Count, Subquery, IntegerField

from pretix.base.models import SubEvent, Order, Event, OrderPosition, User
from pretix.base.services.orders import approve_order, OrderError, deny_order
from pretix.base.services.tasks import EventTask
from pretix.celery_app import app
import random

