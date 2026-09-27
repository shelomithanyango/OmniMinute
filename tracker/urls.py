from django.urls import path
from .views import AudioIntakeView, ArchiveFeedView, TaskSyncView, PDFStreamView

urlpatterns = [
    path('meetings/upload/', AudioIntakeView.as_view(), name='audio-intake'),
    path('meetings/history/', ArchiveFeedView.as_view(), name='archive-feed'),
    path('tasks/<int:pk>/toggle/', TaskSyncView.as_view(), name='task-toggle'),
    path('meetings/<int:pk>/export/', PDFStreamView.as_view(), name='pdf-export'),
]