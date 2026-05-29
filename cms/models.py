from django.db import models


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
    event_id    = models.AutoField(primary_key=True)
    event_name  = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    location    = models.CharField(max_length=255, null=True, blank=True)
    event_date  = models.DateField(null=True, blank=True)
    event_time  = models.TimeField(null=True, blank=True)
    rating      = models.DecimalField(max_digits=2, decimal_places=1, null=True, blank=True)
    image_url   = models.TextField(null=True, blank=True)
    created_by  = models.IntegerField(null=True, blank=True)   # FK ke tabel admin (unmanaged)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'events'
        managed = False

    def __str__(self):
        return self.event_name



class EventCoreValue(models.Model):
    # PK integer biasa (bukan AutoField composite)
    event       = models.ForeignKey(Event,     on_delete=models.CASCADE, db_column='event_id')
    core_value  = models.ForeignKey(CoreValue, on_delete=models.CASCADE, db_column='core_value_id')

    class Meta:
        db_table = 'event_core_values'
        managed = False


class EventRegistration(models.Model):
    registration_id = models.AutoField(primary_key=True)
    event_name = models.CharField(max_length=255)
    full_name = models.CharField(max_length=255)
    email = models.EmailField(max_length=255)
    phone = models.CharField(max_length=50)
    organization = models.CharField(max_length=255, blank=True, null=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'event_registrations'
        ordering = ['-registered_at']

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
# DB table: attributes
# Kolom: attribute_id, attribute_name, attribute_type, file_url, created_by, created_at
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
    file_url       = models.TextField(null=True, blank=True)   # DB pakai text file_url, bukan file
    created_by     = models.IntegerField(null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'attributes'
        managed = False

    def __str__(self):
        return self.attribute_name or ''


# =====================================
# FEEDBACK
# DB table: feedback
# Kolom: feedback_id, session_id, message, sentiment, rating,
#        source_platform, created_at, ai_response
# ===========        ordering = ['-created_at']

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
# DB table: visitor_logs
# Kolom: log_id, page_visited, visit_duration, engagement_score,
#        visitor_ip, visited_at
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
# DB table: admin_activity
# Kolom: activity_id, admin_id, activity, created_at
# =====================================

class AdminActivity(models.Model):
    activity_id = models.AutoField(primary_key=True)
    admin_id    = models.IntegerField(null=True, blank=True)   # FK ke tabel admin
    activity    = models.TextField()
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'admin_activity'
        managed = False

    def __str__(self):
        return self.activity