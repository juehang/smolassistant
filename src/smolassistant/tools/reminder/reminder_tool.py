from datetime import datetime

import schedule
from smolagents import tool


def set_reminder_tool(callback_fn, reminder_service):
    """
    Create a tool for setting one-time reminders.
    All reminders are routed to you, the agent, to handle.
    Depending on the reminder, you may need to notify the user
    or take some other action.
    
    Args:
        callback_fn: Function to call when a reminder is triggered
        reminder_service: ReminderService instance for persistence
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
        
        # Calculate seconds until the reminder is due
        now = datetime.now()
        if parsed_time <= now:
            # Due time has already passed, trigger immediately
            formatted_message = f"🔔 REMINDER: {message}"
            callback_fn(formatted_message)
            return f"Reminder triggered immediately as the due time ({due_time}) has already passed."
            
        # Create the reminder through the service
        reminder_id, _ = reminder_service.create_one_time_reminder(
            message=message,
            due_time=due_time
        )
        
        if reminder_id:
            return f"One-time reminder set for {due_time}. (Reminder ID: {reminder_id})"
        else:
            return "Failed to set reminder. Please try again."
    
    return set_reminder


def set_recurring_reminder_tool(callback_fn, reminder_service):
    """
    Create a tool for setting recurring reminders.
    All reminders are routed to you, the agent, to handle.
    Depending on the reminder, you may need to notify the user
    or take some other action.
    
    Args:
        callback_fn: Function to call when a reminder is triggered
        reminder_service: ReminderService instance for persistence
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
        # Create the recurring reminder through the service
        reminder_id, job = reminder_service.create_recurring_reminder(
            message=message,
            interval=interval,
            time_spec=time_spec
        )
        
        if reminder_id and job:
            if time_spec:
                return f"Recurring reminder set ({interval} at {time_spec}). (Reminder ID: {reminder_id})"
            else:
                return f"Recurring reminder set ({interval}). (Reminder ID: {reminder_id})"
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


def get_reminders_tool(reminder_service):
    """
    Create a tool for getting pending reminders
    
    Args:
        reminder_service: ReminderService instance for persistence
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


def cancel_reminder_tool(reminder_service):
    """
    Create a tool for canceling reminders
    
    Args:
        reminder_service: ReminderService instance for persistence
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
                
                # Delete from database and schedule
                success = reminder_service.delete_recurring_reminder(reminder_id)
                
                if success:
                    return (
                        f"Recurring reminder '{message}' ({schedule_info}) "
                        f"(ID: {reminder_id}) has been cancelled."
                    )
            else:
                # Delete from database and schedule
                success = reminder_service.delete_one_time_reminder(reminder_id)
                
                if success:
                    return (
                        f"One-time reminder '{message}' (ID: {reminder_id}) "
                        f"has been cancelled."
                    )
        
        return f"Could not find reminder with ID {reminder_id}."
    
    return cancel_reminder