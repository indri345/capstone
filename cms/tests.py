from datetime import datetime, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Attribute, Event


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


class ExploreAdminAttributeTests(TestCase):
    def test_admin_explore_renders_attribute_data_from_database(self):
        attribute = Attribute.objects.create(
            attribute_name='Poster Uji Coba',
            attribute_type='poster',
            file_url='https://example.com/poster.pdf',
        )

        session = self.client.session
        session['is_admin'] = True
        session.save()

        response = self.client.get(reverse('admin_explore'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, attribute.attribute_name)
        self.assertContains(response, attribute.attribute_type)
        self.assertContains(response, attribute.file_url)
        self.assertContains(response, 'data-gdrive="https://example.com/poster.pdf"')
