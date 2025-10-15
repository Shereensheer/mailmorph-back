# import os
# import pickle
# from google_auth_oauthlib.flow import InstalledAppFlow
# from google.auth.transport.requests import Request
# from googleapiclient.discovery import build

# # Gmail send and read access
# SCOPES = [
#     "https://www.googleapis.com/auth/gmail.readonly",
#     "https://www.googleapis.com/auth/gmail.modify",
#     "https://www.googleapis.com/auth/gmail.send"
# ]

# def get_gmail_service():
#     creds = None
#     token_path = "token.pkl"

#     # Token file exists
#     if os.path.exists(token_path):
#         with open(token_path, "rb") as token:
#             creds = pickle.load(token)

#     # Token invalid or expired
#     if not creds or not creds.valid:
#         if creds and creds.expired and creds.refresh_token:
#             creds.refresh(Request())
#         else:
#             flow = InstalledAppFlow.from_client_secrets_file(
#                 "client_secret.json", SCOPES
#             )
#             creds = flow.run_local_server(port=0)
#         # Save token
#         with open(token_path, "wb") as token:
#             pickle.dump(creds, token)

#     try:
#         # Build Gmail service
#         service = build("gmail", "v1", credentials=creds)
#         return service
#     except Exception as e:
#         print(f"❌ Failed to create Gmail service: {e}")
#         return None




# services/gmail_auth.py
import os
import pickle
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

TOKEN_PATH = "token.pkl"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]

def get_gmail_service():
    """
    Return googleapiclient service or None if token not present/expired.
    """
    if not os.path.exists(TOKEN_PATH):
        return None
    try:
        with open(TOKEN_PATH, "rb") as f:
            creds = pickle.load(f)
        # creds may be google.oauth2.credentials.Credentials or oauthlib creds—handle both
        if isinstance(creds, Credentials):
            credentials = creds
        else:
            # if stored from google_auth_oauthlib.flow, it might be google.oauth2.credentials.Credentials pickled
            credentials = creds
        service = build("gmail", "v1", credentials=credentials)
        return service
    except Exception as e:
        print("Failed to load Gmail service:", e)
        return None
