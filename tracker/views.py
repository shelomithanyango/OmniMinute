"""
tracker/views.py
API controllers for OmniMinute: audio intake, archive feed, task sync, PDF export.
"""

import io
import os
import threading
import uuid

from django.conf import settings
from django.http import FileResponse
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .ai_worker import run_ai_pipeline
from .models import Meeting, Task
from .serializers import MeetingSerializer, TaskSerializer

TEMP_AUDIO_DIR = os.path.join(settings.BASE_DIR, "temp_audio")


class AudioIntakeView(APIView):
    parser_classes = [MultiPartParser]

    def post(self, request, *args, **kwargs):
        audio_file = request.FILES.get("audio")
        if not audio_file:
            return Response(
                {"error": "No audio file provided under form key 'audio'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)

        extension = os.path.splitext(audio_file.name)[1] or ".wav"
        safe_filename = f"{uuid.uuid4().hex}{extension}"
        saved_path = os.path.join(TEMP_AUDIO_DIR, safe_filename)

        with open(saved_path, "wb+") as destination:
            for chunk in audio_file.chunks():
                destination.write(chunk)

        title = request.data.get("title", "Untitled Meeting")
        channel_name = request.data.get("channel_name", "General Channel")

        meeting = Meeting.objects.create(
            title=title,
            channel_name=channel_name,
            status="processing",
        )

        thread = threading.Thread(
            target=run_ai_pipeline,
            args=(meeting.id, saved_path),
            daemon=True,
        )
        thread.start()

        return Response(
            {
                "status": "processing",
                "meeting_id": meeting.id,
                "message": "Audio received. Synthesis running in the background.",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class ArchiveFeedView(APIView):
    def get(self, request, *args, **kwargs):
        meetings = Meeting.objects.all().order_by("-date_created")
        serializer = MeetingSerializer(meetings, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TaskSyncView(APIView):
    def patch(self, request, pk, *args, **kwargs):
        try:
            task = Task.objects.get(pk=pk)
        except Task.DoesNotExist:
            return Response({"error": "Task not found."}, status=status.HTTP_404_NOT_FOUND)

        task.is_completed = not task.is_completed
        task.save(update_fields=["is_completed"])

        serializer = TaskSerializer(task)
        return Response(serializer.data, status=status.HTTP_200_OK)


class PDFStreamView(APIView):
    def get(self, request, pk, *args, **kwargs):
        try:
            meeting = Meeting.objects.get(pk=pk)
        except Meeting.DoesNotExist:
            return Response({"error": "Meeting not found."}, status=status.HTTP_404_NOT_FOUND)

        buffer = self._build_pdf(meeting)

        filename = f"{meeting.title.replace(' ', '_')}_minutes.pdf"
        return FileResponse(
            buffer,
            as_attachment=True,
            filename=filename,
            content_type="application/pdf",
        )

    @staticmethod
    def _build_pdf(meeting):
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=LETTER,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            rightMargin=0.75 * inch,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("TitleStyle", parent=styles["Title"], fontSize=20, spaceAfter=6)
        meta_style = ParagraphStyle("MetaStyle", parent=styles["Normal"], textColor=colors.grey, spaceAfter=14)
        heading_style = styles["Heading2"]
        body_style = styles["BodyText"]

        elements = []
        elements.append(Paragraph(meeting.title, title_style))
        elements.append(
            Paragraph(
                f"{meeting.meeting_date_text} &nbsp;|&nbsp; {meeting.time_window} "
                f"&nbsp;|&nbsp; {meeting.channel_name}",
                meta_style,
            )
        )

        elements.append(Paragraph("Executive Summary", heading_style))
        elements.append(Paragraph(meeting.summary_snippet or "No summary available.", body_style))
        elements.append(Spacer(1, 12))

        elements.append(Paragraph("Minutes", heading_style))
        elements.append(
            Paragraph((meeting.clean_minutes or "No minutes available.").replace("\n", "<br/>"), body_style)
        )
        elements.append(Spacer(1, 16))

        elements.append(Paragraph("Action Items", heading_style))
        tasks = list(meeting.tasks.all())
        if tasks:
            table_data = [["Task", "Owner", "Priority", "Due Date", "Done"]]
            for task in tasks:
                table_data.append(
                    [
                        task.task_description,
                        task.owner_name,
                        task.priority.capitalize(),
                        task.due_date.strftime("%Y-%m-%d") if task.due_date else "-",
                        "Yes" if task.is_completed else "No",
                    ]
                )

            task_table = Table(
                table_data,
                colWidths=[2.4 * inch, 1.1 * inch, 0.9 * inch, 1.0 * inch, 0.6 * inch],
            )
            task_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
                    ]
                )
            )
            elements.append(task_table)
        else:
            elements.append(Paragraph("No action items recorded.", body_style))

        doc.build(elements)
        buffer.seek(0)
        return buffer
