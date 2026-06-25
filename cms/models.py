from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


# =====================================
# CORE VALUES
# =====================================

class CoreValue(models.Model):
    core_value_id = models.AutoField(primary_key=True)
    core_value_name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'core_values'
        managed = False

    def __str__(self):
        return self.core_value_name


# =====================================
# EVENTS
# =====================================

class Event(models.Model):

    STATUS_DRAFT     = 'draft'
    STATUS_PUBLISHED = 'published'
    STATUS_ONGOING   = 'ongoing'
    STATUS_COMPLETED = 'completed'
    STATUS_ARCHIVED  = 'archived'

    STATUS_CHOICES = [
        (STATUS_DRAFT,     'Draft'),
        (STATUS_PUBLISHED, 'Published'),
        (STATUS_ONGOING,   'Ongoing'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_ARCHIVED,  'Archived'),
    ]

    event_id    = models.AutoField(primary_key=True)
    event_name  = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    location    = models.CharField(max_length=255, null=True, blank=True)
    event_date  = models.DateField(null=True, blank=True)
    event_time  = models.TimeField(null=True, blank=True)
    rating      = models.DecimalField(max_digits=2, decimal_places=1, null=True, blank=True)
    image_url   = models.TextField(null=True, blank=True)
    created_by  = models.IntegerField(null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    # ── New Lifecycle Fields ──────────────────────────────────────
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )
    registration_deadline = models.DateTimeField(null=True, blank=True)
    attendance_open_time  = models.DateTimeField(null=True, blank=True)
    attendance_close_time = models.DateTimeField(null=True, blank=True)
    capacity              = models.PositiveIntegerField(null=True, blank=True)
    person_in_charge      = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'events'
        managed = True   # Changed to True so Django manages migrations

    def __str__(self):
        return self.event_name

    # ── Helpers ──────────────────────────────────────────────────
    @property
    def is_visible_to_public(self):
        """Only Published events show on Explore."""
        return self.status == self.STATUS_PUBLISHED

    @property
    def is_visible_to_participants(self):
        """Published + Completed events visible to participants."""
        return self.status in (self.STATUS_PUBLISHED, self.STATUS_COMPLETED, self.STATUS_ONGOING)

    @property
    def is_registration_open(self):
        now = timezone.now()
        if self.registration_deadline and now > self.registration_deadline:
            return False
        return self.status == self.STATUS_PUBLISHED

    @property
    def is_attendance_open(self):
        now = timezone.now()
        if self.attendance_open_time and self.attendance_close_time:
            return self.attendance_open_time <= now <= self.attendance_close_time
        return False

    @property
    def registered_count(self):
        return EventRegistration.objects.filter(event_id=self.event_id).count()

    @property
    def is_full(self):
        if self.capacity is None:
            return False
        return self.registered_count >= self.capacity

    def get_status_badge_class(self):
        return {
            self.STATUS_DRAFT:     'badge-secondary',
            self.STATUS_PUBLISHED: 'badge-success',
            self.STATUS_ONGOING:   'badge-primary',
            self.STATUS_COMPLETED: 'badge-info',
            self.STATUS_ARCHIVED:  'badge-dark',
        }.get(self.status, 'badge-secondary')


class EventCoreValue(models.Model):
    event       = models.ForeignKey(Event,     on_delete=models.CASCADE, db_column='event_id')
    core_value  = models.ForeignKey(CoreValue, on_delete=models.CASCADE, db_column='core_value_id')

    class Meta:
        db_table = 'event_core_values'
        managed = False


