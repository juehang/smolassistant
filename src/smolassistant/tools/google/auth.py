import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from ...config import ConfigManager, config_dir

# Define scopes for different Google services
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def get_credentials_path():
    """Get the path to the credentials.json file."""
    config = ConfigManager().config
    return os.path.join(
        config_dir, 
        config.get("google", {}).get("credentials_path", "credentials.json")
    )


def get_token_path_for_account(account_name):
    """
    Generate a token path for an account based on its name.
    
    Args:
        account_name: Name of the account
        
    Returns:
        Token path for the account
    """
    # Convert account name to a safe filename
    safe_name = account_name.lower().replace(" ", "_")
    return f"token_{safe_name}.json"


def get_token_paths():
    """
    Get all token paths from the configuration.
    Returns a list of tuples (account_name, token_path).
    """
    config = ConfigManager().config
    paths = []
    
    # Check for both old 'gmail' and new 'google' config sections
    accounts_section = config.get("google", {}).get("accounts", [])
    if not accounts_section:
        accounts_section = config.get("gmail", {}).get("accounts", [])
    
    # Get paths from accounts
    for account in accounts_section:
        name = account.get("name", "unnamed")
        token_path = os.path.join(config_dir, account.get("token_path"))
        paths.append((name, token_path))
    
    return paths


def get_credentials(scopes=None):
    """
    Get and refresh OAuth credentials for all configured accounts.
    
    Args:
        scopes: List of OAuth scopes to request, defaults to GMAIL_SCOPES if None
    
    Returns:
        List of valid OAuth credentials
    
    Raises:
        Exception: If no valid credentials are found
    """
    if scopes is None:
        scopes = GMAIL_SCOPES
        
    all_creds = []
    token_paths = get_token_paths()
    
    for account_name, token_path in token_paths:
        creds = None
        
        # Check if token exists
        if os.path.exists(token_path):
            try:
                creds = Credentials.from_authorized_user_file(
                    token_path, scopes
                )
                
                # If credentials are expired but can be refreshed
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    # Save refreshed token
                    with open(token_path, "w") as token:
                        token.write(creds.to_json())
                
                # Add valid credentials to the list
                if creds and creds.valid:
                    all_creds.append(creds)
            except Exception as e:
                print(
                    f"Error loading credentials for {account_name}: {str(e)}"
                )
    
    # If no valid credentials found, raise exception
    if not all_creds:
        raise Exception(
            "Google API authentication not set up. "
            "Please run the initialize_google_auth function first."
        )
    
    return all_creds


def initialize_google_auth(account_name=None, token_path=None, scopes=None):
    """
    Initialize the Google API authentication flow.
    
    Args:
        account_name: Name of the account to initialize
        token_path: Path to save the token (optional, will be generated from
                   account_name if not provided)
        scopes: List of OAuth scopes to request, defaults to GMAIL_SCOPES if None
        
    Returns:
        A message indicating the result of the authentication process
    """
    if scopes is None:
        scopes = GMAIL_SCOPES
        
    try:
        cred_path = get_credentials_path()
        
        if not os.path.exists(cred_path):
            return (
                f"Credentials file not found at {cred_path}. "
                "Please download the OAuth credentials file from "
                "Google Cloud Console "
                "and save it to this location."
            )
        
        # If token path is not provided, check if it's a known account
        if token_path is None and account_name is not None:
            config = ConfigManager().config
            # Check both 'google' and 'gmail' sections
            accounts_section = config.get("google", {}).get("accounts", [])
            if not accounts_section:
                accounts_section = config.get("gmail", {}).get("accounts", [])
                
            for account in accounts_section:
                if account.get("name") == account_name:
                    token_path = os.path.join(
                        config_dir, account.get("token_path")
                    )
                    break
            
            # If still no token path, generate one from the account name
            if token_path is None:
                token_filename = get_token_path_for_account(account_name)
                token_path = os.path.join(config_dir, token_filename)
        
        # If still no token path, return error
        if token_path is None:
            return "No account name provided for authentication"
        
        # Check if token already exists and is valid
        if os.path.exists(token_path):
            try:
                creds = Credentials.from_authorized_user_file(
                    token_path, scopes
                )
                if creds and creds.valid:
                    service_names = []
                    if 'gmail.readonly' in ' '.join(scopes):
                        service_names.append('Gmail')
                    if 'calendar.readonly' in ' '.join(scopes):
                        service_names.append('Calendar')
                    service_str = ' and '.join(service_names)
                    return (
                        f"Google {service_str} API authentication for {account_name} "
                        "is already set up."
                    )
            except Exception:
                # If there's an error loading the token, continue with the
                # auth flow
                pass
        
        # If no valid token exists, start the auth flow
        flow = InstalledAppFlow.from_client_secrets_file(cred_path, scopes)
        creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        os.makedirs(os.path.dirname(token_path), exist_ok=True)
        with open(token_path, "w") as token:
            token.write(creds.to_json())
        
        service_names = []
        if 'gmail.readonly' in ' '.join(scopes):
            service_names.append('Gmail')
        if 'calendar.readonly' in ' '.join(scopes):
            service_names.append('Calendar')
        service_str = ' and '.join(service_names)
        return (
            f"Google {service_str} API authentication for {account_name} "
            "has been successfully set up."
        )
    except Exception as e:
        return f"Error setting up Google API authentication: {str(e)}"


