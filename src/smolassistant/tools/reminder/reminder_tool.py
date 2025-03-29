from datetime import datetime
import uuid

import schedule
from smolagents import tool


def set_reminder_tool(callback_fn):
    """
    Create a tool for setting reminders.
    All reminders are routed to you, the agent, to handle.
    Depending on the reminder, you may need to notify the user
    or take some other action.
    
    Args:
        callback_fn: Function to call when a reminder is triggered
    """
    @tool
    def set_reminder(message: str, due_time: str) -> str:
        """
        Set a reminder for a future time.
        
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
        
        return f"Reminder set for {due_time}. (Reminder ID: {reminder_id})"
    
    return set_reminder


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
        # Get all jobs with the 'reminder' tag
        jobs = schedule.get_jobs('reminder')
        
        if not jobs:
            return "You have no pending reminders."
            
        result = "Here are your pending reminders:\n\n"
        for i, job in enumerate(jobs, 1):
            # Extract the reminder ID and message from the keywords
            reminder_id = job.job_func.keywords.get(
                'reminder_id', 'unknown ID'
            )
            message = job.job_func.keywords.get('message', 'Reminder')
            
            # Format the next run time
            next_run = job.next_run
            if next_run:
                time_str = next_run.strftime('%A, %B %d at %I:%M %p')
                result += f"{i}. {message} - {time_str} (ID: {reminder_id})\n"
            else:
                result += f"{i}. {message} (ID: {reminder_id})\n"
            
        return result
    
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
            # Extract the message from the first job's keywords
            message = jobs[0].job_func.keywords.get('message', "Reminder")
            
            # Clear all jobs with this tag
            schedule.clear(reminder_id)
            return (
                f"Reminder '{message}' (ID: {reminder_id}) "
                f"has been cancelled."
            )
        else:
            return f"Could not find reminder with ID {reminder_id}."
    
    return cancel_reminder