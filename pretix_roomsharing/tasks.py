from collections import defaultdict

from django.db.models import OuterRef, Count, Subquery, IntegerField

from pretix.base.models import SubEvent, Order, Event, OrderPosition, User
from pretix.base.services.orders import approve_order, OrderError, deny_order
from pretix.base.services.tasks import EventTask
from pretix.celery_app import app
import random


@app.task(bind=True, base=EventTask)
def run_rejection(self, event: Event, subevent_id: int, user_id: int):
    user = User.objects.get(pk=user_id)

    subevent_count = OrderPosition.objects.filter(
        order=OuterRef('pk'),
        subevent_id=subevent_id,
        item__admission=True
    ).order_by().values('order').annotate(k=Count('id')).values('k')
    orders = list(event.orders.annotate(
        pcnt_subevent=Subquery(subevent_count, output_field=IntegerField()),
    ).filter(
        pcnt_subevent__gte=1,
        require_approval=True,
        status=Order.STATUS_PENDING,
    ))
    self.update_state(
        state='PROGRESS',
        meta={'value': 0}
    )
    for i, order in enumerate(orders):
        deny_order(
            order,
            user=user,
            send_mail=True,
        )
        if i % 50 == 0:
            self.update_state(
                state='PROGRESS',
                meta={'value': round(i / len(orders) * 100, 2)}
            )

    return len(orders)
