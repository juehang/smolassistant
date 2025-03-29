import os
import queue
from enum import Enum, auto

from smolagents import CodeAgent, DuckDuckGoSearchTool, LiteLLMModel
from .config import ConfigManager, config_dir
from .tools.reminder import (
    set_reminder_tool, get_reminders_tool, cancel_reminder_tool
)
from .tools.reminder.service import ReminderService


class MessageType(Enum):
    """Enum for message types in the queue"""
    USER_INPUT = auto()
    REMINDER = auto()


def main(config: ConfigManager):
    """Entry point for the assistant"""
    # Create the agent
    model = LiteLLMModel(
        model_id=config.config['model'],
        api_key=config.config['api_key'],
    )
    
    # Create a queue for all messages (both user input and reminders)
    message_queue = queue.Queue()
    
    # Define a callback function for reminders that adds to the queue
    def reminder_callback(message):
        # Add message to queue with type information (unused for now)
        message_queue.put((message, MessageType.REMINDER))
    
    # Initialize ReminderService for thread management
    reminder_service = ReminderService(
        db_path=os.path.join(config_dir, "reminders.sqlite"),
        reminder_queue=message_queue
    )
    reminder_service.start()
    
    # Initialize tools
    tools = [
        DuckDuckGoSearchTool(),
        set_reminder_tool(reminder_callback),
        get_reminders_tool(),
        cancel_reminder_tool()
    ]
    
    agent = CodeAgent(
        tools=tools,
        model=model,
        planning_interval=3
    )
    
    print("SmolAssistant is ready! Type 'exit' or 'quit' to exit.")
    print("Type 'pass' to check for messages in the queue without sending")
    print("input.")
    
    # Main processing loop
    while True:
        # Get user input (blocking)
        try:
            user_input = input("> ")
        except (KeyboardInterrupt, EOFError):
            # Handle Ctrl+C or Ctrl+D
            print("\nExiting...")
            break
            
        # Check for exit command
        if user_input.lower() in ["exit", "quit"]:
            break
            
        # Check for pass command - if not pass, add input to queue
        if user_input.lower() != "pass":
            # Add user input to the queue
            message_queue.put((user_input, MessageType.USER_INPUT))
        
        # Process all messages in the queue
        while not message_queue.empty():
            # Get the next message from the queue
            message, _ = message_queue.get()
            
            # Process the message with the agent
            output = agent.run(message)
            print(output)
    
    # Ensure ReminderService is properly shut down
    reminder_service.stop()
    print("SmolAssistant has been shut down.")


if __name__ in {"__main__", "__mp_main__"}:
    config = ConfigManager()
    main(config)
