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
    
    # Get paths from accounts
    for account in config.get("gmail", {}).get("accounts", []):
        name = account.get("name", "unnamed")
        token_path = os.path.join(config_dir, account.get("token_path"))
        paths.append((name, token_path))
    
    return paths


def get_credentials():
    """
    Get and refresh OAuth credentials for all configured accounts.
    
    Returns:
        List of valid OAuth credentials
    
    Raises:
        Exception: If no valid credentials are found
    """
    all_creds = []
    token_paths = get_token_paths()
    
    for account_name, token_path in token_paths:
        creds = None
        
        # Check if token exists
        if os.path.exists(token_path):
            try:
                creds = Credentials.from_authorized_user_file(
                    token_path, SCOPES
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
            "Gmail API authentication not set up. "
            "Please run the initialize_gmail_auth function first."
        )
    
    return all_creds


def initialize_gmail_auth(account_name=None, token_path=None):
    """
    Initialize the Gmail API authentication flow.
    
    Args:
        account_name: Name of the account to initialize
        token_path: Path to save the token (optional, will be generated from
                   account_name if not provided)
    
    Returns:
        A message indicating the result of the authentication process
    """
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
            for account in config.get("gmail", {}).get("accounts", []):
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
                    token_path, SCOPES
                )
                if creds and creds.valid:
                    return (
                        f"Gmail API authentication for {account_name} "
                        "is already set up."
                    )
            except Exception:
                # If there's an error loading the token, continue with the
                # auth flow
                pass
        
        # If no valid token exists, start the auth flow
        flow = InstalledAppFlow.from_client_secrets_file(cred_path, SCOPES)
        creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        os.makedirs(os.path.dirname(token_path), exist_ok=True)
        with open(token_path, "w") as token:
            token.write(creds.to_json())
        return (
            f"Gmail API authentication for {account_name} "
            "has been successfully set up."
        )
    except Exception as e:
        return f"Error setting up Gmail API authentication: {str(e)}"


def initialize_all_gmail_auth():
    """
    Initialize all Gmail accounts.
    
    Returns:
        A message indicating the result of the authentication process
    """
    token_paths = get_token_paths()
    
    if not token_paths:
        print("No Gmail accounts configured.")
        return (
            "No Gmail accounts configured. "
            "Please add accounts to your config file."
        )
    print(
        f"Starting authentication process for {len(token_paths)} "
        f"Gmail accounts:"
    )
    for i, (account_name, _) in enumerate(token_paths, 1):
        print(f"  {i}. {account_name}")
    
    results = ["Starting authentication process for all accounts:"]
    
    # Initialize all accounts
    for i, (account_name, token_path) in enumerate(token_paths, 1):
        results.append(
            f"Account {i} of {len(token_paths)} ({account_name}): "
            f"{initialize_gmail_auth(account_name, token_path)}"
        )
    
    return "\n".join(results)


def add_gmail_account(name):
    """
    Add a new Gmail account to the configuration.
    
    Args:
        name: Name of the account
    
    Returns:
        A message indicating the result
    """
    try:
        config = ConfigManager()
        
        # Ensure gmail section exists
        if "gmail" not in config.config:
            config.config["gmail"] = {}
        
        # Ensure accounts list exists
        if "accounts" not in config.config["gmail"]:
            config.config["gmail"]["accounts"] = []
        
        # Check if account with this name already exists
        for account in config.config["gmail"]["accounts"]:
            if account.get("name") == name:
                return f"Account with name '{name}' already exists."
        
        # Generate token path from account name
        token_filename = get_token_path_for_account(name)
        
        # Add new account
        config.config["gmail"]["accounts"].append({
            "name": name,
            "token_path": token_filename
        })
        
        # Save config
        config.save()
        
        return f"Added new Gmail account '{name}' to configuration."
    except Exception as e:
        return f"Error adding Gmail account: {str(e)}"