class EventRegistration(models.Model):
    """
    Pendaftaran peserta event — TANPA login.

    Email berperan sebagai identitas unik peserta. Kombinasi (email, event)
    hanya boleh muncul satu kali: satu email = satu pendaftaran per event.
    """
    registration_id = models.AutoField(primary_key=True)

    event_id   = models.IntegerField(null=True, blank=True, db_index=True)
    event_name = models.CharField(max_length=255)

    full_name = models.CharField(max_length=255)
    email     = models.EmailField(max_length=255)
    province  = models.CharField(max_length=100, blank=True, null=True)
    territory = models.CharField(max_length=100, blank=True, null=True)
    phone        = models.CharField(max_length=50, blank=True, null=True)
    organization = models.CharField(max_length=255, blank=True, null=True)

    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'event_registrations'
        ordering = ['-registered_at']
        constraints = [
            models.UniqueConstraint(
                Lower('email'), 'event_id',
                name='uniq_lower_email_per_event',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} — {self.event_name}"


# =====================================
# NEWS EDITIONS
# =====================================
class NewsEdition(models.Model):
    edition_id   = models.AutoField(primary_key=True)
    edition_name = models.CharField(max_length=100)

    class Meta:
        db_table = 'news_editions'
        managed = False

    def __str__(self):
        return self.edition_name

class News(models.Model):
    news_id    = models.AutoField(primary_key=True)
    title      = models.CharField(max_length=255, null=True, blank=True)
    content    = models.TextField(null=True, blank=True)
    image_url  = models.TextField(null=True, blank=True)
    image_file = models.ImageField(
        upload_to='news/',
        null=True,
        blank=True
    )
    edition    = models.ForeignKey(
        NewsEdition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='edition_id',
        related_name='news',
    )
    created_by = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'news'
        managed = False

    def __str__(self):
        return self.title or ''


# =====================================
# ATTRIBUTES
# =====================================

ATTRIBUTE_TYPES = (
    ('playbook', 'Playbook'),
    ('poster',   'Poster'),
    ('asset',    'Asset'),
    ('logo',     'Logo'),
    ('video',    'Video'),
)


class Attribute(models.Model):
    attribute_id   = models.AutoField(primary_key=True)
    attribute_name = models.CharField(max_length=255, null=True, blank=True)
    attribute_type = models.CharField(max_length=50, choices=ATTRIBUTE_TYPES, null=True, blank=True)
    file_url       = models.TextField(null=True, blank=True)
    created_by     = models.IntegerField(null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'attributes'
        managed = False

    def __str__(self):
        return self.attribute_name or ''


# =====================================
# FEEDBACK
# =====================================

class Feedback(models.Model):

    SENTIMENT_CHOICES = [
        ('positive', 'Positive'),
        ('neutral',  'Neutral'),
        ('negative', 'Negative'),
    ]

    SOURCE_CHOICES = [
        ('web',    'Web'),
        ('mobile', 'Mobile'),
        ('api',    'API'),
    ]

    feedback_id     = models.AutoField(primary_key=True)

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        db_column='event_id',
        null=True,
        blank=True
    )

    session_id      = models.CharField(max_length=100, blank=True, null=True)
    message         = models.TextField()
    sentiment       = models.CharField(max_length=20, choices=SENTIMENT_CHOICES, default='neutral')
    rating          = models.IntegerField(null=True, blank=True)
    source_platform = models.CharField(max_length=50, choices=SOURCE_CHOICES, default='web')
    created_at      = models.DateTimeField(auto_now_add=True)
    ai_response     = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'feedback'
        managed = False
        ordering = ['-created_at']


# =====================================
# VISITOR LOGS
# =====================================

class VisitorLog(models.Model):
    log_id           = models.AutoField(primary_key=True)
    page_visited     = models.CharField(max_length=255, null=True, blank=True)
    visit_duration   = models.IntegerField(null=True, blank=True, help_text="Duration in seconds")
    engagement_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    visitor_ip       = models.CharField(max_length=100, null=True, blank=True)
    visited_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'visitor_logs'
        managed = False

    def __str__(self):
        return self.page_visited or ''


# =====================================
# ADMIN ACTIVITY
# =====================================

class AdminActivity(models.Model):
    activity_id = models.AutoField(primary_key=True)
    admin_id    = models.IntegerField(null=True, blank=True)
    activity    = models.TextField()
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'admin_activity'
        managed = False

    def __str__(self):
        return self.activity


# =====================================
# ATTENDANCE
# =====================================

class Attendance(models.Model):

    STATUS_PENDING  = 'pending_verification'
    STATUS_VERIFIED = 'verified'
    STATUS_REJECTED = 'rejected'

    STATUS_CHOICES = [
        (STATUS_PENDING,  'Pending Verification'),
        (STATUS_VERIFIED, 'Verified'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    attendance_id       = models.AutoField(primary_key=True)
    event_registration  = models.ForeignKey(
        EventRegistration,
        on_delete=models.CASCADE,
        related_name='attendances',
    )
    participant_email   = models.EmailField(max_length=255)
    photo_evidence      = models.ImageField(upload_to='attendance/', null=True, blank=True)
    latitude            = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    longitude           = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    attendance_timestamp = models.DateTimeField(auto_now_add=True)
    status              = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_PENDING)
    verified_at         = models.DateTimeField(null=True, blank=True)
    notes               = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'attendance'
        ordering = ['-attendance_timestamp']

    def __str__(self):
        return f"{self.participant_email} — {self.event_registration.event_name} [{self.status}]"