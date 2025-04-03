from datetime import datetime
import uuid

import schedule
from smolagents import tool


def set_reminder_tool(callback_fn):
    """
    Create a tool for setting one-time reminders.
    All reminders are routed to you, the agent, to handle.
    Depending on the reminder, you may need to notify the user
    or take some other action.
    
    Args:
        callback_fn: Function to call when a reminder is triggered
    """
    @tool
    def set_reminder(message: str, due_time: str) -> str:
        """
        Set a one-time reminder for a specific future time.
        
        Args:
            message: The reminder message. This message should include the 
                target of the reminder (ie. user or agent).
            due_time: When the reminder should trigger, in ISO format
                (YYYY-MM-DD HH:MM:SS)
        """
        try:
            # Try to parse as ISO format
            parsed_time = datetime.fromisoformat(due_time)
        except ValueError:
            return (
                "Invalid time format. Please use ISO format "
                "(YYYY-MM-DD HH:MM:SS). Timezones are supported using the "
                "'+' or '-' offset format."
            )
        
        # Generate a unique ID for the reminder
        reminder_id = f"reminder_{uuid.uuid4()}"
        
        # Define the job function
        def reminder_job(message=None, reminder_id=None):
            formatted_message = f"🔔 REMINDER: {message}"
            callback_fn(formatted_message)
            # Return CancelJob to remove the job after it runs
            return schedule.CancelJob
        
        # Calculate seconds until the reminder is due
        now = datetime.now()
        if parsed_time > now:
            # Schedule for future time
            seconds_until_due = (parsed_time - now).total_seconds()
            
            # Schedule the job to run once after the calculated delay
            # Tag it with 'reminder' and reminder_id for identification
            job = schedule.every(seconds_until_due).seconds.do(
                reminder_job,
                message=message,
                reminder_id=reminder_id
            )
            job.tag('reminder', reminder_id)
        else:
            # Due time has already passed, trigger immediately
            formatted_message = f"🔔 REMINDER: {message}"
            callback_fn(formatted_message)
        
        return f"One-time reminder set for {due_time}. (Reminder ID: {reminder_id})"
    
    return set_reminder


def set_recurring_reminder_tool(callback_fn):
    """
    Create a tool for setting recurring reminders.
    All reminders are routed to you, the agent, to handle.
    Depending on the reminder, you may need to notify the user
    or take some other action.
    
    Args:
        callback_fn: Function to call when a reminder is triggered
    """
    @tool
    def set_recurring_reminder(message: str, interval: str, time_spec: str = "") -> str:
        """
        Set a recurring reminder that repeats based on the specified interval and time.
        
        Args:
            message: The reminder message. This message should include the 
                target of the reminder (ie. user or agent).
            interval: When the reminder should trigger. Valid values are:
                - "second", "minute", "hour", "day" - Every second/minute/hour/day
                - "monday", "tuesday", "wednesday", "thursday", "friday", 
                  "saturday", "sunday" - Weekly on specified day
                - "X seconds", "X minutes", "X hours", "X days" where X is a 
                  number - Every X seconds/minutes/hours/days
            time_spec: Time specification for the interval (optional, depends on interval):
                - For "day" interval: Use "HH:MM" format (e.g., "10:30")
                - For weekday intervals: Use "HH:MM" format (e.g., "14:15")
                - For "hour" interval: Use ":MM" format (e.g., ":45")
                - For "minute" interval: Use ":SS" format (e.g., ":30")
                - For other intervals: Leave empty
        """
        # Generate a unique ID for the reminder
        reminder_id = f"recurring_{uuid.uuid4()}"
        
        # Define the job function
        def reminder_job(message=None, reminder_id=None, interval=None, time_spec=None):
            if time_spec:
                formatted_message = f"🔄 RECURRING REMINDER ({interval} at {time_spec}): {message}"
            else:
                formatted_message = f"🔄 RECURRING REMINDER ({interval}): {message}"
            callback_fn(formatted_message)
        
        # Create mapped dictionaries for the schedule methods
        interval_methods = {
            # Basic intervals
            "second": schedule.every().second,
            "minute": schedule.every().minute,
            "hour": schedule.every().hour,
            "day": schedule.every().day,
            
            # Days of week
            "monday": schedule.every().monday,
            "tuesday": schedule.every().tuesday,
            "wednesday": schedule.every().wednesday,
            "thursday": schedule.every().thursday,
            "friday": schedule.every().friday,
            "saturday": schedule.every().saturday,
            "sunday": schedule.every().sunday,
        }
        
        job = None
        display_interval = interval.lower()
        
        # Check for numbered intervals like "2 hours"
        interval_parts = interval.lower().split()
        if len(interval_parts) == 2 and interval_parts[0].isdigit():
            count = int(interval_parts[0])
            unit = interval_parts[1]
            
            # Handle plural forms by removing trailing 's'
            if unit.endswith('s'):
                unit = unit[:-1]
            
            # Map the unit to the correct schedule method
            if unit == "second":
                job = schedule.every(count).seconds.do(
                    reminder_job,
                    message=message,
                    reminder_id=reminder_id,
                    interval=display_interval,
                    time_spec=time_spec
                )
            elif unit == "minute":
                job = schedule.every(count).minutes.do(
                    reminder_job,
                    message=message,
                    reminder_id=reminder_id,
                    interval=display_interval,
                    time_spec=time_spec
                )
            elif unit == "hour":
                job = schedule.every(count).hours.do(
                    reminder_job,
                    message=message,
                    reminder_id=reminder_id,
                    interval=display_interval,
                    time_spec=time_spec
                )
            elif unit == "day":
                job = schedule.every(count).days.do(
                    reminder_job,
                    message=message,
                    reminder_id=reminder_id,
                    interval=display_interval,
                    time_spec=time_spec
                )
        else:
            # Handle standard intervals
            method = interval_methods.get(interval.lower())
            
            if method:
                if time_spec:
                    # With time specification
                    job = method.at(time_spec).do(
                        reminder_job,
                        message=message,
                        reminder_id=reminder_id,
                        interval=display_interval,
                        time_spec=time_spec
                    )
                else:
                    # Without time specification
                    job = method.do(
                        reminder_job,
                        message=message,
                        reminder_id=reminder_id,
                        interval=display_interval,
                        time_spec=time_spec
                    )
        
        if job:
            # Tag the job for identification and management
            job.tag('recurring', reminder_id)
            
            if time_spec:
                return f"Recurring reminder set ({display_interval} at {time_spec}). (Reminder ID: {reminder_id})"
            else:
                return f"Recurring reminder set ({display_interval}). (Reminder ID: {reminder_id})"
        else:
            return (
                "Invalid interval or time specification. Please use one of the following formats:\n"
                "- Basic intervals: 'second', 'minute', 'hour', 'day'\n"
                "- Weekday intervals: 'monday', 'tuesday', 'wednesday', etc.\n"
                "- Numbered intervals: 'X seconds', 'X minutes', 'X hours', 'X days'\n\n"
                "Time specification depends on the interval:\n"
                "- For 'day' interval: Use 'HH:MM' format (e.g., '10:30')\n"
                "- For weekday intervals: Use 'HH:MM' format (e.g., '14:15')\n"
                "- For 'hour' interval: Use ':MM' format (e.g., ':45')\n"
                "- For 'minute' interval: Use ':SS' format (e.g., ':30')\n"
                "- For other intervals: Leave empty"
            )
    
    return set_recurring_reminder


