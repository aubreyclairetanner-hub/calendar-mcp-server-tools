from north_mcp_python_sdk import NorthMCPServer
import pickle
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.auth.transport.requests import Request

_default_port = 3001

mcp = NorthMCPServer(
    "AUBREY MCP SERVER", host="0.0.0.0", port=_default_port
)

# ---------------------------
# Google Calendar Authentication
# ---------------------------

SCOPES = [
    'https://www.googleapis.com/auth/calendar',  # Full calendar access (read + write)
    'https://www.googleapis.com/auth/drive',  # Full drive access (needed to create folders)
    'https://www.googleapis.com/auth/cloud-platform'
]

# ---- FILL IN THE PATH TO YOUR DOWNLOADED CREDENTIALS ----
CREDENTIALS_FILE = 'credentials.json'  # <-- replace if different

# Try to load saved token
try:
    with open('token.pkl', 'rb') as token_file:
        creds = pickle.load(token_file)
except FileNotFoundError:
    creds = None

# Check if credentials are invalid or expired
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        creds = flow.run_local_server(port=0)
    # Save the refreshed/new token
    with open('token.pkl', 'wb') as token_file:
        pickle.dump(creds, token_file)

# Build the Calendar service
calendar_service = build('calendar', 'v3', credentials=creds)

# Build the Drive service
drive_service = build('drive', 'v3', credentials=creds)

# Helper function for flexible date parsing
def parse_flexible_date(date_str):
    """
    Parse flexible date formats like 'today', 'yesterday', 'last Monday', or YYYY-MM-DD
    Returns date in YYYY-MM-DD format
    """
    if not date_str:
        return None

    date_str = date_str.lower().strip()
    now = datetime.now(timezone.utc)

    # Handle relative dates
    if date_str == 'today':
        return now.strftime('%Y-%m-%d')
    elif date_str == 'yesterday':
        return (now - timedelta(days=1)).strftime('%Y-%m-%d')
    elif date_str == 'tomorrow':
        return (now + timedelta(days=1)).strftime('%Y-%m-%d')
    elif 'last' in date_str:
        # Handle "last monday", "last week", etc.
        days_map = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }
        for day_name, day_num in days_map.items():
            if day_name in date_str:
                days_back = (now.weekday() - day_num) % 7
                if days_back == 0:
                    days_back = 7  # Last week's same day
                return (now - timedelta(days=days_back)).strftime('%Y-%m-%d')
        if 'week' in date_str:
            return (now - timedelta(days=7)).strftime('%Y-%m-%d')

    # Try to parse as YYYY-MM-DD format
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return date_str
    except ValueError:
        raise ValueError(f"Invalid date format: '{date_str}'. Use YYYY-MM-DD, 'today', 'yesterday', or 'last Monday'")

