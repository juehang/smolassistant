import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from ...config import ConfigManager, config_dir

# Define the scopes required for Gmail API
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_credentials_path():
    """Get the path to the credentials.json file."""
    config = ConfigManager().config
    return os.path.join(
        config_dir, 
        config.get("gmail", {}).get("credentials_path", "credentials.json")
    )


def get_token_path():
    """Get the path to the token.json file."""
    config = ConfigManager().config
    return os.path.join(
        config_dir, 
        config.get("gmail", {}).get("token_path", "token.json")
    )


def get_credentials():
    """
    Get and refresh OAuth credentials.
    This function is used by the tools to get valid credentials.
    
    Returns:
        Valid OAuth credentials
    
    Raises:
        Exception: If authentication fails or needs to be initialized
    """
    creds = None
    
    # Check if token exists
    if os.path.exists(get_token_path()):
        creds = Credentials.from_authorized_user_file(get_token_path(), SCOPES)
    
    # If no credentials or invalid, raise exception
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Refresh token if expired
            creds.refresh(Request())
            # Save refreshed token
            with open(get_token_path(), "w") as token:
                token.write(creds.to_json())
        else:
            # Need to initialize auth
            raise Exception(
                "Gmail API authentication not set up. "
                "Please run the initialize_gmail_auth function first."
            )
    
    return creds


def initialize_gmail_auth():
    """
    Initialize the Gmail API authentication flow.
    This function should be called from the UI to set up authentication.
    
    Returns:
        A message indicating the result of the authentication process
    """
    try:
        # Check if token already exists
        if os.path.exists(get_token_path()):
            # Verify the token is valid
            token_path = get_token_path()
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            if creds and creds.valid:
                return "Gmail API authentication is already set up."
        
        # If no valid token exists, start the auth flow
        flow = InstalledAppFlow.from_client_secrets_file(
            get_credentials_path(), SCOPES
        )
        creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open(get_token_path(), "w") as token:
            token.write(creds.to_json())
        
        return "Gmail API authentication has been successfully set up."
    except Exception as e:
        return f"Error setting up Gmail API authentication: {str(e)}"