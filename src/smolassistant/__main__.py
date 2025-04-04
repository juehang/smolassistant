import os
import queue
import re

from nicegui import run, ui
from smolagents import CodeAgent, DuckDuckGoSearchTool, LiteLLMModel

# Removed unused imports since we're not displaying memory steps for now
from .config import ConfigManager, config_dir
from .tools.gmail import (
    add_gmail_account,
    get_unread_emails_tool,
    initialize_all_gmail_auth,
    initialize_gmail_auth,
    search_emails_tool,
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

    # Process the message and get the response
    # Display the user message in the chat container
    with container:
        ui.chat_message(
            text=message,
            name="You",
            sent=True,
        )
    response = await run.io_bound(
        agent.run, message + "\n" + additional_instructions, reset=True,
    )
    
    # Format the response for UI display (convert newlines to <br>)
    ui_response = format_message_for_ui(response)
    
    # Display the response in the chat container
    with container:
        ui.chat_message(
            text=ui_response, name="Assistant", sent=False, text_html=True,
        )

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


# Setup Gmail auth functions
async def setup_gmail_auth():
    """Initialize Gmail API authentication for all accounts."""
    # Get the number of accounts
    config = ConfigManager().config
    accounts = config.config.get("gmail", {}).get("accounts", [])

    # Notify user that authentication is starting
    ui.notify(
        f"Starting authentication for {len(accounts) + 1} Gmail accounts. "
        "Check the console for progress.",
        position="top",
        color="primary",
    )

    # Use run.io_bound to prevent blocking the UI
    result = await run.io_bound(initialize_all_gmail_auth)

    # Display result to user
    ui.notify(
        result,
        position="top",
        color="positive" if "successful" in result.lower() else "negative",
    )


async def setup_specific_gmail_auth(account_info):
    """Initialize Gmail API authentication for a specific account."""
    if not account_info:
        return
    print(account_info)
    account_name, token_path = account_info

    # Use run.io_bound to prevent blocking the UI
    result = await run.io_bound(
        initialize_gmail_auth, account_name, token_path,
    )
    # Display result to user
    ui.notify(
        result,
        position="top",
        color="positive" if "successful" in result.lower() else "negative",
    )


async def add_new_gmail_account():
    """Add a new Gmail account to the configuration."""
    # Create a dialog to get account details
    with ui.dialog() as dialog, ui.card():
        ui.label("Add New Gmail Account").classes("text-h6 q-mb-md")
        name_input = ui.input("Account Name")

        async def submit():
            name = name_input.value

            if not name:
                ui.notify("Please enter an account name", color="warning")
                return

            # Use run.io_bound to prevent blocking the UI
            result = await run.io_bound(add_gmail_account, name)
            ui.notify(
                result,
                position="top",
                color="positive" if "successful" in result.lower() else "negative",
            )
            dialog.close()

        with ui.row().classes("justify-end q-mt-md"):
            ui.button("Cancel", on_click=dialog.close)
            ui.button("Add", on_click=submit).props('color=positive')

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
        agent.prompt_templates["system_prompt"] = (
            agent.prompt_templates["system_prompt"]
            + "\n"
            + config.config["additional_system_prompt"]
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

    # Apply standard CSS styles to ensure proper element containment
    ui.query('.nicegui-content').classes('h-screen p-0')
    
    # Main layout container with fixed width sidebar and chat area
    with ui.row().classes('w-full h-screen no-wrap p-0 m-0'):
        # Left sidebar - fixed width with Gmail setup and future config options
        with ui.column().classes('w-1/4 h-full').style('min-width: 300px; max-width: 300px'):
            with ui.card().classes("w-full h-full p-4 overflow-auto"):
                ui.label("Gmail Accounts").classes("text-h6 mb-4 text-primary")
                
                # Setup All button
                ui.button(
                    "Setup All Gmail Accounts", 
                    on_click=setup_gmail_auth
                ).props('color=primary full-width').classes("mb-4")
                
                # Account selection
                accounts = config.config.get("gmail", {}).get("accounts", [])
                account_options = {}
                
                for account in accounts:
                    name = account.get("name", "unnamed")
                    token_path = os.path.join(
                        config_dir, account.get("token_path"),
                    )
                    account_options[(name, token_path)] = name
                
                if account_options:
                    ui.select(
                        options=account_options,
                        label="Select account to setup",
                        on_change=lambda e: setup_specific_gmail_auth(e.value),
                    ).classes("w-full mb-4")
                
                ui.separator().classes("my-4")
                
                # Add New Account button
                ui.button(
                    "Add New Gmail Account", 
                    on_click=add_new_gmail_account
                ).props('color=positive full-width')
                
                # Reserved space for future configuration UI
                with ui.expansion("Future Configuration").classes("mt-8 w-full"):
                    ui.label("Space reserved for future configuration options")
        
        # Main chat area - takes remaining width
        with ui.column().classes('w-3/4 h-full p-4'):
            # Container for chat messages - most of the height
            chat_message_container = ui.scroll_area().classes(
                "w-full h-5/6 bg-gray-800 rounded-lg p-4"
            )
            
            # Input area fixed at bottom
            with ui.card().classes("w-full mt-4"):
                with ui.row().classes("w-full items-center"):
                    # Input field
                    input_field = ui.textarea(
                        placeholder="Type your message...",
                    ).classes("w-full")
                    
                    # Send button
                    send_button = ui.button(icon="send").props('color=primary')

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