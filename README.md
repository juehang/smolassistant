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
- Telemetry integration using OpenTelemetry and Phoenix

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
| user.location | User's physical location | "Houston, TX" |
| user.timezone | User's timezone in IANA format | "America/Chicago" |
| text_processor.model | Model to use for summarization | "anthropic/claude-3-haiku-20240307" |
| text_processor.summary_prompt | Prompt for summarization | *Default instructions for summarizing with key information preservation* |
| telemetry.enabled | Enable/disable telemetry | true |

### Telemetry Integration

SmolAssistant includes telemetry integration using OpenTelemetry and Phoenix. This feature allows you to:

- Monitor and debug agent runs
- Analyze the steps and decisions made by the agent
- Visualize the agent's workflow

To access the telemetry dashboard, click the "Open Telemetry Dashboard" button in the sidebar. This will open Phoenix at `http://0.0.0.0:6006` where you can inspect your agent runs. Note that Phoenix needs to be run separately, via
```
python -m phoenix.server.main serve
```

You can enable or disable telemetry in the configuration file:

```toml
[telemetry]
enabled = true  # Set to false to disable telemetry
```

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

### User Location and Timezone Configuration

The assistant can be configured with your location and timezone information, which helps it provide more contextually relevant responses. This is configured in the `user` section:

```toml
[user]
location = "Houston, TX"
timezone = "America/Chicago"
```

This information is automatically added to the system prompt through a template mechanism. The `additional_system_prompt` field contains placeholders that are replaced with your actual location and timezone values:

```toml
additional_system_prompt = """
...existing prompt content...
The user is located in {user_location} (timezone: {user_timezone}).
"""
```

You can customize both the location and timezone to your preferences.

## Google Calendar Integration

SmolAssistant includes tools for accessing and searching Google Calendar events:

- **get_upcoming_events**: Retrieves events for a specified number of days
- **search_calendar_events**: Searches for events matching specific criteria

### Timezone Display

The Calendar integration displays timezone information for events, helping you better understand when events occur. For example:

- Timed events show their associated timezone: "7:30 PM-8:30 PM (tzfile('UTC'))"
- All-day events display as "All day" without timezone information

This feature ensures you have accurate time context for your calendar events, especially when dealing with events across different timezones.

## Reminder Functionality

SmolAssistant supports both one-time and recurring reminders. You can ask the assistant to:
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