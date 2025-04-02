import threading
import telebot


def create_telegram_bot(message_queue, token, config, authorized_user_id=None):
    """
    Create and configure a Telegram bot that communicates with the agent
    via the message queue.
    
    Args:
        message_queue: Queue for sending/receiving messages to/from the agent
        token: Telegram bot token
        authorized_user_id: ID of the authorized Telegram user (if any)
        
    Returns:
        tuple: (bot, callback_function) where:
            - bot: Configured TeleBot instance
            - callback_function: Function to send responses
    """
    bot = telebot.TeleBot(token, parse_mode="html")
    
    # Track the authorized user ID
    _authorized_user_id = authorized_user_id
    
    def is_authorized(user_id):
        """
        Check if a user is authorized to use the bot
        
        Args:
            user_id: Telegram user ID to check
            
        Returns:
            bool: True if authorized, False otherwise
        """
        nonlocal _authorized_user_id
        
        # If no authorized user is set yet, authorize the first user
        if _authorized_user_id is None:
            _authorized_user_id = user_id
            # Save to config
            config.config['telegram']['authorized_user_id'] = user_id
            config.save()
            print(f"Authorized first Telegram user with ID: {user_id}")
            return True
        
        # Check if this is the authorized user
        if user_id == _authorized_user_id:
            return True
        
        # Unauthorized user
        bot.send_message(
            user_id,
            "Sorry, you are not authorized to use this bot."
        )
        print(f"Rejected unauthorized Telegram user with ID: {user_id}")
        return False
    
    # Handle '/start' and '/help' commands
    @bot.message_handler(commands=['start', 'help'])
    def send_welcome(message):
        # Check authorization
        if not is_authorized(message.from_user.id):
            return
        
        bot.reply_to(
            message,
            "Hello! I'm SmolAssistant. You can chat with me directly."
        )
    
    # Handle all other messages
    @bot.message_handler(func=lambda message: True)
    def handle_message(message):
        # Check authorization
        if not is_authorized(message.from_user.id):
            return
        
        # Forward message to agent via queue
        print(f"Received message from Telegram: {message.text}")
        message_queue.put(message.text)
    
    # Function to send responses back to the user
    def send_response(response):
        """
        Send a response back to the authorized user
        
        Args:
            response: The text response to send
        """
        nonlocal _authorized_user_id
        if _authorized_user_id:
            try:
                bot.send_message(_authorized_user_id, response)
                print(f"Sent response to Telegram user: {response[:50]}...")
            except Exception as e:
                print(f"Error sending message to Telegram: {str(e)}")
    
    return bot, send_response


def run_telegram_bot(bot):
    """
    Run the Telegram bot in a separate thread.
    
    Args:
        bot: Configured TeleBot instance
        
    Returns:
        The thread running the bot
    """
    def bot_polling():
        """Run the bot's polling loop"""
        print("Starting Telegram bot polling...")
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            print(f"Error in Telegram bot polling: {str(e)}")
    
    # Start the bot in a separate thread
    bot_thread = threading.Thread(target=bot_polling)
    bot_thread.daemon = True
    bot_thread.start()
    print("Telegram bot thread started")
    
    return bot_thread