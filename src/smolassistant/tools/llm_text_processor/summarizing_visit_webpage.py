from smolagents import Tool
from typing import Optional, Callable

class SummarizingVisitWebpageTool(Tool):
    """
    A wrapper around VisitWebpageTool that adds summarization capability.
    """
    name = "visit_webpage"
    description = (
        "Visits a webpage at the given url and reads its content as a markdown string. "
        "Can optionally summarize the content."
        "Do not disable summarization unless you have a good reason to do so."
    )
    inputs = {
        "url": {
            "type": "string",
            "description": "The url of the webpage to visit.",
        },
        "summarize": {
            "type": "boolean",
            "description": "Whether to summarize the content.",
            "default": True,  # Default to True for summarization
            "nullable": True 
        }
    }
    output_type = "string"
    
    def __init__(self, max_output_length: int = 40000, summarize_func: Optional[Callable] = None):
        super().__init__()
        self.max_output_length = max_output_length
        self._original_tool = None
        self.summarize_func = summarize_func
        
    def _initialize_original_tool(self):
        """Initialize the original VisitWebpageTool on first use."""
        try:
            from smolagents import VisitWebpageTool
            self._original_tool = VisitWebpageTool(max_output_length=self.max_output_length)
        except ImportError as e:
            raise ImportError(
                "You must install the smolagents package to use this tool."
            ) from e
    
    def forward(self, url: str, summarize: bool = True) -> str:
        """
        Visit a webpage and optionally summarize its content.
        Do not disable summarization unless you have a good reason to do so.
        
        Args:
            url: The URL of the webpage to visit
            summarize: Whether to summarize the content (default: True)
            
        Returns:
            The webpage content, optionally summarized
        """
        if not self._original_tool:
            self._initialize_original_tool()
            
        # Get the original content
        content = self._original_tool.forward(url)
        
        # Return as is if summarization is not requested or no summarize function
        if not summarize or not self.summarize_func:
            return content
            
        # Summarize the content
        try:
            return self.summarize_func(content)
        except Exception as e:
            # Add a note about summarization failure but return the original
            return f"Note: Summarization failed ({str(e)})\n\n{content}"
