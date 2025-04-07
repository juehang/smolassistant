import datetime
from typing import Callable, List, Optional, Tuple, Dict, Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from smolagents import tool

from .auth import get_credentials, CALENDAR_SCOPES


def format_calendar_results(services_with_events: List[Tuple]):
    """
    Format calendar events into a readable, token-efficient string.

    Args:
        services_with_events: List of tuples (service, events, account_index)

    Returns:
        Formatted string with events grouped by day
    """
    total_events = sum(len(events) for _, events, _ in services_with_events)

    if total_events == 0:
        return "No upcoming events found in any calendar."

    # Group all events by day
    events_by_day = {}

    for _, events, account_idx in services_with_events:
        for event in events:
            # Get start date/time
            start = event["start"].get("dateTime", event["start"].get("date"))

            # Convert to datetime object
            if "T" in start:  # Has time component
                start_dt = datetime.datetime.fromisoformat(
                    start.replace("Z", "+00:00")
                )
                is_all_day = False
            else:  # All-day event
                start_dt = datetime.datetime.fromisoformat(start)
                is_all_day = True

            # Get just the date part as string for grouping
            day_str = start_dt.strftime("%Y-%m-%d")

            if day_str not in events_by_day:
                events_by_day[day_str] = []

            # Add account info and processed datetime
            event["account_idx"] = account_idx
            event["start_dt"] = start_dt
            event["is_all_day"] = is_all_day
            events_by_day[day_str].append(event)

    # Sort days
    sorted_days = sorted(events_by_day.keys())

    # Build the result
    result = f"Found {total_events} upcoming events:\n\n"

    # Today and tomorrow for relative references
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )

    for day in sorted_days:
        # Format the day header
        if day == today:
            day_header = "Today"
        elif day == tomorrow:
            day_header = "Tomorrow"
        else:
            # Convert YYYY-MM-DD to a more readable format
            dt = datetime.datetime.fromisoformat(day)
            day_header = dt.strftime("%A, %B %d")  # e.g., "Monday, April 8"

        result += f"{day_header}:\n"

        # Add events for this day
        for i, event in enumerate(events_by_day[day], 1):
            # Format the event time
            if event["is_all_day"]:
                time_str = "All day"
            else:
                # Format the time
                start_time = event["start_dt"].strftime("%I:%M %p").lstrip("0")

                # Get end time if available
                if "end" in event:
                    end = event["end"].get("dateTime")
                    if end:
                        end_dt = datetime.datetime.fromisoformat(
                            end.replace("Z", "+00:00")
                        )
                        end_time = end_dt.strftime("%I:%M %p").lstrip("0")
                        time_str = f"{start_time}-{end_time}"
                    else:
                        time_str = start_time
                else:
                    time_str = start_time

            # Get summary (title)
            summary = event.get("summary", "Untitled Event")

            # Add location if available (but keep it brief)
            location = (
                event.get("location", "").split(",")[0]
                if event.get("location")
                else ""
            )
            location_str = f" - {location}" if location else ""

            # Start building the event line
            event_line = f"{i}. {summary} ({time_str}){location_str}"

            # Add calendar name for context (especially if multiple calendars)
            calendar = event.get("calendarTitle", "")
            if calendar:
                event_line += f" [{calendar}]"

            result += f"{event_line}\n"

            # Add meeting link if present (but only the most important one)
            conference_data = event.get("conferenceData", {})
            if conference_data:
                entry_points = conference_data.get("entryPoints", [])
                for entry in entry_points:
                    if entry.get("entryPointType") == "video":
                        result += f"   Link: {entry.get('uri', '')}\n"
                        break

            # Add a very brief description snippet if available
            description = event.get("description", "")
            if description:
                # Extract just the first ~50 chars of description
                desc_snippet = description.split("\n")[0][:50]
                if len(desc_snippet) == 50:
                    desc_snippet += "..."
                if desc_snippet.strip():  # Only add if not empty
                    result += f"   Note: {desc_snippet}\n"

            result += "\n"

    return result


