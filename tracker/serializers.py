from rest_framework import serializers
from .models import Meeting, Task

class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ['id', 'task_description', 'owner_name', 'priority', 'due_date', 'is_completed']

class MeetingSerializer(serializers.ModelSerializer):
    tasks = TaskSerializer(many=True, read_only=True)

    class Meta:
        model = Meeting
        fields = [
            'id', 'date_created', 'title', 'meeting_date_text', 'time_window', 
            'duration_recorded', 'channel_name', 'status', 'action_items_count',
            'category', 'summary_snippet', 'attendee_count', 'language_indicator',
            'tangents_excluded', 'banter_duration_filtered', 'raw_transcript', 'clean_minutes', 'tasks'
        ]