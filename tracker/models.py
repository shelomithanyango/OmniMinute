from django.db import models

class Meeting(models.Model):
    STATUS_CHOICES = [
        ('processing', 'Processing'),
        ('synthesized', 'Synthesized'),
        ('archived', 'Archived'),
    ]

    date_created = models.DateTimeField(auto_now_add=True)
    title = models.CharField(max_length=255, default="Untitled Meeting")
    meeting_date_text = models.CharField(max_length=100, default="Today")
    time_window = models.CharField(max_length=100, default="10:30 AM - 11:15 AM")
    duration_recorded = models.CharField(max_length=50, default="00:00:00")
    channel_name = models.CharField(max_length=255, default="General Channel")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='processing')
    action_items_count = models.IntegerField(default=0)
    category = models.CharField(max_length=100, default="General")
    summary_snippet = models.TextField(default="No preview snippet available.")
    attendee_count = models.IntegerField(default=0)
    language_indicator = models.CharField(max_length=100, default="En Cleaned")

    #  NEW MINUTES METRICS FIELDS:
    tangents_excluded = models.IntegerField(default=0) # Tracks number of tangents (e.g., 18)
    banter_duration_filtered = models.IntegerField(default=0) # Tracks minutes of clutter (e.g., 12)

    # Core raw AI blocks
    raw_transcript = models.TextField(blank=True, null=True)
    clean_minutes = models.TextField(blank=True, null=True) # Will store the markdown summary text blocks

    def __str__(self):
        return self.title

class Task(models.Model):
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('urgent', 'Urgent'),
    ]

    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="tasks")
    task_description = models.CharField(max_length=500)
    is_completed = models.BooleanField(default=False)
    
    #  NEW SMART TASK FIELDS:
    owner_name = models.CharField(max_length=255, default="Unassigned") # e.g., "David Mwangi"
    priority = models.CharField(max_length=50, choices=PRIORITY_CHOICES, default='medium')
    due_date = models.DateField(blank=True, null=True) # Captures dates (e.g., Oct 29, 2026)

    def __str__(self):
        return f"{self.task_description} ({self.owner_name})"
