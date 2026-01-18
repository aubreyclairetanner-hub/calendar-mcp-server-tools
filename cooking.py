from north_mcp_python_sdk import NorthMCPServer
import pickle
import io
from datetime import datetime, timezone, timedelta
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
    'https://www.googleapis.com/auth/drive.readonly',
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

@mcp.tool("Meeting Finder")
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
        return meet_events
    except Exception as e:
        print(f"ERROR in meeting_finder: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

@mcp.tool("Next Meeting")
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
            return {"message": "No upcoming meetings found"}

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

@mcp.tool("Meeting Rescheduler")
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
        new_time: New time in HH:MM format (leave empty to auto-find next available)
        duration_minutes: Meeting duration in minutes (default: 60)
        calendar_id: Calendar ID (default: 'primary')

    Returns:
        Updated meeting details with new time

    Example:
        meeting_title = "Team Standup", new_date = "2026-01-20", new_time = "10:00"
        Returns: Rescheduled meeting info
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

        # Parse new date/time
        new_datetime = datetime.strptime(f"{new_date} {new_time}", "%Y-%m-%d %H:%M")
        new_datetime = new_datetime.replace(tzinfo=timezone.utc)
        new_end = new_datetime + timedelta(minutes=duration_minutes)

        # Update event
        event['start'] = {
            'dateTime': new_datetime.isoformat().replace('+00:00', 'Z'),
            'timeZone': 'UTC'
        }
        event['end'] = {
            'dateTime': new_end.isoformat().replace('+00:00', 'Z'),
            'timeZone': 'UTC'
        }

        updated_event = calendar_service.events().update(
            calendarId=calendar_id,
            eventId=event_id,
            body=event
        ).execute()

        print(f"Meeting rescheduled successfully!")

        return {
            "event_id": updated_event['id'],
            "title": updated_event.get('summary'),
            "new_start_time": updated_event['start'].get('dateTime'),
            "new_end_time": updated_event['end'].get('dateTime'),
            "status": "rescheduled",
            "calendar_link": updated_event.get('htmlLink')
        }

    except Exception as e:
        print(f"ERROR in meeting_rescheduler: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

@mcp.tool("Drive Meeting Summarizer")
def drive_meeting_summarizer(date: str = '', time: str = '', meeting_title: str = ''):
    """
    Automatically finds and summarizes meeting recordings from Google Drive.
    Searches the 'Meet Recordings' folder for recordings matching the date/time.

    Args:
        date: Date of the meeting in YYYY-MM-DD format (e.g., '2026-01-18')
        time: Time of the meeting in HH:MM format (e.g., '14:30')
        meeting_title: Optional meeting title to help identify the recording

    Returns:
        Transcript and summary of the meeting

    Example:
        date = "2026-01-18", time = "14:30"
        Returns: Transcript and summary of the meeting from that time
    """
    try:
        from google.cloud import speech_v1
        import tempfile
        import os

        # If no date provided, use today
        if not date:
            date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

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
            print("Meet Recordings folder not found, searching all recordings...")

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
            return {"error": f"No meeting recordings found for {date} {time}"}

        print(f"Found {len(files)} recordings")
        for f in files:
            print(f"  - {f['name']} ({f['createdTime']})")

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

            # Check file size - if > 10MB, need to upload to GCS first
            file_size_mb = len(audio_content) / (1024 * 1024)
            print(f"Audio file size: {file_size_mb:.2f} MB")

            if file_size_mb > 10:
                # For large files, would need to upload to Google Cloud Storage
                # For now, return an error
                os.unlink(temp_path)
                os.unlink(audio_path)
                return {
                    "file_id": file_id,
                    "file_name": file_name,
                    "error": f"Audio file too large ({file_size_mb:.2f}MB). Maximum is 10MB for direct transcription.",
                    "note": "For longer meetings, consider using Google Cloud Storage integration."
                }

            # Use synchronous recognize for short audio (< 1 minute)
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
                return {
                    "file_id": file_id,
                    "file_name": file_name,
                    "transcript": "",
                    "summary": "No speech detected in recording.",
                    "transcript_length": 0
                }

            # Combine all transcripts
            transcript = " ".join([result.alternatives[0].transcript for result in response.results])

            # Clean up temp files
            os.unlink(temp_path)
            os.unlink(audio_path)

            print(f"Transcribed {len(transcript)} characters")

            # Simple summarization: first 5 sentences
            sentences = transcript.split(".")
            summary_sentences = [s.strip() for s in sentences[:5] if s.strip()]
            summary = ". ".join(summary_sentences)

            if summary:
                summary += "."

            print(f"Generated summary: {summary[:100]}...")

            return {
                "file_id": file_id,
                "file_name": file_name,
                "date": date,
                "time": time,
                "transcript": transcript,
                "summary": summary,
                "transcript_length": len(transcript)
            }

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

if __name__ == "__main__":
    mcp.run(transport="streamable-http")