def get_reminders_tool():
    """
    Create a tool for getting pending reminders
    """
    @tool
    def get_reminders() -> str:
        """
        Get all pending reminders
        
        Args:
            None
        """
        # Get all jobs with the 'reminder' or 'recurring' tag
        one_time_jobs = schedule.get_jobs('reminder')
        recurring_jobs = schedule.get_jobs('recurring')
        
        if not one_time_jobs and not recurring_jobs:
            return "You have no pending reminders."
        
        result = []
        
        if one_time_jobs:
            result.append("One-time reminders:")
            for i, job in enumerate(one_time_jobs, 1):
                # Extract the reminder ID and message from the keywords
                reminder_id = job.job_func.keywords.get(
                    'reminder_id', 'unknown ID'
                )
                message = job.job_func.keywords.get('message', 'Reminder')
                
                # Format the next run time
                next_run = job.next_run
                if next_run:
                    time_str = next_run.strftime('%A, %B %d at %I:%M %p')
                    result.append(f"{i}. {message} - {time_str} (ID: {reminder_id})")
                else:
                    result.append(f"{i}. {message} (ID: {reminder_id})")
        
        if recurring_jobs:
            if one_time_jobs:
                result.append("\nRecurring reminders:")
                start_idx = len(one_time_jobs) + 1
            else:
                result.append("Recurring reminders:")
                start_idx = 1
                
            for i, job in enumerate(recurring_jobs, start_idx):
                # Extract the reminder ID, message, and pattern information
                reminder_id = job.job_func.keywords.get(
                    'reminder_id', 'unknown ID'
                )
                message = job.job_func.keywords.get('message', 'Reminder')
                interval = job.job_func.keywords.get('interval', 'Unknown schedule')
                time_spec = job.job_func.keywords.get('time_spec', '')
                
                # Format the next run time
                next_run = job.next_run
                if next_run:
                    time_str = next_run.strftime('%A, %B %d at %I:%M %p')
                    
                    # Format the schedule information
                    if time_spec:
                        schedule_info = f"{interval} at {time_spec}"
                    else:
                        schedule_info = interval
                    
                    result.append(
                        f"{i}. {message} - Next: {time_str}, Pattern: {schedule_info} "
                        f"(ID: {reminder_id})"
                    )
                else:
                    # Format the schedule information
                    if time_spec:
                        schedule_info = f"{interval} at {time_spec}"
                    else:
                        schedule_info = interval
                    
                    result.append(
                        f"{i}. {message} - Pattern: {schedule_info} (ID: {reminder_id})"
                    )
        
        return "\n".join(result)
    
    return get_reminders


def cancel_reminder_tool():
    """
    Create a tool for canceling reminders
    """
    @tool
    def cancel_reminder(reminder_id: str) -> str:
        """
        Cancel a reminder by its ID
        
        Args:
            reminder_id: The ID of the reminder to cancel
        """
        # Get jobs with the specific reminder_id tag
        jobs = schedule.get_jobs(reminder_id)
        
        if jobs:
            # Extract information from the first job's keywords
            message = jobs[0].job_func.keywords.get('message', "Reminder")
            
            # Check if this is a recurring reminder
            is_recurring = 'recurring' in jobs[0].tags
            
            if is_recurring:
                interval = jobs[0].job_func.keywords.get('interval', '')
                time_spec = jobs[0].job_func.keywords.get('time_spec', '')
                
                # Format the schedule information
                if time_spec:
                    schedule_info = f"{interval} at {time_spec}"
                else:
                    schedule_info = interval
            
            # Clear all jobs with this tag
            schedule.clear(reminder_id)
            
            if is_recurring:
                return (
                    f"Recurring reminder '{message}' ({schedule_info}) "
                    f"(ID: {reminder_id}) has been cancelled."
                )
            else:
                return (
                    f"One-time reminder '{message}' (ID: {reminder_id}) "
                    f"has been cancelled."
                )
        else:
            return f"Could not find reminder with ID {reminder_id}."
    
    return cancel_reminder