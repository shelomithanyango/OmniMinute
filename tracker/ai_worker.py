"""
tracker/ai_worker.py
Offline AI pipeline: local transcription (faster-whisper) + local LLM cleanup (Ollama / Llama 3.1).
"""

import json
import logging
import re
from datetime import datetime

import requests
from faster_whisper import WhisperModel

from .models import Meeting, Task

logger = logging.getLogger(__name__)

WHISPER_MODEL_SIZE = "base"
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.1:8b"
OLLAMA_TIMEOUT_SECONDS = 300

_whisper_model = None


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        logger.info("Loading faster-whisper model (%s, %s)...", WHISPER_MODEL_SIZE, WHISPER_DEVICE)
        _whisper_model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )
    return _whisper_model


def transcribe_audio(audio_path: str) -> str:
    model = _get_whisper_model()
    segments, info = model.transcribe(audio_path, beam_size=5)
    logger.info("Detected language '%s' (p=%.2f)", info.language, info.language_probability)
    raw_text = " ".join(segment.text.strip() for segment in segments)
    return raw_text.strip()


SYSTEM_PROMPT = """You are an executive scribe for OmniMinute, a corporate meeting-minutes tool.

You will receive a raw, unfiltered meeting transcript. It may mix English, Kiswahili, and Sheng,
and will contain small talk, jokes, and tangents unrelated to actual business decisions
(for example phrases like "mambo vipi", "rada chafu", or "form ni gani").

Your job:
1. Strip out all banter, jokes, and off-topic tangents.
2. Translate/rephrase all surviving business content into clear, formal, professional English.
3. Extract concrete action items with an owner (if named), a priority guess (low/medium/urgent),
   and a due date if one was mentioned (YYYY-MM-DD, or null if not mentioned).
4. Produce a short 1-3 sentence executive summary.

Respond with ONLY valid JSON (no markdown fences, no commentary) matching exactly this shape:

{
  "clean_minutes": "string - the full cleaned, formal minutes text",
  "summary_snippet": "string - 1-3 sentence executive summary",
  "category": "string - one short label, e.g. 'Engineering', 'Sales', 'Operations'",
  "tangents_excluded": integer,
  "tasks": [
    {
      "task_description": "string",
      "owner_name": "string - 'Unassigned' if unknown",
      "priority": "low | medium | urgent",
      "due_date": "YYYY-MM-DD or null"
    }
  ]
}
"""


def _call_ollama(raw_transcript: str) -> dict:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": raw_transcript,
        "system": SYSTEM_PROMPT,
        "stream": False,
        "format": "json",
    }

    response = requests.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT_SECONDS)
    response.raise_for_status()

    body = response.json()
    model_output = body.get("response", "").strip()
    model_output = re.sub(r"^```(json)?|```$", "", model_output, flags=re.MULTILINE).strip()

    return json.loads(model_output)


def run_ai_pipeline(meeting_id: int, audio_path: str) -> None:
    try:
        meeting = Meeting.objects.get(pk=meeting_id)
    except Meeting.DoesNotExist:
        logger.error("run_ai_pipeline: Meeting %s not found", meeting_id)
        return

    try:
        raw_text = transcribe_audio(audio_path)
        meeting.raw_transcript = raw_text
        meeting.save(update_fields=["raw_transcript"])

        structured = _call_ollama(raw_text)

        meeting.clean_minutes = structured.get("clean_minutes", "")
        meeting.summary_snippet = structured.get("summary_snippet", meeting.summary_snippet)
        meeting.category = structured.get("category", meeting.category)
        meeting.tangents_excluded = int(structured.get("tangents_excluded", 0) or 0)

        tasks_data = structured.get("tasks", []) or []
        for task_item in tasks_data:
            due_date_raw = task_item.get("due_date")
            due_date = None
            if due_date_raw:
                try:
                    due_date = datetime.strptime(due_date_raw, "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    due_date = None

            priority = task_item.get("priority")
            if priority not in ("low", "medium", "urgent"):
                priority = "medium"

            Task.objects.create(
                meeting=meeting,
                task_description=(task_item.get("task_description") or "Untitled task").strip(),
                owner_name=task_item.get("owner_name") or "Unassigned",
                priority=priority,
                due_date=due_date,
            )

        meeting.action_items_count = meeting.tasks.count()
        meeting.status = "synthesized"
        meeting.save()

        logger.info("Meeting %s synthesized successfully (%s tasks).", meeting_id, meeting.action_items_count)

    except Exception:
        logger.exception("run_ai_pipeline failed for meeting %s", meeting_id)
        meeting.summary_snippet = "AI processing failed - check server logs."
        meeting.save(update_fields=["summary_snippet"])