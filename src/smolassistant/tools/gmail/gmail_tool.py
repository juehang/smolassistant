from datetime import datetime, timedelta
import base64
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from smolagents import tool
from typing import Optional, Callable

from .auth import get_credentials


def calculate_date_range(days):
    """
    Calculate the date range for the query.
    
    Args:
        days: Number of days to look back
        
    Returns:
        Date string in Gmail's search format (YYYY/MM/DD)
    """
    date = datetime.now() - timedelta(days=days)
    return date.strftime("%Y/%m/%d")


def format_email_results(services_with_messages):
    """
    Format email results from multiple accounts into a readable string.
    
    Args:
        services_with_messages: List of tuples
                               (service, messages, account_index)
        
    Returns:
        Formatted string with email details
    """
    # Count total emails
    total_emails = sum(
        len(messages) for _, messages, _ in services_with_messages
    )
    
    if total_emails == 0:
        return "No emails found in any account."
    result = (
        f"Found {total_emails} emails across "
        f"{len(services_with_messages)} accounts:\n\n"
    )
    
    for service, messages, account_idx in services_with_messages:
        if not messages:
            continue
            
        result += f"Account {account_idx + 1}:\n"
        
        for i, msg in enumerate(messages, 1):
            try:
                # Get the full message details
                message = service.users().messages().get(
                    userId="me", id=msg["id"], format="full"
                ).execute()
                
                # Extract headers
                headers = message.get("payload", {}).get("headers", [])
                subject = next(
                    (h["value"] for h in headers if h["name"] == "Subject"),
                    "No subject"
                )
                sender = next(
                    (h["value"] for h in headers if h["name"] == "From"),
                    "Unknown sender"
                )
                date = next(
                    (h["value"] for h in headers if h["name"] == "Date"),
                    "Unknown date"
                )
                
                # Extract message body
                message_body = get_message_body(message)
                
                # Truncate message body if too long
                max_body_length = 500
                if len(message_body) > max_body_length:
                    message_body = (message_body[:max_body_length] +
                                    "... [truncated]")
                
                # Get attachments
                attachments = get_attachments(message)
                
                # Add to result
                result += f"  {i}. Subject: {subject}\n"
                result += f"     From: {sender}\n"
                result += f"     Date: {date}\n"
                result += f"     ID: {msg['id']}\n"
                
                # Add message body
                if message_body:
                    formatted_body = message_body.replace('\n', '\n     ')
                    result += f"\n     Message:\n     {formatted_body}\n"
                
                # Add attachments if any
                if attachments:
                    result += "\n     Attachments:\n"
                    for attachment in attachments:
                        result += f"     - {attachment}\n"
                
                result += "\n"
                
            except HttpError as error:
                result += f"  {i}. Error retrieving email: {str(error)}\n\n"
    
    return result


def get_message_body(message):
    """
    Extract the message body from a Gmail API message object.
    
    Args:
        message: Gmail API message object
        
    Returns:
        String containing the message body text
    """
    if not message:
        return ""
    
    def decode_base64url(data):
        """Decode base64url encoded string."""
        if not data:
            return ""
        # Add padding if needed
        padded = data + '=' * (4 - len(data) % 4) if len(data) % 4 else data
        try:
            return base64.urlsafe_b64decode(padded).decode('utf-8')
        except Exception:
            return "[Could not decode message]"
    
    def get_text_from_part(part):
        """Recursively extract text from message part."""
        if not part:
            return ""
            
        # Check for body data in this part
        if part.get("body") and part["body"].get("data"):
            if part.get("mimeType") == "text/plain":
                return decode_base64url(part["body"]["data"])
            elif part.get("mimeType") == "text/html":
                # Return HTML content (could convert to plain text if needed)
                return decode_base64url(part["body"]["data"])
        
        # If this part has subparts, process them
        if part.get("parts"):
            # Prioritize text/plain parts over text/html
            plain_text = ""
            html_text = ""
            
            for subpart in part["parts"]:
                if subpart.get("mimeType") == "text/plain":
                    plain_text = get_text_from_part(subpart)
                elif subpart.get("mimeType") == "text/html":
                    html_text = get_text_from_part(subpart)
                elif subpart.get("parts"):
                    # Recursively check deeper parts
                    subpart_text = get_text_from_part(subpart)
                    if subpart_text:
                        return subpart_text
            
            # Return plain text if available, otherwise HTML
            return plain_text or html_text
            
        return ""
    
    # Start with the main payload
    return get_text_from_part(message.get("payload", {}))


