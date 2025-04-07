import os
import sys
import asyncio
import json
import threading
import logging
import datetime
import traceback
from typing import Dict, List, Tuple, Optional, Any, Set, Callable
import textwrap

import nicegui
from nicegui import app, ui
import litellm
from litellm import completion

from smolagents import (
    CodeAgent,
    DuckDuckGoSearchTool,
    VisitWebpageTool,
    WikipediaQueryTool,
)
import pytz
from loguru import logger
logger.remove()
logger.add(
    lambda msg: logging.info(msg),
    format="{message}",
    filter=lambda record: record["level"].name == "INFO"
)

# Import our tools
from .config import ConfigManager
from .tools import (
    set_reminder_tool,
    set_recurring_reminder_tool,
    get_reminders_tool,
    cancel_reminder_tool,
    get_unread_emails_tool,
    search_emails_tool,
    get_upcoming_events_tool,
    search_calendar_events_tool,
    initialize_gmail_auth,
    initialize_calendar_auth,
    create_telegram_bot,
    run_telegram_bot,
    process_text_tool,
    SummarizingVisitWebpageTool,
)

# Initialize configuration
config = ConfigManager().config


class MessageService:
    """Manages messages from all sources."""

    def __init__(self):
        self.messages = {}
        self.counter = 0
        self.lock = threading.Lock()

    def add_message(
        self, content: str, role: str = "user", source: str = "web"
    ) -> int:
        """Add a message and return its ID."""
        with self.lock:
            message_id = self.counter
            self.counter += 1
            self.messages[message_id] = {
                "content": content,
                "role": role,
                "source": source,
                "timestamp": datetime.datetime.now().isoformat(),
            }
            return message_id

    def get_message(self, message_id: int) -> Dict:
        """Get a message by ID."""
        return self.messages.get(message_id, {})

    def get_messages(self) -> Dict[int, Dict]:
        """Get all messages."""
        return self.messages.copy()


# Create a global message service
message_service = MessageService()


def get_message_history_tool(history_service: MessageService):
    """
    Create a tool to get message history.

    Args:
        history_service: The message history service

    Returns:
        A tool function
    """
    from smolagents import tool

    @tool
    def get_message_history(max_messages: int = 10) -> str:
        """
        Get recent message history to maintain context.

        Args:
            max_messages: Maximum number of messages to return (default: 10)

        Returns:
            Recent message history as a string
        """
        messages = history_service.get_messages()
        # Sort by ID (which corresponds to creation order)
        sorted_msgs = sorted(messages.items(), key=lambda x: x[0], reverse=True)
        # Take the most recent N messages
        recent_msgs = sorted_msgs[:max_messages]
        # Reverse to get chronological order
        recent_msgs.reverse()

        # Format messages
        result = "Recent message history:\n\n"
        for msg_id, msg in recent_msgs:
            source = msg.get("source", "unknown")
            role = msg.get("role", "user")
            content = msg.get("content", "")
            timestamp = msg.get("timestamp", "")

            # Format timestamp if available
            time_str = ""
            if timestamp:
                try:
                    dt = datetime.datetime.fromisoformat(timestamp)
                    time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    time_str = timestamp

            result += f"ID: {msg_id} | Source: {source} | Role: {role} | Time: {time_str}\n"
            result += f"Content: {content}\n\n"

        return result

    return get_message_history


