from typing import List
from pydantic import BaseModel, Field
from north_mcp_python_sdk import NorthMCPServer

_default_port = 3001

# update all the mcp tool functions to be <aubrey_marcelotanner>_<tool>
# since mcp tool names MUST be unique

mcp = NorthMCPServer(
    "Simple Calculator", host="0.0.0.0", port=_default_port
)

import pickle
from datetime import datetime, timezone
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# ---------------------------
# Google Calendar Authentication
# ---------------------------

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

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

@mcp.tool("Meeting Finder")
def meeting_finder(
    calendar_id: str = 'primary',  # <-- replace if you want another calendar
    start_date: str = None,        # <-- YYYY-MM-DDTHH:MM:SSZ format or None for now
    end_date: str = None           # <-- YYYY-MM-DDTHH:MM:SSZ format or None for now
):
    """
    Finds Google Meet events in a calendar within a date range.
    Example North input: "North, show me all Google Meet meetings I attended last week that have recordings."
    """
    if not start_date:
        start_date = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    if not end_date:
        end_date = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    events_result = calendar_service.events().list(
        calendarId=calendar_id,
        timeMin=start_date,
        timeMax=end_date,
        singleEvents=True,
        orderBy='startTime',
        conferenceDataVersion=1
    ).execute()
    events = events_result.get('items', [])

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
    return meet_events

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
