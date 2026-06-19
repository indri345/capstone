import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "capstone.settings")
django.setup()

from cms.models import VisitorLog
from django.db.models import Count
from django.db.models.functions import TruncDay, TruncMonth
from django.utils import timezone
from datetime import timedelta, date

today = timezone.localdate()
start_date = today - timedelta(days=6)
qs = VisitorLog.objects.filter(visited_at__date__gte=start_date, visited_at__date__lte=today)
agg = qs.annotate(period_val=TruncDay('visited_at')).values('period_val').annotate(count=Count('log_id'))

for item in agg:
    print(item)

