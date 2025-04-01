from datetime import datetime, timedelta
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from smolagents import tool

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


def format_email_results(service, messages):
    """
    Format email results into a readable string.
    
    Args:
        service: Gmail API service instance
        messages: List of message objects from Gmail API
        
    Returns:
        Formatted string with email details
    """
    if not messages:
        return "No emails found."
    
    result = f"Found {len(messages)} emails:\n\n"
    
    for i, msg in enumerate(messages[:10], 1):  # Limit to 10 emails
        try:
            # Get the message details
            message = service.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["Subject", "From", "Date"]
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
            
            # Add to result
            result += f"{i}. Subject: {subject}\n"
            result += f"   From: {sender}\n"
            result += f"   Date: {date}\n"
            result += f"   ID: {msg['id']}\n\n"
        except HttpError as error:
            result += f"{i}. Error retrieving email: {str(error)}\n\n"
    
    if len(messages) > 10:
        result += f"... and {len(messages) - 10} more emails."
    
    return result


def get_unread_emails_tool():
    """
    Create a tool for getting unread emails.
    """
    @tool
    def get_unread_emails(days: int = 7) -> str:
        """
        Get unread emails from the last specified number of days.
        
        Args:
            days: Number of days to look back for unread emails (default: 7)
        """
        try:
            # Get credentials
            creds = get_credentials()
            
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
            
            # Format and return the results
            return format_email_results(service, messages)
        except Exception as e:
            if "authentication not set up" in str(e):
                return (
                    "Gmail API authentication not set up. "
                    "Please use the initialize_gmail_auth function first."
                )
            return f"Error fetching unread emails: {str(e)}"
    
    return get_unread_emails


def search_emails_tool():
    """
    Create a tool for searching emails.
    """
    @tool
    def search_emails(query: str, max_results: int = 10) -> str:
        """
        Search emails using Gmail's search syntax.
        
        Args:
            query: Search query using Gmail's search operators
            max_results: Maximum number of results to return (default: 10)
        """
        try:
            # Get credentials
            creds = get_credentials()
            
            # Build the Gmail API service
            service = build("gmail", "v1", credentials=creds)
            
            # Call the Gmail API
            results = service.users().messages().list(
                userId="me", q=query, maxResults=max_results
            ).execute()
            messages = results.get("messages", [])
            
            # Format and return the results
            return format_email_results(service, messages)
        except Exception as e:
            if "authentication not set up" in str(e):
                return (
                    "Gmail API authentication not set up. "
                    "Please use the initialize_gmail_auth function first."
                )
            return f"Error searching emails: {str(e)}"
    
    return search_emails