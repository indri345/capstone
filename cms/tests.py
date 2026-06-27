from datetime import datetime, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from .models import Event


class EventAttendanceLogicTests(TestCase):
    def test_attendance_opens_after_thirty_minutes_when_no_window_is_set(self):
        event = Event.objects.create(
            event_name='Test Event',
            event_date=timezone.now().date(),
            event_time=(timezone.now() + timedelta(minutes=5)).time(),
        )

        with patch('cms.models.timezone.now', return_value=timezone.make_aware(datetime(2024, 1, 1, 10, 0, 0))):
            self.assertFalse(event.is_attendance_open)

        with patch('cms.models.timezone.now', return_value=timezone.make_aware(datetime(2024, 1, 1, 10, 31, 0))):
            self.assertTrue(event.is_attendance_open)

    def test_status_label_uses_in_progress_text(self):
        event = Event(status=Event.STATUS_ONGOING)
        self.assertEqual(event.get_status_display(), 'In Progress')
