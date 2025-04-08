import os
import queue
import re
from datetime import datetime

from nicegui import run, ui
from smolagents import CodeAgent, DuckDuckGoSearchTool, LiteLLMModel
from phoenix.otel import register
from openinference.instrumentation.smolagents import SmolagentsInstrumentor

# Removed unused imports since we're not displaying memory steps for now
from .config import ConfigManager, config_dir
from .tools.google import (
    add_google_account,
    get_unread_emails_tool,
    initialize_all_google_auth,
    initialize_google_auth,
    search_emails_tool,
    get_upcoming_events_tool,
    search_calendar_events_tool,
)
from .tools.llm_text_processor import (
    SummarizingVisitWebpageTool,
    process_text_tool,
)
from .tools.message_history import MessageHistory, get_message_history_tool
from .tools.reminder import (
    cancel_reminder_tool,
    get_reminders_tool,
    set_recurring_reminder_tool,
    set_reminder_tool,
)
from .tools.reminder.service import ReminderService
from .tools.telegram import create_telegram_bot, run_telegram_bot


def format_message_for_ui(message):
    """
    Format a message for UI display by converting newlines to <br> tags.
    
    Args:
        message: The message to format
        
    Returns:
        Formatted message with newlines converted to <br> tags
    """
    # Replace newlines with <br> tags, but preserve existing HTML
    return message.replace('\n', '<br>')


def get_current_time():
    """Get formatted current time for message timestamps."""
    return datetime.now().strftime("%H:%M")


async def process_message(
    message,
    agent,
    container,
    message_history,
    telegram_cb=None,
    additional_instructions="",
):
    """
    Process a message through the agent and display the response.

    Args:
        message: The message to process
        agent: The agent to process the message
        container: The UI container to display the message and response
        message_history: The MessageHistory instance to store messages
        telegram_cb: Optional callback to send the response to Telegram
    """
    # Add user message to history
    message_history.add_message("user", message)

    # Custom styled user message
    with container:
        with ui.element("div").classes("flex justify-end q-mb-md"):
            with ui.card().props('flat bordered').classes("q-pa-sm bg-primary-2"):
                ui.label("You").classes("text-subtitle2 text-weight-medium text-primary")
                ui.label(message).classes("text-body1")
                ui.label(get_current_time()).classes("text-caption text-weight-light text-grey-6 text-right")
    
    # Process the message
    response = await run.io_bound(
        agent.run, message + "\n" + additional_instructions, reset=True,
    )
    
    # Format the response for UI display (convert newlines to <br>)
    ui_response = format_message_for_ui(response)
    
    # Custom styled assistant message
    with container:
        with ui.element("div").classes("flex justify-start q-mb-md"):
            with ui.card().props('flat bordered').classes("q-pa-sm bg-dark"):
                ui.label("Assistant").classes("text-subtitle2 text-weight-medium text-secondary")
                ui.html(ui_response).classes("text-body1")
                ui.label(get_current_time()).classes("text-caption text-weight-light text-grey-6 text-right")

    # Add assistant response to history (original format)
    message_history.add_message("assistant", response)

    # If Telegram response callback is available, send the original response there too
    if telegram_cb:
        telegram_cb(response)  # Send original format to Telegram

    return response


async def process_queue(
    message_queue,
    agent,
    container,
    message_history,
    telegram_cb=None,
    additional_instructions="",
):
    """
    Process all messages in the queue.

    Args:
        message_queue: The queue containing messages to process
        agent: The agent to process the messages
        container: The UI container to display messages and responses
        message_history: The MessageHistory instance to store messages
        telegram_cb: Optional callback to send responses to Telegram
    """
    # Check if there are messages in the queue
    if not message_queue.empty():
        # Process all messages in the queue
        while not message_queue.empty():
            # Get the next message from the queue
            message = message_queue.get()
            # Process the message
            await process_message(
                message,
                agent,
                container,
                message_history,
                telegram_cb,
                additional_instructions=additional_instructions,
            )


async def send_message(
    message_queue,
    message,
    agent,
    container,
    message_history,
    telegram_cb=None,
    additional_instructions="",
):
    """
    Send a message to the agent via the queue.

    Args:
        message_queue: The queue to add the message to
        message: The message to send
        agent: The agent to process the message
        container: The UI container to display messages and responses
        message_history: The MessageHistory instance to store messages
        telegram_cb: Optional callback to send responses to Telegram
    """
    # Store message value and clear input field immediately
    msg_value = message.strip()
    
    # Only process if there's actual content
    if msg_value:
        message_queue.put(msg_value)
        await process_queue(
            message_queue,
            agent,
            container,
            message_history,
            telegram_cb,
            additional_instructions=additional_instructions,
        )