class ReminderService:
    """Manages one-time and recurring reminders."""

    def __init__(self):
        import schedule
        self.schedule = schedule
        self.reminders = {}
        self.recurring_reminders = {}
        self.next_id = 1
        self.callback = None
        self.lock = threading.Lock()
        self.scheduler_thread = None
        self.running = False

    def set_callback(self, callback_func):
        """Set the callback function to be called when a reminder is triggered."""
        self.callback = callback_func

    def set_reminder(self, text, datetime_str):
        """
        Set a one-time reminder.

        Args:
            text: The reminder text
            datetime_str: ISO format datetime string

        Returns:
            Reminder ID and scheduled time
        """
        with self.lock:
            reminder_id = f"reminder_{self.next_id}"
            self.next_id += 1

            # Parse the datetime string
            dt = datetime.datetime.fromisoformat(datetime_str)

            # Calculate seconds until the reminder
            now = datetime.datetime.now()
            seconds_until = (dt - now).total_seconds()

            if seconds_until <= 0:
                return f"Error: Cannot set reminder in the past. Requested time: {dt}, Current time: {now}"

            # Add the job to the schedule
            self.schedule.every(seconds_until).seconds.do(
                self._trigger_reminder, reminder_id=reminder_id, text=text
            ).tag(reminder_id, "reminder")

            # Store the reminder info
            self.reminders[reminder_id] = {
                "text": text,
                "datetime": dt.isoformat(),
                "created": now.isoformat(),
            }

            return reminder_id, dt.isoformat()

    def set_recurring_reminder(self, text, interval, time_spec=None):
        """
        Set a recurring reminder.

        Args:
            text: The reminder text
            interval: The interval (e.g., "day", "monday", "2 hours")
            time_spec: Optional time specification (e.g., "10:30")

        Returns:
            Reminder ID and next occurrence
        """
        with self.lock:
            reminder_id = f"recurring_{self.next_id}"
            self.next_id += 1

            # Process the interval and time_spec to create the schedule
            job = None

            # Parse various interval formats
            if interval.lower() == "day":
                # Daily at specified time
                if time_spec:
                    hour, minute = map(int, time_spec.split(":"))
                    job = self.schedule.every().day.at(time_spec).do(
                        self._trigger_reminder, reminder_id=reminder_id, text=text
                    )
                else:
                    # Daily from now
                    job = self.schedule.every().day.do(
                        self._trigger_reminder, reminder_id=reminder_id, text=text
                    )
            elif interval.lower() in [
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            ]:
                # Weekly on a specific day
                day_attr = getattr(self.schedule.every(), interval.lower())
                if time_spec:
                    job = day_attr.at(time_spec).do(
                        self._trigger_reminder, reminder_id=reminder_id, text=text
                    )
                else:
                    job = day_attr.do(
                        self._trigger_reminder, reminder_id=reminder_id, text=text
                    )
            elif interval.lower() == "hour":
                # Hourly at specified minute
                if time_spec and time_spec.startswith(":"):
                    minute = int(time_spec[1:])
                    job = self.schedule.every().hour.at(f":{minute:02d}").do(
                        self._trigger_reminder, reminder_id=reminder_id, text=text
                    )
                else:
                    # Every hour from now
                    job = self.schedule.every().hour.do(
                        self._trigger_reminder, reminder_id=reminder_id, text=text
                    )
            elif interval.lower() == "minute":
                # Every minute at specified second
                if time_spec and time_spec.startswith(":"):
                    second = int(time_spec[1:])
                    # Note: schedule doesn't support minute:second, so we use a custom approach
                    def run_at_second():
                        current_second = datetime.datetime.now().second
                        if current_second == second:
                            self._trigger_reminder(reminder_id=reminder_id, text=text)

                    job = self.schedule.every().minute.do(run_at_second)
                else:
                    # Every minute from now
                    job = self.schedule.every().minute.do(
                        self._trigger_reminder, reminder_id=reminder_id, text=text
                    )
            elif " " in interval:
                # Interval like "2 hours", "30 minutes"
                try:
                    number, unit = interval.split(" ", 1)
                    number = int(number)
                    unit = unit.rstrip("s")  # Remove potential plural 's'

                    if unit == "minute":
                        job = self.schedule.every(number).minutes.do(
                            self._trigger_reminder, reminder_id=reminder_id, text=text
                        )
                    elif unit == "hour":
                        job = self.schedule.every(number).hours.do(
                            self._trigger_reminder, reminder_id=reminder_id, text=text
                        )
                    elif unit == "day":
                        job = self.schedule.every(number).days.do(
                            self._trigger_reminder, reminder_id=reminder_id, text=text
                        )
                    elif unit == "week":
                        job = self.schedule.every(number).weeks.do(
                            self._trigger_reminder, reminder_id=reminder_id, text=text
                        )
                    elif unit == "second":
                        job = self.schedule.every(number).seconds.do(
                            self._trigger_reminder, reminder_id=reminder_id, text=text
                        )
                except ValueError:
                    return f"Error: Unable to parse interval '{interval}'"
            else:
                # Other intervals as seconds
                try:
                    seconds = int(interval)
                    job = self.schedule.every(seconds).seconds.do(
                        self._trigger_reminder, reminder_id=reminder_id, text=text
                    )
                except ValueError:
                    return f"Error: Unknown interval format '{interval}'"

            if job:
                job.tag(reminder_id, "recurring")
                # Store the reminder info
                self.recurring_reminders[reminder_id] = {
                    "text": text,
                    "interval": interval,
                    "time_spec": time_spec,
                    "created": datetime.datetime.now().isoformat(),
                }
                # Calculate next run time
                next_run = job.next_run
                if next_run:
                    return reminder_id, next_run.isoformat()
                else:
                    return reminder_id, "Unknown next run time"
            else:
                return f"Error: Failed to set recurring reminder with interval '{interval}'"

    def get_reminders(self):
        """Get all pending reminders."""
        with self.lock:
            result = "One-time reminders:\n"
            if not self.reminders:
                result += "  No one-time reminders set.\n"
            else:
                for reminder_id, info in self.reminders.items():
                    try:
                        dt = datetime.datetime.fromisoformat(info["datetime"])
                        formatted_dt = dt.strftime("%Y-%m-%d %H:%M:%S")
                        result += f"  🔔 {reminder_id}: {info['text']} (at {formatted_dt})\n"
                    except Exception as e:
                        result += f"  🔔 {reminder_id}: {info['text']} (Error: {str(e)})\n"

            result += "\nRecurring reminders:\n"
            if not self.recurring_reminders:
                result += "  No recurring reminders set.\n"
            else:
                for reminder_id, info in self.recurring_reminders.items():
                    time_spec_str = f" at {info['time_spec']}" if info['time_spec'] else ""
                    result += f"  🔄 {reminder_id}: {info['text']} (every {info['interval']}{time_spec_str})\n"

            return result

    def cancel_reminder(self, reminder_id):
        """Cancel a reminder by ID."""
        with self.lock:
            if reminder_id in self.reminders:
                # Clear all jobs with this tag
                self.schedule.clear(reminder_id)
                # Remove from our dictionary
                reminder_info = self.reminders.pop(reminder_id)
                return f"Cancelled one-time reminder: {reminder_info['text']}"
            elif reminder_id in self.recurring_reminders:
                # Clear all jobs with this tag
                self.schedule.clear(reminder_id)
                # Remove from our dictionary
                reminder_info = self.recurring_reminders.pop(reminder_id)
                return f"Cancelled recurring reminder: {reminder_info['text']}"
            else:
                return f"Error: No reminder found with ID {reminder_id}"

    def _trigger_reminder(self, reminder_id, text):
        """Trigger a reminder."""
        try:
            if self.callback:
                self.callback(text, reminder_id)

            # For one-time reminders, remove from storage after triggering
            if reminder_id in self.reminders:
                with self.lock:
                    self.reminders.pop(reminder_id, None)
                return self.schedule.CancelJob
            return None
        except Exception as e:
            print(f"Error triggering reminder: {str(e)}")
            traceback.print_exc()
            return None

    def start_scheduler(self):
        """Start the scheduler in a background thread."""
        if self.running:
            return  # Already running

        self.running = True

        def run_scheduler():
            while self.running:
                self.schedule.run_pending()
                # Sleep for a short time to avoid high CPU usage
                time.sleep(1)

        self.scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        self.scheduler_thread.start()

    def stop_scheduler(self):
        """Stop the scheduler."""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
            self.scheduler_thread = None


