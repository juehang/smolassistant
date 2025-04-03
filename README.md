# SmolAssistant

An agentic AI assistant based on the smolagents library.

## Features

- Interactive chat interface with a powerful AI assistant
- Built on smolagents, supporting Python code execution
- Web search capabilities
- Text processing and summarization using Claude 3.5 Haiku
- Reminder functionality (one-time and recurring)
- Gmail integration with automatic summarization
- Telegram bot support

## Configuration

SmolAssistant can be configured through a TOML configuration file located at:

```
~/.config/smolassistant/config.toml
```

### Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| model | Model identifier | "anthropic/claude-3-7-sonnet-latest" |
| api_key | API key for the LLM provider | "" |
| additional_instructions | Instructions appended to each user message | *Formatting instructions for HTML tags and general guidelines that need strict adherence* |
| additional_system_prompt | Custom text added to the system prompt | *Default instructions about being friendly, expressing confidence levels, and date/time handling* |
| text_processor.model | Model to use for summarization | "anthropic/claude-3-haiku-20240307" |
| text_processor.summary_prompt | Prompt for summarization | *Default instructions for summarizing with key information preservation* |

### Customizing the System Prompt

The `additional_system_prompt` allows you to add custom instructions to the assistant's system prompt. The default setting includes:

```toml
additional_system_prompt = """
Please ensure that your responses via the final answer function 
are friendly and helpful, and greet the user when appropriate!
If you are unsure about your answer, please include your confidence.
You do not know the current date or time; if you need this information, 
please use your coding capabilities to find it.
"""
```

You can modify this in your configuration file to customize the assistant's behavior:

```toml
additional_system_prompt = """
# Additional Custom Instructions
Your responses should be concise, helpful, and to the point. 
When providing code, include brief explanations of what the code does.
Always provide examples when explaining concepts.
"""
```

### Customizing Text Processing

The `text_processor` section allows you to customize how text is summarized:

```toml
[text_processor]
model = "anthropic/claude-3-haiku-20240307"
summary_prompt = """
Summarize the following text. Preserve key information 
while being concise. For emails, include sender, subject, and main points. 
For webpages, include main topics and key details. 
For attachments, mention types but not full filenames.
"""
```

## Reminder Functionality

SmolAssistant supports both one-time and recurring reminders. You can ask the assistant to:

- Set reminders for specific dates and times
- Create recurring reminders (daily, weekly, or at custom intervals)
- List all your pending reminders
- Cancel reminders when they're no longer needed

The assistant understands natural language requests for managing your reminders.

## Text Processing Functionality

SmolAssistant includes a text processing tool that can summarize large outputs. This functionality is:

- Used by default in email search and unread email tools
- Used by default in the webpage visit tool
- Available as a standalone tool for the agent to use on any text

You can toggle summarization on or off with a boolean parameter in the tool calls.