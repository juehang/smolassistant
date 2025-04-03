import os
import queue

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
        agent.run, message + "\n" + additional_instructions, reset=True
    )
    # Display the response in the chat container
    with container:
        ui.chat_message(
            text=response, name="Assistant", sent=False, text_html=True
        )

    # Add assistant response to history
    message_history.add_message("assistant", response)

    # If Telegram response callback is available, send the response there too
    if telegram_cb:
        telegram_cb(response)

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
    message_queue.put(message)
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
        "Check the console for progress."
    )

    # Use run.io_bound to prevent blocking the UI
    result = await run.io_bound(initialize_all_gmail_auth)

    # Display result to user
    ui.notify(result)


async def setup_specific_gmail_auth(account_info):
    """Initialize Gmail API authentication for a specific account."""
    if not account_info:
        return
    print(account_info)
    account_name, token_path = account_info

    # Use run.io_bound to prevent blocking the UI
    result = await run.io_bound(
        initialize_gmail_auth, account_name, token_path
    )
    # Display result to user
    ui.notify(result)


async def add_new_gmail_account():
    """Add a new Gmail account to the configuration."""
    # Create a dialog to get account details
    with ui.dialog() as dialog, ui.card():
        ui.label("Add New Gmail Account")
        name_input = ui.input("Account Name")

        async def submit():
            name = name_input.value

            if not name:
                ui.notify("Please enter an account name")
                return

            # Use run.io_bound to prevent blocking the UI
            result = await run.io_bound(add_gmail_account, name)
            ui.notify(result)
            dialog.close()

        ui.button("Add", on_click=submit)
        ui.button("Cancel", on_click=dialog.close)

    dialog.open()


def main(config: ConfigManager):
    """Entry point for the assistant with GUI"""
    # Create a queue for all messages (both user input and reminders)
    message_queue = queue.Queue()

    # Initialize the message history with max size from config
    message_history = MessageHistory(
        max_size=config.config.get("message_history", {}).get("max_size", 20)
    )

    # Get the database path from config
    db_path = config.config.get("reminders", {}).get("db_path", "reminders.sqlite")

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
        "authorized_user_id"
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

    chat_container = ui.column().classes(
        "grid grid-cols-3 grid-rows-5 w-full h-full"
    )
    with chat_container:
        chat_message_container = ui.scroll_area().classes(
            "bg-black border border-cyan-950 rounded-lg "
            "col-start-2 min-h-[65vh]"
        )

        # Add Gmail API setup buttons
        with ui.card().classes(
            "bg-black border border-cyan-950 rounded-lg col-start-1"
        ):
            ui.button("Setup All Gmail Accounts", on_click=setup_gmail_auth)

            # Create a dropdown for account selection
            accounts = config.config.get("gmail", {}).get("accounts", [])
            account_options = {}

            for account in accounts:
                name = account.get("name", "unnamed")
                token_path = os.path.join(
                    config_dir, account.get("token_path")
                )
                account_options[(name, token_path)] = name

            if account_options:
                ui.select(
                    options=account_options,
                    label="Select account to setup",
                    on_change=lambda e: setup_specific_gmail_auth(e.value),
                ).classes("w-64")

            # Add button to add a new account
            ui.button("Add New Gmail Account", on_click=add_new_gmail_account)

        with ui.card().classes(
            "bg-black border border-cyan-950 rounded-lg "
            "col-start-2 min-h-[20vh]"
        ):
            input_field = ui.textarea(
                placeholder="Type your message..."
            ).classes("w-full h-full bg-black text-white")

    input_field.on(
        "keydown.enter",
        lambda: send_message(
            message_queue,
            input_field.value,
            agent,
            chat_message_container,
            message_history,
            telegram_cb,
            additional_instructions=config.config["additional_instructions"],
        ),
    )

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
