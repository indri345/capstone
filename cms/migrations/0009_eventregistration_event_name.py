from django.db import migrations, models


def copy_event_names(apps, schema_editor):
    EventRegistration = apps.get_model("cms", "EventRegistration")
    Event = apps.get_model("cms", "Event")
    for reg in EventRegistration.objects.all():
        if hasattr(reg, "event_id") and reg.event_id:
            try:
                event = Event.objects.get(event_id=reg.event_id)
                reg.event_name = event.event_name
                reg.save(update_fields=["event_name"])
            except Event.DoesNotExist:
                reg.event_name = f"Event #{reg.event_id}"
                reg.save(update_fields=["event_name"])


class Migration(migrations.Migration):

    dependencies = [
        ("cms", "0008_eventregistration"),
    ]

    operations = [
        migrations.AddField(
            model_name="eventregistration",
            name="event_name",
            field=models.CharField(default="", max_length=255),
            preserve_default=False,
        ),
        migrations.RunPython(copy_event_names, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="eventregistration",
            name="event",
        ),
    ]