# Setup Google auth functions
async def setup_gmail_auth():
    """Initialize Google API authentication for all accounts."""
    # Get the number of accounts
    config = ConfigManager().config
    accounts = config.config.get("google", {}).get("accounts", [])
    if not accounts:
        accounts = config.config.get("gmail", {}).get("accounts", [])

    # Notify user that authentication is starting
    ui.notify(
        f"Starting authentication for {len(accounts) + 1} Google accounts. "
        "Check the console for progress.",
        position="top",
        color="primary",
    )

    # Use run.io_bound to prevent blocking the UI
    result = await run.io_bound(initialize_all_google_auth)

    # Display result to user
    ui.notify(
        result,
        position="top",
        color="positive" if "successful" in result.lower() else "negative",
    )


async def setup_specific_gmail_auth(account_info):
    """Initialize Google API authentication for a specific account."""
    if not account_info:
        return
    print(account_info)
    account_name, token_path = account_info

    # Use run.io_bound to prevent blocking the UI
    result = await run.io_bound(
        initialize_google_auth, account_name, token_path,
    )
    # Display result to user
    ui.notify(
        result,
        position="top",
        color="positive" if "successful" in result.lower() else "negative",
    )


async def add_new_gmail_account():
    """Add a new Google account to the configuration."""
    # Create a dialog to get account details
    with ui.dialog() as dialog, ui.card():
        ui.label("Add New Google Account").classes("text-h5 text-weight-medium text-primary q-mb-md")
        ui.label("Enter account details").classes("text-body2 text-weight-regular q-mb-md")
        name_input = ui.input("Account Name").props('outlined filled')

        async def submit():
            name = name_input.value

            if not name:
                ui.notify("Please enter an account name", color="warning")
                return

            # Use run.io_bound to prevent blocking the UI
            result = await run.io_bound(add_google_account, name)
            ui.notify(
                result,
                position="top",
                color="positive" if "successful" in result.lower() else "negative",
            )
            dialog.close()

        with ui.row().classes("justify-end q-mt-md"):
            ui.button("Cancel", on_click=dialog.close).classes("text-button")
            ui.button("Add", on_click=submit).props('color=positive').classes("text-button")

    dialog.open()


