import os
import queue

from nicegui import run, ui, app
from smolagents import CodeAgent, DuckDuckGoSearchTool, LiteLLMModel
# Removed unused imports since we're not displaying memory steps for now
from .config import ConfigManager, config_dir
from .tools.reminder import (
    set_reminder_tool, get_reminders_tool, cancel_reminder_tool
)
from .tools.reminder.service import ReminderService
from .tools.gmail import (
    get_unread_emails_tool, search_emails_tool, initialize_gmail_auth
)


async def process_message(message, agent, container):
    # Process the message and get the response
    # Display the user message in the chat container
    with container:
        ui.chat_message(text=message, name='You', sent=True)
    response = await run.io_bound(agent.run, message, reset=False)
    # Display the response in the chat container
    with container:
        ui.chat_message(text=response, name='Assistant', sent=False)
    return response


async def process_queue(message_queue, agent, container):
    # Check if there are messages in the queue
    if not message_queue.empty():
        # Process all messages in the queue
        while not message_queue.empty():
            # Get the next message from the queue
            message = message_queue.get()
            # Process the message
            await process_message(message, agent, container)


async def send_message(message_queue, message, agent, container):
    message_queue.put(message)
    await process_queue(message_queue, agent, container)


# Setup Gmail auth function
async def setup_gmail_auth():
    # Use run.io_bound to prevent blocking the UI
    result = await run.io_bound(initialize_gmail_auth)
    # Display result to user
    ui.notify(result)


def main(config: ConfigManager):
    """Entry point for the assistant with GUI"""
    # Create a queue for all messages (both user input and reminders)
    message_queue = queue.Queue()
    
    # Initialize ReminderService for thread management
    reminder_service = ReminderService(
        db_path=os.path.join(config_dir, "reminders.sqlite"),
        reminder_queue=message_queue
    )
    reminder_service.start()
    
    # Create the agent
    model = LiteLLMModel(
        model_id=config.config['model'],
        api_key=config.config['api_key'],
    )
    
    # Initialize tools
    def reminder_callback(msg):
        message_queue.put(msg)
    
    tools = [
        DuckDuckGoSearchTool(),
        set_reminder_tool(reminder_callback),
        get_reminders_tool(),
        cancel_reminder_tool(),
        get_unread_emails_tool(),
        search_emails_tool()
    ]
    
    # Create agent
    agent = CodeAgent(
        tools=tools,
        model=model,
        planning_interval=3
    )
    
    # Check if Telegram is enabled
    telegram_enabled = config.config.get('telegram', {}).get('enabled', False)
    telegram_token = config.config.get('telegram', {}).get('token', '')
    # import pdb; pdb.set_trace()
    # Initialize and start Telegram bot if enabled
    if telegram_enabled and telegram_token:
        print('Telegram bot is enabled.')

    # Create the UI with dark theme
    ui.dark_mode().enable()
    
    chat_container = ui.column().classes(
        'grid grid-cols-3 grid-rows-5 w-full h-full'
    )
    with chat_container:
        chat_message_container = ui.scroll_area().classes(
            'bg-black border border-cyan-950 rounded-lg '
            'col-start-2 min-h-[70vh]'
        )
        
        # Add Gmail API setup button
        with ui.card().classes(
            'bg-black border border-cyan-950 rounded-lg col-start-1'
        ):
            ui.button('Setup Gmail API', on_click=setup_gmail_auth)
        
        with ui.card().classes(
            'bg-black border border-cyan-950 rounded-lg '
            'col-start-2 min-h-[15vh]'
        ):
            input_field = ui.textarea(
                placeholder='Type your message...'
            ).classes('w-full h-full bg-black text-white')
    # Start the UI
    ui.run(
        title="SmolAssistant",
        favicon="🤖",
    )

    input_field.on(
        'keydown.enter',
        lambda: send_message(
            message_queue, input_field.value, agent, chat_message_container
        )
    )

    ui.timer(
        1.0,
        lambda: process_queue(message_queue, agent, chat_message_container)
    )


if __name__ in {"__main__", "__mp_main__", "smolassistant.__main__"}:
    try:
        config = ConfigManager()
        main(config)
    except Exception as e:
        print(f"Fatal error: {str(e)}")
