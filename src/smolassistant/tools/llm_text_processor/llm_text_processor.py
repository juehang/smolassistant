from smolagents import tool
from typing import Optional, Callable
from litellm import completion

def process_text_tool(config):
    """
    Create a tool for processing text using the configured LLM.
    
    Args:
        config: The application config instance
        
    Returns:
        A tool function that processes text and a summarize_text function
    """
    def summarize_text(text: str, custom_prompt: Optional[str] = None) -> str:
        """
        Summarize text using the configured LLM.
        
        Args:
            text: The text to summarize
            custom_prompt: Optional custom prompt to override the default
            
        Returns:
            Summarized text, or original text if summarization fails
        """
        model_name = config.config.get(
            'text_processor', {}).get('model', 'anthropic/claude-3-haiku-20240307')
        
        prompt = custom_prompt or config.config.get(
            'text_processor', {}).get('summary_prompt', 
            "Summarize the following text. Preserve key information while being concise.")
        
        try:
            # Prepare the message in the format expected by litellm
            messages = [
                {"role": "user", "content": f"{prompt}\n\nText to summarize:\n{text}"}
            ]
            
            # Call the LLM using litellm directly
            response = completion(
                model=model_name,
                messages=messages,
                api_key=config.config['api_key']
            )
            
            # Extract the response content
            return response.choices[0].message.content.strip()
        except Exception as e:
            # Return the error message to let the agent handle it
            return f"Error summarizing text: {str(e)}"
    
    @tool
    def process_text(text: str, summarize: bool = True, custom_instructions: str = None) -> str:
        """
        Process text using the configured LLM. Can summarize or follow custom instructions.
        
        Args:
            text: The text to process
            summarize: Whether to summarize the text (default: True)
            custom_instructions: Optional custom instructions for text processing
            
        Returns:
            Processed text
        """
        if not summarize:
            return text
            
        return summarize_text(text, custom_prompt=custom_instructions)
    
    # Return both the tool and the summarize_text function so it can be reused
    return process_text, summarize_text