async def handle_user_message(
    agent_instance, message, context=None, sender_info=None, ui_callbacks=None
):
    """
    Process a user message through the agent.

    Args:
        agent_instance: The agent instance
        message: User message
        context: Optional context
        sender_info: Optional sender information
        ui_callbacks: Optional UI callbacks

    Returns:
        Agent response
    """
    try:
        logger.info(f"Received message: {message}")

        # Add to message history
        message_service.add_message(message, "user", sender_info or "unknown")

        # Create execution context
        if context is None:
            context = {}

        # Add sender info to context if provided
        if sender_info:
            context["sender"] = sender_info

        # Process the message through the agent
        response = agent_instance.process(message, context=context)

        # Add response to message history
        message_service.add_message(response, "assistant", "agent")

        return response
    except Exception as e:
        error_msg = f"Error processing message: {str(e)}"
        logger.error(error_msg)
        traceback.print_exc()
        return f"Sorry, I encountered an error: {str(e)}"


def main():
    """Main function to run the assistant."""
    import time

    # Create reminder service
    reminder_service = ReminderService()

    # Set up the NiceGUI web interface
    ui.colors(primary="#6d28d9")  # Use a nice purple color

    # Create a dictionary to store UI references
    ui_refs = {
        "chat_messages": None,  # Will store the chat messages container
        "input_box": None,      # Will store the input box
        "progress_bar": None,   # Will store the progress bar
    }

    # Callback for reminder notifications
    async def reminder_callback(text, reminder_id):
        """Handle reminder triggers."""
        # Get the reminder type from the ID
        reminder_type = "one-time" if reminder_id.startswith("reminder_") else "recurring"
        
        # Create notification text
        if reminder_type == "one-time":
            notification_text = f"🔔 Reminder: {text}"
        else:
            notification_text = f"🔄 Recurring reminder: {text}"
        
        # Create a notification
        await ui.notify(
            notification_text,
            type="info",
            position="top-right",
            close_button="OK",
            timeout=30,
        )
        
        # Also add it to the chat if the chat interface exists
        if ui_refs["chat_messages"] is not None:
            ui_refs["chat_messages"].add_message(
                "assistant", notification_text
            )

    # Set the callback for reminders
    reminder_service.set_callback(reminder_callback)

    # Start the reminder scheduler
    reminder_service.start_scheduler()

    # Create LLM text processor
    process_text, summarize_text = process_text_tool()

    async def format_user_message(content):
        """Format user messages for display."""
        return ui.chat_message(
            content,
            name="You",
            avatar="https://robohash.org/user?bgset=bg1",
        ).classes("items-end")

    async def format_assistant_message(content):
        """Format assistant messages for display."""
        return ui.chat_message(
            content,
            name="Assistant",
            avatar="https://robohash.org/assistant?bgset=bg1",
        ).classes("items-start")

    async def on_submit_message():
        """Handle message submission."""
        nonlocal agent
        content = ui_refs["input_box"].value
        ui_refs["input_box"].value = ""

        # Add user message to the chat
        await ui_refs["chat_messages"].add_message("user", content)

        # Show progress
        progress = ui.spinner("dots", size="3rem", color="primary")
        progress.open()

        try:
            # Process the message
            response = await handle_user_message(agent, content)

            # Add assistant response to the chat
            await ui_refs["chat_messages"].add_message("assistant", response)
        except Exception as e:
            # Add error message to the chat
            error_msg = f"Sorry, I encountered an error: {str(e)}"
            await ui_refs["chat_messages"].add_message("assistant", error_msg)
        finally:
            # Hide progress
            progress.close()

    # Create the UI
    @ui.page("/")
    async def home():
        """Create the home page UI."""
        # Access the ui_refs from the outer scope
        nonlocal ui_refs

        with ui.column().classes("w-full max-w-3xl mx-auto p-4 gap-4"):
            ui.label("SmolAssistant").classes("text-2xl font-bold text-center")

            # Create chat messages container
            chat_messages = ui.chat().classes("w-full h-96 overflow-auto")
            ui_refs["chat_messages"] = chat_messages

            # Create the input layout
            with ui.row().classes("w-full"):
                input_box = ui.input(placeholder="Type your message here...")
                input_box.classes("flex-grow mr-2")
                input_box.on("keydown.enter", on_submit_message)
                ui_refs["input_box"] = input_box

                ui.button("Send", on_click=on_submit_message).classes("bg-primary")

            # Add a welcome message
            await chat_messages.add_message(
                "assistant", "Hello! I'm SmolAssistant. How can I help you today?"
            )

    # Try to start the Telegram bot if configured
    if "telegram" in config and "bot_token" in config["telegram"]:
        try:
            # Create the bot
            bot = create_telegram_bot(config["telegram"]["bot_token"])

            # Define message handler
            @bot.message_handler(content_types=["text"])
            async def handle_telegram_message(message):
                """Handle Telegram messages."""
                nonlocal agent
                try:
                    user_id = message.from_user.id
                    username = message.from_user.username or str(user_id)
                    chat_id = message.chat.id
                    message_text = message.text

                    sender_info = f"telegram:{username}"

                    # Process the message
                    response = await handle_user_message(
                        agent, message_text, sender_info=sender_info
                    )

                    # Send response back to Telegram
                    # Split long messages if needed (Telegram has a 4096 character limit)
                    max_length = 4000
                    for i in range(0, len(response), max_length):
                        chunk = response[i:i + max_length]
                        try:
                            await bot.send_message(chat_id, chunk)
                        except Exception as e:
                            print(f"Error sending Telegram message: {str(e)}")
                except Exception as e:
                    error_msg = f"Error processing Telegram message: {str(e)}"
                    print(error_msg)
                    traceback.print_exc()
                    try:
                        await bot.send_message(
                            message.chat.id, f"Sorry, I encountered an error: {str(e)}"
                        )
                    except Exception:
                        pass

            # Start the bot in a background thread
            run_telegram_bot(bot)
            print("Telegram bot started")
        except Exception as e:
            print(f"Failed to start Telegram bot: {str(e)}")

    # Get the model configuration
    model_config = config.get("model", {})
    model_name = model_config.get("name", "gpt-3.5-turbo")
    api_key = model_config.get("api_key", None)
    base_url = model_config.get("base_url", None)

    # Configure litellm
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
    if base_url:
        os.environ["OPENAI_API_BASE"] = base_url

    # Set up the model
    model = {"model": model_name}

    # Create tools list
    tools = [
        DuckDuckGoSearchTool(),
        # Replace VisitWebpageTool with our summarizing version
        SummarizingVisitWebpageTool(summarize_func=summarize_text),
        # Add our text processor tool
        text_processor,
        set_reminder_tool(reminder_callback, reminder_service),
        set_recurring_reminder_tool(reminder_callback, reminder_service),
        get_reminders_tool(reminder_service),
        cancel_reminder_tool(reminder_service),
        # Pass the summarize function to our email tools
        get_unread_emails_tool(summarize_func=summarize_text),
        search_emails_tool(summarize_func=summarize_text),
        # Add calendar tools
        get_upcoming_events_tool(summarize_func=summarize_text),
        search_calendar_events_tool(summarize_func=summarize_text),
        get_message_history_tool(message_service),
    ]
    # Create agent
    agent = CodeAgent(
        tools=tools,
        model=model,
        planning_interval=3,
    )

    # Start the UI
    ui.run(
        title="SmolAssistant",
        favicon="🤖",
        storage_secret="smolassistant_secret_key",
    )


if __name__ == "__main__":
    main()