def initialize_all_google_auth(scopes=None):
    """
    Initialize all Google accounts.
    
    Args:
        scopes: List of OAuth scopes to request, defaults to GMAIL_SCOPES if None
        
    Returns:
        A message indicating the result of the authentication process
    """
    if scopes is None:
        scopes = GMAIL_SCOPES + CALENDAR_SCOPES
        
    token_paths = get_token_paths()
    
    if not token_paths:
        print("No Google accounts configured.")
        return (
            "No Google accounts configured. "
            "Please add accounts to your config file."
        )
    
    service_names = []
    if any('gmail.readonly' in scope for scope in scopes):
        service_names.append('Gmail')
    if any('calendar.readonly' in scope for scope in scopes):
        service_names.append('Calendar')
    service_str = ' and '.join(service_names)
    
    print(
        f"Starting {service_str} authentication process for {len(token_paths)} "
        f"Google accounts:"
    )
    for i, (account_name, _) in enumerate(token_paths, 1):
        print(f"  {i}. {account_name}")
    
    results = [f"Starting {service_str} authentication process for all accounts:"]
    
    # Initialize all accounts
    for i, (account_name, token_path) in enumerate(token_paths, 1):
        results.append(
            f"Account {i} of {len(token_paths)} ({account_name}): "
            f"{initialize_google_auth(account_name, token_path, scopes)}"
        )
    
    return "\n".join(results)


def add_google_account(name):
    """
    Add a new Google account to the configuration.
    
    Args:
        name: Name of the account
    
    Returns:
        A message indicating the result
    """
    try:
        config = ConfigManager()
        
        # Ensure google section exists
        if "google" not in config.config:
            # Check if 'gmail' section exists and migrate settings
            if "gmail" in config.config:
                config.config["google"] = config.config["gmail"].copy()
            else:
                config.config["google"] = {}
        
        # Ensure accounts list exists
        if "accounts" not in config.config["google"]:
            config.config["google"]["accounts"] = []
        
        # Check if account with this name already exists
        for account in config.config["google"]["accounts"]:
            if account.get("name") == name:
                return f"Account with name '{name}' already exists."
        
        # Generate token path from account name
        token_filename = get_token_path_for_account(name)
        
        # Add new account
        config.config["google"]["accounts"].append({
            "name": name,
            "token_path": token_filename
        })
        
        # Save config
        config.save()
        
        return f"Added new Google account '{name}' to configuration."
    except Exception as e:
        return f"Error adding Google account: {str(e)}"


# Add functions to initialize Gmail, Calendar, or both
def initialize_gmail_auth(account_name=None, token_path=None):
    """
    Initialize the Gmail API authentication flow.
    
    Args:
        account_name: Name of the account to initialize
        token_path: Path to save the token (optional)
        
    Returns:
        Result message from initialize_google_auth
    """
    return initialize_google_auth(account_name, token_path, GMAIL_SCOPES)


def initialize_calendar_auth(account_name=None, token_path=None):
    """
    Initialize the Calendar API authentication flow.
    
    Args:
        account_name: Name of the account to initialize
        token_path: Path to save the token (optional)
        
    Returns:
        Result message from initialize_google_auth
    """
    return initialize_google_auth(account_name, token_path, CALENDAR_SCOPES)


def initialize_all_gmail_auth():
    """
    Initialize Gmail API for all accounts.
    
    Returns:
        Result message from initialize_all_google_auth
    """
    return initialize_all_google_auth(GMAIL_SCOPES)


def initialize_all_calendar_auth():
    """
    Initialize Calendar API for all accounts.
    
    Returns:
        Result message from initialize_all_google_auth
    """
    return initialize_all_google_auth(CALENDAR_SCOPES)