def get_attachments(message):
    """
    Extract attachment filenames from a Gmail API message object.
    
    Args:
        message: Gmail API message object
        
    Returns:
        List of attachment filenames
    """
    attachments = []
    
    def find_attachments(part):
        """Recursively find attachments in message parts."""
        if not part:
            return
            
        # Check if this part is an attachment
        if part.get("filename") and part.get("filename").strip():
            attachments.append(part.get("filename"))
            
        # Check subparts
        if part.get("parts"):
            for subpart in part["parts"]:
                find_attachments(subpart)
    
    # Start with the main payload
    if message and message.get("payload"):
        find_attachments(message["payload"])
        
    return attachments


def get_unread_emails_tool(summarize_func: Optional[Callable] = None):
    """
    Create a tool for getting unread emails from all accounts.
    
    Args:
        summarize_func: Optional function to summarize text
    """
    @tool
    def get_unread_emails(days: int = 2, summarize: bool = True) -> str:
        """
        Get unread emails from all accounts for the last specified
        number of days.
        Do not disable summarization unless you have a good reason to do so.
        
        Args:
            days: Number of days to look back for unread emails (default: 2)
            summarize: Whether to summarize the results (default: True)

        Returns:
           A string containing the unread emails from all accounts.
        """
        try:
            # Get credentials for all accounts
            all_creds = get_credentials()
            
            services_with_messages = []
            
            # Process each account
            for idx, creds in enumerate(all_creds):
                try:
                    # Build the Gmail API service
                    service = build("gmail", "v1", credentials=creds)
                    
                    # Calculate the date range
                    date_range = calculate_date_range(days)
                    
                    # Create the query
                    query = f"is:unread after:{date_range}"
                    
                    # Call the Gmail API
                    results = service.users().messages().list(
                        userId="me", q=query
                    ).execute()
                    messages = results.get("messages", [])
                    
                    # Add to the list
                    services_with_messages.append((service, messages, idx))
                except Exception as e:
                    print(f"Error processing account {idx}: {str(e)}")
            
            # Format the results
            result = format_email_results(services_with_messages)
            
            # Summarize if requested and summarize_func is available
            if summarize and summarize_func:
                try:
                    result = summarize_func(result)
                except Exception as e:
                    # Add a note about summarization failure but return the original
                    result = f"Note: Summarization failed ({str(e)})\n\n{result}"
                
            return result
        except Exception as e:
            if "authentication not set up" in str(e):
                return (
                    "Gmail API authentication not set up. "
                    "Please use the initialize_gmail_auth function first."
                )
            return f"Error fetching unread emails: {str(e)}"
    
    return get_unread_emails


def search_emails_tool(summarize_func: Optional[Callable] = None):
    """
    Create a tool for searching emails across all accounts.
    Do not disable summarization unless you have a good reason to do so.
    
    Args:
        summarize_func: Optional function to summarize text
    """
    @tool
    def search_emails(query: str, max_results: int = 10, summarize: bool = True) -> str:
        """
        Search emails using Gmail's search syntax across all accounts.
        
        Args:
            query: Search query using Gmail's search operators
            max_results: Maximum number of results to return per account (default: 10)
            summarize: Whether to summarize the results (default: True)
        """
        try:
            # Get credentials for all accounts
            all_creds = get_credentials()
            
            services_with_messages = []
            
            # Process each account
            for idx, creds in enumerate(all_creds):
                try:
                    # Build the Gmail API service
                    service = build("gmail", "v1", credentials=creds)
                    
                    # Call the Gmail API
                    results = service.users().messages().list(
                        userId="me", q=query, maxResults=max_results
                    ).execute()
                    messages = results.get("messages", [])
                    
                    # Add to the list
                    services_with_messages.append((service, messages, idx))
                except Exception as e:
                    print(f"Error processing account {idx}: {str(e)}")
            
            # Format the results
            result = format_email_results(services_with_messages)
            
            # Summarize if requested and summarize_func is available
            if summarize and summarize_func:
                try:
                    result = summarize_func(result)
                except Exception as e:
                    # Add a note about summarization failure but return the original
                    result = f"Note: Summarization failed ({str(e)})\n\n{result}"
                
            return result
        except Exception as e:
            if "authentication not set up" in str(e):
                return (
                    "Gmail API authentication not set up. "
                    "Please use the initialize_gmail_auth function first."
                )
            return f"Error searching emails: {str(e)}"
    
    return search_emails