def main(config: ConfigManager):
    """Entry point for the assistant with GUI"""
    # Create a queue for all messages (both user input and reminders)
    message_queue = queue.Queue()

    # Initialize the message history with max size from config
    message_history = MessageHistory(
        max_size=config.config.get("message_history", {}).get("max_size", 20),
    )

    # Get the database path from config
    db_path = config.config.get("reminders", {}).get(
        "db_path", "reminders.sqlite",
    )

    # If the path is not absolute, make it relative to the config directory
    if not os.path.isabs(db_path):
        db_path = os.path.join(config_dir, db_path)

    # Initialize ReminderService for thread management and persistence
    reminder_service = ReminderService(
        db_path=db_path,
        reminder_queue=message_queue,
    )
    reminder_service.start()
    
    # Initialize telemetry if enabled
    if config.config.get("telemetry", {}).get("enabled", True):
        register()
        SmolagentsInstrumentor().instrument()
    
    # Create the agent
    model = LiteLLMModel(
        model_id=config.config["model"],
        api_key=config.config["api_key"],
    )

    # Create a closure for summarize_text using the process_text_tool
    text_processor, summarize_text = process_text_tool(config)

    # Initialize tools
    def reminder_callback(msg):
        message_queue.put(msg)

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
        get_message_history_tool(message_history),
    ]
    # Create agent
    agent = CodeAgent(
        tools=tools,
        model=model,
        planning_interval=3,
    )

    # Add additional system prompt text if provided in config
    if config.config.get("additional_system_prompt"):
        # Process the template to replace placeholders with actual values
        processed_prompt = config.process_template(config.config["additional_system_prompt"])
        
        agent.prompt_templates["system_prompt"] = (
            agent.prompt_templates["system_prompt"]
            + "\n"
            + processed_prompt
        )

    # Check if Telegram is enabled
    telegram_enabled = config.config.get("telegram", {}).get("enabled", False)
    telegram_token = config.config.get("telegram", {}).get("token", "")
    authorized_user_id = config.config.get("telegram", {}).get(
        "authorized_user_id",
    )

    # Initialize and start Telegram bot if enabled
    telegram_cb = None
    if telegram_enabled and telegram_token:
        print("Telegram bot is enabled.")

        # Create the bot with access to the message queue
        bot, telegram_cb = create_telegram_bot(
            message_queue=message_queue,
            token=telegram_token,
            config=config,
            authorized_user_id=authorized_user_id,
        )

        # Start the bot in a background thread
        run_telegram_bot(bot)

    # Create the UI with dark theme
    ui.dark_mode().enable()

    # Add custom CSS for styling consistency
    ui.add_head_html("""
    <style>
    :root {
        --background-dark: #121212;
        --card-dark: #1E1E1E;
        --primary-color: #1976D2;
        --secondary-color: #26A69A;
        --accent-color: #9C27B0;
    }
    .scroll-area-with-thumb::-webkit-scrollbar {
        width: 8px;
    }
    .scroll-area-with-thumb::-webkit-scrollbar-thumb {
        background: #666;
        border-radius: 4px;
    }
    .bg-primary-2 {
        background-color: rgba(25, 118, 210, 0.2);
    }
    </style>
    """)

    # Apply standard CSS styles to ensure proper element containment
    ui.query('.nicegui-content').classes('h-screen p-0')
    
    # Main layout container with fixed width sidebar and chat area
    with ui.row().classes('w-full h-screen no-wrap p-0 m-0'):
        # Left sidebar - fixed width with Gmail setup and future config options
        with ui.column().classes('w-1/4 h-full').style('min-width: 300px; max-width: 300px; background-color: var(--card-dark)'):
            with ui.card().props('flat bordered').classes("w-full h-full q-pa-md"):
                ui.label("Google Accounts").classes("text-h5 text-weight-medium text-primary q-mb-md")
                
                # Setup All button with Quasar styling
                ui.button(
                    "Setup All Google Accounts", 
                    on_click=setup_gmail_auth
                ).props('color=primary full-width unelevated').classes("text-button q-mb-md")
                
                # Account selection
                accounts = config.config.get("google", {}).get("accounts", [])
                if not accounts:
                    accounts = config.config.get("gmail", {}).get("accounts", [])
                
                account_options = {}
                
                for account in accounts:
                    name = account.get("name", "unnamed")
                    token_path = os.path.join(
                        config_dir, account.get("token_path"),
                    )
                    account_options[(name, token_path)] = name
                
                if account_options:
                    ui.label("Account Selection").classes("text-subtitle2 text-weight-medium q-mt-sm q-mb-xs")
                    ui.select(
                        options=account_options,
                        label="Select account to setup",
                        on_change=lambda e: setup_specific_gmail_auth(e.value),
                    ).props('outlined filled bg-dark').classes("w-full q-mb-md")
                
                ui.separator().props('dark spaced')
                
                # Add New Account button with improved styling
                ui.button(
                    "Add New Google Account", 
                    on_click=add_new_gmail_account
                ).props('color=positive full-width unelevated').classes("text-button q-mt-md")
                
                # Telemetry section
                ui.separator().props('dark spaced')
                
                # Telemetry button
                telemetry_button = ui.button(
                    "Open Telemetry Dashboard", 
                    on_click=lambda: ui.navigate.to("http://0.0.0.0:6006", new_tab=True)
                ).props('color=secondary full-width unelevated').classes("text-button q-mb-md")

                # Disable button if telemetry is not enabled
                if not config.config.get("telemetry", {}).get("enabled", True):
                    telemetry_button.props('disabled')
                
                # Reserved space for future configuration UI
                with ui.expansion("Future Configuration").classes("q-mt-xl w-full"):
                    ui.label("Configuration Options").classes("text-subtitle1 text-weight-regular")
                    ui.label("Space reserved for future configuration options").classes("text-body2 text-weight-light text-grey-6")
        
        # Main chat area - takes remaining width
        with ui.column().classes('w-3/4 h-full p-4'):
            # Container for chat messages with improved styling
            ui.label("Chat").classes("text-h4 text-weight-regular text-primary q-mb-md")
            
            chat_message_container = ui.scroll_area().classes(
                "w-full h-5/6 bg-grey-9 rounded-lg p-4 scroll-area-with-thumb"
            ).props('dark')
            
            # Input area with enhanced styling
            with ui.card().props('flat bordered').classes("w-full q-mt-md q-pa-sm"):
                # ui.label("Message").classes("text-caption text-weight-regular q-mb-xs text-grey-6")
                with ui.row().classes("w-full items-end justify-between"):
                    input_field = ui.textarea(
                        placeholder="Type your message...",
                    ).props('outlined filled autogrow hide-bottom-space').classes("flex-grow text-body1")
                    
                    send_button = ui.button(icon="send").props('round color=primary').classes("q-ml-sm self-center")
    # Define function to handle message sending and clear the input
    async def handle_send():
        message = input_field.value
        if message.strip():
            # Clear the input field immediately
            current_message = message
            input_field.value = ""
            # Send the message
            await send_message(
                message_queue,
                current_message,
                agent,
                chat_message_container,
                message_history,
                telegram_cb,
                additional_instructions=config.config["additional_instructions"],
            )

    # Event handler for input field and send button
    input_field.on("keydown.enter", handle_send)
    send_button.on("click", handle_send)

    # Process queue timer
    ui.timer(
        1.0,
        lambda: process_queue(
            message_queue,
            agent,
            chat_message_container,
            message_history,
            telegram_cb,
            additional_instructions=config.config["additional_instructions"],
        ),
    )

    # Start the UI
    ui.run(
        title="SmolAssistant",
        favicon="🤖",
        reload=False,
    )


if __name__ in {"__main__", "__mp_main__", "smolassistant.__main__"}:
    try:
        config = ConfigManager()
        main(config)
    except Exception as e:
        print(f"Fatal error: {e!s}")