def get_upcoming_events_tool(summarize_func: Optional[Callable] = None):
    """
    Create a tool for getting upcoming calendar events.

    Args:
        summarize_func: Optional function to summarize text
    """

    @tool
    def get_upcoming_events(
        days: int = 7, max_results: int = 10, summarize: bool = True
    ) -> str:
        """
        Get upcoming calendar events for the next specified number of days.

        Args:
            days: Number of days to look ahead (default: 7)
            max_results: Maximum number of results to return per calendar (default: 10)
            summarize: Whether to summarize the results (default: True)

        Returns:
            Formatted string with upcoming events
        """
        try:
            # Get credentials for Calendar API
            all_creds = get_credentials(CALENDAR_SCOPES)

            services_with_events = []

            # Get current time in UTC
            now = (
                datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
            )

            # Calculate end time
            end_time = (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(days=days)
            ).isoformat() + "Z"

            # Process each account
            for idx, creds in enumerate(all_creds):
                try:
                    # Build the Calendar API service
                    service = build("calendar", "v3", credentials=creds)

                    # Get list of calendars
                    calendar_list = service.calendarList().list().execute()
                    calendars = calendar_list.get("items", [])

                    # For each calendar, get events
                    all_events = []
                    for calendar in calendars:
                        cal_id = calendar["id"]
                        # Skip calendars that might not be relevant
                        if calendar.get("selected", True) is False:
                            continue

                        events_result = (
                            service.events()
                            .list(
                                calendarId=cal_id,
                                timeMin=now,
                                timeMax=end_time,
                                maxResults=max_results,
                                singleEvents=True,
                                orderBy="startTime",
                            )
                            .execute()
                        )

                        events = events_result.get("items", [])
                        for event in events:
                            # Add calendar info to each event
                            event["calendarTitle"] = calendar.get(
                                "summary", "Unknown Calendar"
                            )
                            all_events.append(event)

                    # Sort all events by start time
                    all_events.sort(
                        key=lambda x: x["start"].get(
                            "dateTime", x["start"].get("date", "")
                        )
                    )

                    # Take top max_results events
                    all_events = all_events[:max_results]

                    services_with_events.append((service, all_events, idx))
                except Exception as e:
                    print(f"Error processing account {idx}: {str(e)}")

            # Format the results
            result = format_calendar_results(services_with_events)

            # Summarize if requested
            if summarize and summarize_func and len(result) > 500:
                try:
                    result = summarize_func(result)
                except Exception as e:
                    result = (
                        f"Note: Summarization failed ({str(e)})\n\n{result}"
                    )

            return result
        except Exception as e:
            if "authentication not set up" in str(e):
                return (
                    "Google Calendar API authentication not set up. "
                    "Please use the initialize_calendar_auth function first."
                )
            return f"Error fetching calendar events: {str(e)}"

    return get_upcoming_events


def search_calendar_events_tool(summarize_func: Optional[Callable] = None):
    """
    Create a tool for searching calendar events.

    Args:
        summarize_func: Optional function to summarize text
    """

    @tool
    def search_calendar_events(
        query: str,
        days: int = 30,
        max_results: int = 10,
        summarize: bool = True,
    ) -> str:
        """
        Search calendar events for events containing the query text.

        Args:
            query: Search text to find in event titles/descriptions
            days: Number of days to look ahead (default: 30)
            max_results: Maximum number of results to return per calendar (default: 10)
            summarize: Whether to summarize the results (default: True)

        Returns:
            Formatted string with matching events
        """
        try:
            # Get credentials for Calendar API
            all_creds = get_credentials(CALENDAR_SCOPES)

            services_with_events = []

            # Get current time in UTC
            now = (
                datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
            )

            # Calculate end time
            end_time = (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(days=days)
            ).isoformat() + "Z"

            # Process each account
            for idx, creds in enumerate(all_creds):
                try:
                    # Build the Calendar API service
                    service = build("calendar", "v3", credentials=creds)

                    # Get list of calendars
                    calendar_list = service.calendarList().list().execute()
                    calendars = calendar_list.get("items", [])

                    # For each calendar, get events
                    all_events = []
                    for calendar in calendars:
                        cal_id = calendar["id"]
                        # Skip calendars that might not be relevant
                        if calendar.get("selected", True) is False:
                            continue

                        # Get all events, then filter by query
                        events_result = (
                            service.events()
                            .list(
                                calendarId=cal_id,
                                timeMin=now,
                                timeMax=end_time,
                                maxResults=max_results
                                * 2,  # Get more to allow for filtering
                                singleEvents=True,
                                orderBy="startTime",
                            )
                            .execute()
                        )

                        events = events_result.get("items", [])

                        # Filter events by query text
                        filtered_events = []
                        for event in events:
                            summary = event.get("summary", "").lower()
                            description = event.get("description", "").lower()
                            location = event.get("location", "").lower()

                            if (
                                query.lower() in summary
                                or query.lower() in description
                                or query.lower() in location
                            ):
                                # Add calendar info to event
                                event["calendarTitle"] = calendar.get(
                                    "summary", "Unknown Calendar"
                                )
                                filtered_events.append(event)

                        all_events.extend(filtered_events)

                    # Sort all events by start time
                    all_events.sort(
                        key=lambda x: x["start"].get(
                            "dateTime", x["start"].get("date", "")
                        )
                    )

                    # Take top max_results events
                    all_events = all_events[:max_results]

                    services_with_events.append((service, all_events, idx))
                except Exception as e:
                    print(f"Error processing account {idx}: {str(e)}")

            # Format the results
            result = format_calendar_results(services_with_events)

            # Summarize if requested
            if summarize and summarize_func and len(result) > 500:
                try:
                    result = summarize_func(result)
                except Exception as e:
                    result = (
                        f"Note: Summarization failed ({str(e)})\n\n{result}"
                    )

            return result
        except Exception as e:
            if "authentication not set up" in str(e):
                return (
                    "Google Calendar API authentication not set up. "
                    "Please use the initialize_calendar_auth function first."
                )
            return f"Error searching calendar events: {str(e)}"

    return search_calendar_events