@mcp.tool("aubrey_meeting_finder")
def meeting_finder(
    calendar_id: str = 'primary',
    start_date: str = '',
    end_date: str = ''
):
    """
    Finds Google Meet events in a calendar within a date range.

    Args:
        calendar_id: The calendar ID to search (default: 'primary')
        start_date: Start date in YYYY-MM-DDTHH:MM:SSZ format (empty for now)
        end_date: End date in YYYY-MM-DDTHH:MM:SSZ format (empty for now)

    Returns:
        List of Google Meet events with meeting links and details
    """
    try:
        if not start_date:
            start_date = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat().replace('+00:00', 'Z')
        if not end_date:
            end_date = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat().replace('+00:00', 'Z')

        print(f"Fetching events from {start_date} to {end_date}")

        events_result = calendar_service.events().list(
            calendarId=calendar_id,
            timeMin=start_date,
            timeMax=end_date,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])

        print(f"Found {len(events)} total events")

        meet_events = []
        for e in events:
            if 'hangoutLink' in e:  # Google Meet link exists
                meet_events.append({
                    "event_id": e.get('id'),
                    "title": e.get('summary'),
                    "date": e['start'].get('dateTime', e['start'].get('date')),
                    "meet_link": e.get('hangoutLink'),
                    "recording": True  # placeholder; replace later with Drive check
                })

        print(f"Returning {len(meet_events)} Meet events")

        if not meet_events:
            return {
                "message": "No Google Meet events found in this date range.",
                "suggestion": "Try expanding your date range or check if meetings have Google Meet links.",
                "events": []
            }

        return {"events": meet_events, "count": len(meet_events)}
    except Exception as e:
        print(f"ERROR in meeting_finder: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

@mcp.tool("aubrey_next_meeting")
def next_meeting(calendar_id: str = 'primary'):
    """
    Shows your next upcoming meeting on Google Calendar.

    Args:
        calendar_id: The calendar ID to search (default: 'primary')

    Returns:
        Dictionary with next meeting title and start time
    """
    try:
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

        print(f"Fetching next meeting after {now}")

        events_result = calendar_service.events().list(
            calendarId=calendar_id,
            timeMin=now,
            maxResults=1,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        if not events:
            return {
                "message": "No upcoming meetings found on your calendar.",
                "suggestion": "Your calendar is clear! No meetings scheduled."
            }

        event = events[0]
        result = {
            "title": event.get('summary', 'No title'),
            "start_time": event['start'].get('dateTime', event['start'].get('date')),
            "event_id": event.get('id')
        }

        print(f"Next meeting: {result['title']} at {result['start_time']}")
        return result

    except Exception as e:
        print(f"ERROR in next_meeting: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

@mcp.tool("aubrey_meeting_rescheduler")
def meeting_rescheduler(
    meeting_title: str = '',
    event_id: str = '',
    new_date: str = '',
    new_time: str = '',
    duration_minutes: int = 60,
    calendar_id: str = 'primary'
):
    """
    Reschedules a meeting to a new date/time or finds the next available slot.

    Args:
        meeting_title: Title of the meeting to reschedule (optional if event_id provided)
        event_id: Event ID of the meeting (optional if meeting_title provided)
        new_date: New date in YYYY-MM-DD format (leave empty to auto-find next available)
        new_time: New time in HH:MM format in YOUR local timezone (leave empty to auto-find next available)
        duration_minutes: Meeting duration in minutes (default: 60)
        calendar_id: Calendar ID (default: 'primary')

    Returns:
        Updated meeting details with new time. If conflicts exist, includes warning and conflicting events.

    Example:
        meeting_title = "Team Standup", new_date = "2026-01-20", new_time = "10:00"
        Returns: Rescheduled meeting info (10:00 AM in your timezone)
    """
    try:
        print(f"Rescheduling meeting: {meeting_title or event_id}")

        # Find the event if only title is provided
        if not event_id and meeting_title:
            now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

            events_result = calendar_service.events().list(
                calendarId=calendar_id,
                timeMin=now,
                q=meeting_title,
                maxResults=5,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])

            if not events:
                return {"error": f"No meeting found with title '{meeting_title}'"}

            # Use the first matching event
            event = events[0]
            event_id = event['id']
            print(f"Found meeting: {event.get('summary')} at {event['start'].get('dateTime')}")
        elif event_id:
            # Get event details
            event = calendar_service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
            print(f"Found event: {event.get('summary')}")
        else:
            return {"error": "Must provide either meeting_title or event_id"}

        # Get calendar timezone
        calendar_info = calendar_service.calendars().get(calendarId=calendar_id).execute()
        calendar_timezone = calendar_info.get('timeZone', 'UTC')
        print(f"Calendar timezone: {calendar_timezone}")

        # If new date/time not specified, find next available slot
        if not new_date or not new_time:
            print("Finding next available time slot...")

            # Get busy times for the next 7 days
            now = datetime.now(timezone.utc)
            time_min = now.isoformat().replace('+00:00', 'Z')
            time_max = (now + timedelta(days=7)).isoformat().replace('+00:00', 'Z')

            body = {
                "timeMin": time_min,
                "timeMax": time_max,
                "items": [{"id": calendar_id}]
            }

            freebusy_result = calendar_service.freebusy().query(body=body).execute()
            busy_times = freebusy_result['calendars'][calendar_id]['busy']

            # Find first available slot (9 AM - 5 PM, weekdays)
            current = now
            found_slot = False

            while not found_slot and current < now + timedelta(days=7):
                # Skip to next business hour
                if current.hour < 9:
                    current = current.replace(hour=9, minute=0, second=0)
                elif current.hour >= 17:
                    current = (current + timedelta(days=1)).replace(hour=9, minute=0, second=0)

                # Skip weekends
                if current.weekday() >= 5:
                    current = (current + timedelta(days=1)).replace(hour=9, minute=0, second=0)
                    continue

                # Check if slot is free
                slot_end = current + timedelta(minutes=duration_minutes)

                is_busy = False
                for busy in busy_times:
                    busy_start = datetime.fromisoformat(busy['start'].replace('Z', '+00:00'))
                    busy_end = datetime.fromisoformat(busy['end'].replace('Z', '+00:00'))

                    if not (slot_end <= busy_start or current >= busy_end):
                        is_busy = True
                        break

                if not is_busy:
                    new_date = current.strftime('%Y-%m-%d')
                    new_time = current.strftime('%H:%M')
                    found_slot = True
                    print(f"Found available slot: {new_date} at {new_time}")
                else:
                    current += timedelta(minutes=30)  # Try next 30-minute slot

            if not found_slot:
                return {"error": "No available time slots found in the next 7 days"}

        # Parse new date/time in calendar's timezone
        new_datetime = datetime.strptime(f"{new_date} {new_time}", "%Y-%m-%d %H:%M")
        new_datetime = new_datetime.replace(tzinfo=ZoneInfo(calendar_timezone))
        print(f"Parsed time in {calendar_timezone}: {new_datetime}")

        # Convert to UTC for API
        new_datetime_utc = new_datetime.astimezone(timezone.utc)
        new_end_utc = new_datetime_utc + timedelta(minutes=duration_minutes)
        print(f"Converted to UTC: {new_datetime_utc}")

        # Check for conflicts at the requested time
        conflict_warning = None
        conflicting_events = []

        # Query FreeBusy to check for conflicts
        body = {
            "timeMin": new_datetime_utc.isoformat().replace('+00:00', 'Z'),
            "timeMax": new_end_utc.isoformat().replace('+00:00', 'Z'),
            "items": [{"id": calendar_id}]
        }

        freebusy_result = calendar_service.freebusy().query(body=body).execute()
        busy_times = freebusy_result['calendars'][calendar_id]['busy']

        # Find conflicting events if any
        if busy_times:
            print(f"⚠️ Conflict detected at {new_date} {new_time} {calendar_timezone}")

            # Get details of conflicting events
            events_at_time = calendar_service.events().list(
                calendarId=calendar_id,
                timeMin=new_datetime_utc.isoformat().replace('+00:00', 'Z'),
                timeMax=new_end_utc.isoformat().replace('+00:00', 'Z'),
                singleEvents=True
            ).execute()

            for conflicting_event in events_at_time.get('items', []):
                # Skip the event being rescheduled
                if conflicting_event.get('id') != event_id:
                    conflicting_events.append({
                        "title": conflicting_event.get('summary', 'No title'),
                        "start": conflicting_event['start'].get('dateTime', conflicting_event['start'].get('date')),
                        "end": conflicting_event['end'].get('dateTime', conflicting_event['end'].get('date'))
                    })

            if conflicting_events:
                conflict_warning = f"⚠️ Double-booked: This time conflicts with {len(conflicting_events)} existing meeting(s)"
                print(conflict_warning)

        # Update event (proceed even if conflicts exist)
        event['start'] = {
            'dateTime': new_datetime_utc.isoformat().replace('+00:00', 'Z'),
            'timeZone': calendar_timezone
        }
        event['end'] = {
            'dateTime': new_end_utc.isoformat().replace('+00:00', 'Z'),
            'timeZone': calendar_timezone
        }

        updated_event = calendar_service.events().update(
            calendarId=calendar_id,
            eventId=event_id,
            body=event
        ).execute()

        print(f"Meeting rescheduled successfully!")

        result = {
            "event_id": updated_event['id'],
            "title": updated_event.get('summary'),
            "new_start_time": updated_event['start'].get('dateTime'),
            "new_end_time": updated_event['end'].get('dateTime'),
            "status": "rescheduled",
            "calendar_link": updated_event.get('htmlLink')
        }

        # Add conflict information if any
        if conflict_warning:
            result["warning"] = conflict_warning
            result["conflicting_events"] = conflicting_events
            result["forced"] = True
            result["message"] = f"Meeting rescheduled successfully, but you're now double-booked with {len(conflicting_events)} other meeting(s)"

        return result

    except Exception as e:
        print(f"ERROR in meeting_rescheduler: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

@mcp.tool("aubrey_drive_meeting_summarizer")
def drive_meeting_summarizer(date: str = '', time: str = '', meeting_title: str = ''):
    """
    🤖 COMPREHENSIVE MEETING ANALYSIS - Your AI meeting assistant!

    Finds recordings in Google Drive, transcribes them, and provides deep insights including:
    - Full transcript with Speech-to-Text
    - Quick summary (first 5 sentences)
    - Key discussion points extracted
    - Decisions made during meeting
    - Questions raised that need follow-up
    - Action items with assignees
    - Sentiment analysis (positive/challenging/neutral)

    Args:
        date: Date of the meeting (e.g., '2026-01-18', 'today', 'yesterday', 'last Monday')
        time: Time of the meeting in HH:MM format (e.g., '14:30') - optional
        meeting_title: Optional meeting title to help identify the recording

    Returns:
        Complete analysis including transcript, insights, action items, and sentiment

    Example:
        date = "yesterday"
        Returns: Full analysis of yesterday's meeting with AI-extracted insights
    """
    try:
        from google.cloud import speech_v1
        import tempfile
        import os

        # Parse flexible date format
        if not date:
            date = 'today'

        try:
            date = parse_flexible_date(date)
        except ValueError as e:
            return {"error": str(e)}

        # Validate time format if provided
        if time:
            try:
                datetime.strptime(time, '%H:%M')
            except ValueError:
                return {"error": f"Invalid time format: '{time}'. Use HH:MM format (e.g., '14:30')"}

        print(f"Searching for meeting recordings from {date} {time}")

        # Search for Meet Recordings folder
        query = "name='Meet Recordings' and mimeType='application/vnd.google-apps.folder'"
        results = drive_service.files().list(q=query, fields='files(id, name)').execute()
        folders = results.get('files', [])

        folder_id = None
        if folders:
            folder_id = folders[0]['id']
            print(f"Found Meet Recordings folder: {folder_id}")
        else:
            # Create the folder if it doesn't exist
            print("Meet Recordings folder not found, creating it...")
            folder_metadata = {
                'name': 'Meet Recordings',
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = drive_service.files().create(body=folder_metadata, fields='id').execute()
            folder_id = folder.get('id')
            print(f"Created Meet Recordings folder: {folder_id}")

        # Build search query for recordings
        # Look for files created on the specified date
        search_query = f"createdTime >= '{date}T00:00:00' and createdTime < '{date}T23:59:59' and (mimeType contains 'video' or mimeType contains 'audio')"

        if folder_id:
            search_query += f" and '{folder_id}' in parents"

        if meeting_title:
            search_query += f" and name contains '{meeting_title}'"

        print(f"Search query: {search_query}")

        # Search for recording files
        results = drive_service.files().list(
            q=search_query,
            orderBy='createdTime desc',
            fields='files(id, name, mimeType, createdTime)',
            pageSize=10
        ).execute()

        files = results.get('files', [])

        if not files:
            return {
                "status": "not_recorded",
                "message": f"❌ This meeting was not recorded on {date}",
                "reason": "No recording file found in Google Drive",
                "suggestion": "The meeting either wasn't recorded, or the recording isn't saved to the 'Meet Recordings' folder in Google Drive. Check your Google Meet recording settings.",
                "searched_date": date,
                "searched_title": meeting_title if meeting_title else "any",
                "searched_folder": "Meet Recordings"
            }

        print(f"Found {len(files)} recordings")
        for f in files:
            print(f"  - {f['name']} ({f['createdTime']})")

        # If multiple recordings found, return list for user to choose
        if len(files) > 1:
            recordings_list = []
            for f in files:
                recordings_list.append({
                    "file_id": f['id'],
                    "file_name": f['name'],
                    "created_time": f['createdTime'],
                    "mime_type": f['mimeType']
                })
            return {
                "message": f"Found {len(files)} recordings for {date}",
                "recordings": recordings_list,
                "suggestion": "Please specify the meeting_title to narrow down results, or I'll transcribe the most recent one."
            }

        # Use the first/most recent recording
        file_id = files[0]['id']
        file_name = files[0]['name']

        print(f"Using recording: {file_name}")

        # Download the file
        request = drive_service.files().get_media(fileId=file_id)

        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_file:
            temp_path = temp_file.name
            downloader = MediaIoBaseDownload(temp_file, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    print(f"Download {int(status.progress() * 100)}% complete")

        print(f"File downloaded to {temp_path}")

        # Extract audio from video using ffmpeg
        audio_path = temp_path.replace('.mp4', '.wav')
        print(f"Extracting audio to {audio_path}")

        import subprocess
        try:
            # Extract audio as WAV format
            subprocess.run([
                'ffmpeg', '-i', temp_path,
                '-vn',  # No video
                '-acodec', 'pcm_s16le',  # Linear PCM 16-bit
                '-ar', '16000',  # 16kHz sample rate
                '-ac', '1',  # Mono
                audio_path
            ], check=True, capture_output=True)

            print(f"Audio extracted successfully")

            # Read audio file
            with open(audio_path, 'rb') as audio_file:
                audio_content = audio_file.read()

            # Transcribe using Google Speech-to-Text
            print("Transcribing audio with Speech-to-Text API...")
            client = speech_v1.SpeechClient(credentials=creds)

            # Check file size - if > 10MB, transcribe first 10MB as partial transcript
            file_size_mb = len(audio_content) / (1024 * 1024)
            print(f"Audio file size: {file_size_mb:.2f} MB")

            partial_transcript = False
            if file_size_mb > 10:
                print(f"File exceeds 10MB limit. Transcribing first 10MB as partial transcript...")
                # Truncate to first 10MB
                audio_content = audio_content[:10 * 1024 * 1024]
                partial_transcript = True

            # Use synchronous recognize for audio
            audio = speech_v1.RecognitionAudio(content=audio_content)
            config = speech_v1.RecognitionConfig(
                encoding=speech_v1.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                language_code="en-US",
                enable_automatic_punctuation=True,
            )

            print("Starting transcription...")
            response = client.recognize(config=config, audio=audio)

            # Check if we got any results
            if not response.results:
                os.unlink(temp_path)
                os.unlink(audio_path)
                result = {
                    "file_id": file_id,
                    "file_name": file_name,
                    "transcript": "",
                    "summary": "No speech detected in recording.",
                    "transcript_length": 0
                }
                if partial_transcript:
                    result["note"] = f"Only first 10MB of {file_size_mb:.2f}MB file was processed (partial transcript)"
                return result

            # Combine all transcripts
            transcript = " ".join([result.alternatives[0].transcript for result in response.results])

            # Clean up temp files
            os.unlink(temp_path)
            os.unlink(audio_path)

            print(f"Transcribed {len(transcript)} characters")

            # COMPREHENSIVE ANALYSIS
            import re
            sentences = transcript.split(".")

            # 1. Simple summary: first 5 sentences
            summary_sentences = [s.strip() for s in sentences[:5] if s.strip()]
            summary = ". ".join(summary_sentences)
            if summary:
                summary += "."

            # 2. Extract key discussion points
            key_points = []
            important_keywords = ['important', 'critical', 'key', 'priority', 'must', 'need to', 'decided', 'agreed']
            for sentence in sentences:
                sentence = sentence.strip()
                if any(keyword in sentence.lower() for keyword in important_keywords) and len(sentence) > 20:
                    key_points.append(sentence)

            # 3. Extract decisions made
            decisions = []
            decision_patterns = [
                r"(?:we|I|they)\s+(?:decided|agreed|concluded|determined)\s+(?:to|that)\s+(.+?)(?:\.|,|$)",
                r"(?:decision|conclusion):\s*(.+?)(?:\.|$)",
                r"(?:let's|we'll|we will|we're going to)\s+(.+?)(?:\.|,|$)"
            ]
            for sentence in sentences:
                for pattern in decision_patterns:
                    matches = re.finditer(pattern, sentence, re.IGNORECASE)
                    for match in matches:
                        decision_text = match.group(1).strip() if match.groups() else sentence.strip()
                        if len(decision_text) > 10 and len(decision_text) < 150:
                            decisions.append(decision_text)

            # 4. Extract questions raised
            questions = []
            for sentence in sentences:
                if '?' in sentence:
                    question = sentence.split('?')[0].strip() + '?'
                    if len(question) > 10:
                        questions.append(question)

            # 5. Extract action items
            action_items = []
            action_patterns = [
                r"(\w+)\s+(?:will|should|needs to|has to|must)\s+(.+?)(?:\.|,|$)",
                r"(?:TODO|Action item|Action|Task):\s*(.+?)(?:\.|$)",
                r"(\w+)\s+(?:to|going to)\s+(.+?)(?:\.|,|$)"
            ]
            for sentence in sentences:
                sentence = sentence.strip()
                for pattern in action_patterns:
                    matches = re.finditer(pattern, sentence, re.IGNORECASE)
                    for match in matches:
                        if len(match.groups()) == 2:
                            person = match.group(1).strip()
                            task = match.group(2).strip()
                        else:
                            person = "Unassigned"
                            task = match.group(1).strip()
                        if len(task) > 10 and len(task) < 200:
                            action_items.append({
                                "assignee": person.capitalize(),
                                "task": task
                            })

            # Remove duplicate action items
            unique_actions = []
            seen_tasks = set()
            for item in action_items:
                task_key = item['task'].lower()[:50]
                if task_key not in seen_tasks:
                    seen_tasks.add(task_key)
                    unique_actions.append(item)

            # 6. Sentiment analysis
            positive_words = ['great', 'good', 'excellent', 'awesome', 'perfect', 'agree', 'yes', 'love', 'like']
            negative_words = ['bad', 'wrong', 'issue', 'problem', 'concern', 'worried', 'no', 'disagree', 'difficult']
            positive_count = sum(1 for word in positive_words if word in transcript.lower())
            negative_count = sum(1 for word in negative_words if word in transcript.lower())

            if positive_count > negative_count * 1.5:
                sentiment = "Positive - Collaborative and productive discussion"
            elif negative_count > positive_count * 1.5:
                sentiment = "Challenging - Several concerns or issues raised"
            else:
                sentiment = "Neutral - Balanced discussion"

            print(f"Generated comprehensive analysis")

            result = {
                "file_id": file_id,
                "file_name": file_name,
                "date": date,
                "time": time,
                "transcript": transcript,
                "transcript_length": len(transcript),
                "summary": summary,
                "insights": {
                    "key_discussion_points": key_points[:5],
                    "decisions_made": list(set(decisions))[:5],
                    "questions_raised": questions[:5],
                    "action_items": unique_actions[:10],
                    "sentiment": sentiment,
                    "positive_indicators": positive_count,
                    "concerns_raised": negative_count
                }
            }

            if partial_transcript:
                result["note"] = f"⚠️ Partial transcript: Only first 10MB of {file_size_mb:.2f}MB file was processed. Full meeting may have additional content."

            return result

        except subprocess.CalledProcessError as e:
            # Clean up temp file
            os.unlink(temp_path)
            if os.path.exists(audio_path):
                os.unlink(audio_path)

            return {
                "file_id": file_id,
                "file_name": file_name,
                "error": "ffmpeg not installed. Please run: brew install ffmpeg",
                "note": "Audio extraction from video requires ffmpeg"
            }

    except Exception as e:
        print(f"ERROR in drive_meeting_summarizer: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

@mcp.tool("aubrey_meeting_prep_assistant")
def meeting_prep_assistant(
    meeting_title: str = '',
    attendee_email: str = '',
    lookback_days: int = 90,
    include_transcripts: bool = True,
    max_results: int = 5
):
    """
    Prepares you for an upcoming meeting by finding context from previous similar meetings.

    Args:
        meeting_title: Title of the upcoming meeting (e.g., "Weekly Sync")
        attendee_email: Email of key attendee to find previous meetings with
        lookback_days: How many days back to search (default: 90)
        include_transcripts: Whether to fetch full analysis from recordings (default: True, slower but more detailed)
        max_results: Maximum number of previous meetings to return (default: 5)

    Returns:
        Context from previous meetings including summaries, action items, and key decisions

    Example:
        meeting_title = "Weekly Sync", lookback_days = 30
        Returns: Last 5 Weekly Sync meetings from past 30 days with full analysis
    """
    try:
        # Validate inputs
        if not meeting_title and not attendee_email:
            return {
                "error": "Please provide either meeting_title or attendee_email",
                "suggestion": "Example: meeting_title='Team Standup' or attendee_email='boss@company.com'"
            }

        # Search for previous meetings with same title or attendee
        start_date = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat().replace('+00:00', 'Z')
        end_date = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

        events_result = calendar_service.events().list(
            calendarId='primary',
            timeMin=start_date,
            timeMax=end_date,
            q=meeting_title if meeting_title else attendee_email,
            singleEvents=True,
            orderBy='startTime',
            maxResults=max_results * 2  # Get extra in case some don't have recordings
        ).execute()

        events = events_result.get('items', [])

        if not events:
            return {
                "message": f"No previous meetings found matching '{meeting_title or attendee_email}' in last {lookback_days} days",
                "suggestion": "Try increasing lookback_days or checking the meeting title spelling"
            }

        previous_meetings = []
        meetings_with_recordings = 0

        for event in events[:max_results * 2]:  # Process more to find recordings
            meeting_date = event['start'].get('dateTime', event['start'].get('date'))
            meeting_info = {
                "title": event.get('summary', 'No title'),
                "date": meeting_date,
                "attendees": [a.get('email', 'Unknown') for a in event.get('attendees', [])]
            }

            # Try to get full analysis if requested
            if include_transcripts:
                try:
                    event_date = meeting_date.split('T')[0]
                    summary_result = drive_meeting_summarizer(date=event_date, meeting_title=event.get('summary', ''))

                    if 'transcript' in summary_result and 'insights' in summary_result:
                        meeting_info['had_recording'] = True
                        meeting_info['summary'] = summary_result.get('summary', '')
                        meeting_info['insights'] = {
                            "key_points": summary_result['insights'].get('key_discussion_points', [])[:3],
                            "decisions": summary_result['insights'].get('decisions_made', [])[:3],
                            "action_items": summary_result['insights'].get('action_items', [])[:5],
                            "sentiment": summary_result['insights'].get('sentiment', 'Unknown')
                        }
                        meetings_with_recordings += 1
                    else:
                        meeting_info['had_recording'] = False
                        meeting_info['note'] = "No recording available"
                except:
                    meeting_info['had_recording'] = False
                    meeting_info['note'] = "Could not fetch recording"
            else:
                meeting_info['had_recording'] = False
                meeting_info['note'] = "Transcripts not requested (set include_transcripts=True)"

            previous_meetings.append(meeting_info)

            # Stop if we have enough meetings
            if len(previous_meetings) >= max_results:
                break

        # Aggregate action items across all meetings
        all_action_items = []
        for meeting in previous_meetings:
            if meeting.get('had_recording') and 'insights' in meeting:
                all_action_items.extend(meeting['insights'].get('action_items', []))

        return {
            "upcoming_meeting": meeting_title or f"Meeting with {attendee_email}",
            "search_period": f"Last {lookback_days} days",
            "previous_meetings_count": len(previous_meetings),
            "meetings_with_recordings": meetings_with_recordings,
            "previous_meetings": previous_meetings,
            "aggregated_action_items": all_action_items[:10],  # Top 10 action items from all meetings
            "message": f"Found {len(previous_meetings)} previous meetings ({meetings_with_recordings} with recordings)"
        }

    except Exception as e:
        print(f"ERROR in meeting_prep_assistant: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

@mcp.tool("aubrey_calendar_conflicts_detector")
def calendar_conflicts_detector(days_ahead: int = 7, calendar_id: str = 'primary'):
    """
    Detects scheduling conflicts and back-to-back meetings in your calendar.

    Args:
        days_ahead: Number of days to check ahead (default: 7)
        calendar_id: Calendar ID to check (default: 'primary')

    Returns:
        List of conflicts, back-to-back meetings, and scheduling suggestions

    Example:
        days_ahead = 7
        Returns: All conflicts and packed schedule in next week
    """
    try:
        # Get events for the next N days
        start_date = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        end_date = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).isoformat().replace('+00:00', 'Z')

        events_result = calendar_service.events().list(
            calendarId=calendar_id,
            timeMin=start_date,
            timeMax=end_date,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        if not events:
            return {
                "message": "No upcoming events found - your calendar is clear!",
                "conflicts": [],
                "back_to_back": []
            }

        conflicts = []
        back_to_back = []

        # Check for overlapping events
        for i in range(len(events)):
            event1 = events[i]

            # Skip all-day events
            if 'dateTime' not in event1['start']:
                continue

            event1_start = datetime.fromisoformat(event1['start']['dateTime'].replace('Z', '+00:00'))
            event1_end = datetime.fromisoformat(event1['end']['dateTime'].replace('Z', '+00:00'))

            for j in range(i + 1, len(events)):
                event2 = events[j]

                # Skip all-day events
                if 'dateTime' not in event2['start']:
                    continue

                event2_start = datetime.fromisoformat(event2['start']['dateTime'].replace('Z', '+00:00'))
                event2_end = datetime.fromisoformat(event2['end']['dateTime'].replace('Z', '+00:00'))

                # Check for overlap
                if event1_start < event2_end and event2_start < event1_end:
                    conflicts.append({
                        "event1": {
                            "title": event1.get('summary', 'No title'),
                            "start": event1['start']['dateTime'],
                            "end": event1['end']['dateTime']
                        },
                        "event2": {
                            "title": event2.get('summary', 'No title'),
                            "start": event2['start']['dateTime'],
                            "end": event2['end']['dateTime']
                        },
                        "type": "overlap"
                    })

                # Check for back-to-back (no buffer)
                if event1_end == event2_start:
                    back_to_back.append({
                        "event1": event1.get('summary', 'No title'),
                        "event2": event2.get('summary', 'No title'),
                        "time": event1_end.strftime('%Y-%m-%d %H:%M'),
                        "suggestion": "Consider adding 5-10 min buffer for breaks"
                    })

        # Calculate total meeting hours
        total_duration = timedelta(0)
        for event in events:
            if 'dateTime' in event['start']:
                start = datetime.fromisoformat(event['start']['dateTime'].replace('Z', '+00:00'))
                end = datetime.fromisoformat(event['end']['dateTime'].replace('Z', '+00:00'))
                total_duration += (end - start)

        total_hours = total_duration.total_seconds() / 3600

        return {
            "period": f"Next {days_ahead} days",
            "total_meetings": len(events),
            "total_hours": round(total_hours, 1),
            "conflicts": conflicts,
            "conflicts_count": len(conflicts),
            "back_to_back_meetings": back_to_back,
            "back_to_back_count": len(back_to_back),
            "message": f"Analyzed {len(events)} meetings. Found {len(conflicts)} conflicts and {len(back_to_back)} back-to-back meetings.",
            "health_score": "🔴 Overbooked" if total_hours > 30 else "🟡 Busy" if total_hours > 15 else "🟢 Healthy"
        }

    except Exception as e:
        print(f"ERROR in calendar_conflicts_detector: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

if __name__ == "__main__":
    mcp.run(transport="streamable-http")

