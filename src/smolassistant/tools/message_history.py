"""
Message history tool for maintaining a list of recent user-assistant interactions.
"""
from collections import deque
from typing import List, Dict, Any, Callable

from smolagents import tool


class MessageHistory:
    """Stores a history of messages between the user and assistant."""

    def __init__(self, max_size: int = 20):
        """
        Initialize the message history.
        
        Args:
            max_size: Maximum number of messages to store (default: 20)
        """
        self.messages = deque(maxlen=max_size)
        self.max_size = max_size
    
    def add_message(self, role: str, content: str) -> None:
        """
        Add a message to the history.
        
        Args:
            role: The role of the message sender ("user" or "assistant")
            content: The content of the message
        """
        self.messages.append(f"{role.capitalize()}: {content}")
    
    def get_history(self) -> str:
        """
        Get the full message history as a formatted string.
        
        Returns:
            A string containing the message history
        """
        return "\n\n".join(self.messages)


def get_message_history_tool(history: MessageHistory) -> Dict[str, Any]:
    """
    Create a tool for accessing message history.
    
    Args:
        history: The MessageHistory instance to use
        
    Returns:
        A tool function decorated with @tool
    """
    @tool
    def get_message_history() -> str:
        """
        Get the history of recent messages between you and the user.
        """
        return history.get_history()
    
    return get_message_history
