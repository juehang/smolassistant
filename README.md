# SmolAssistant

An agentic AI assistant based on the smolagents library.

## Features

- Interactive chat interface with a powerful AI assistant
- Built on smolagents, supporting Python code execution
- Web search capabilities
- Reminder functionality
- Gmail integration
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

These instructions will be appended to the default system prompt used by the agent, giving you control over the assistant's behavior without modifying the codebase.