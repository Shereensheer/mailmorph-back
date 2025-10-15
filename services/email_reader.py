# services/email_reader.py
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import base64
import email

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_gmail_service():
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    return build('gmail', 'v1', credentials=creds)

def get_replies():
    service = get_gmail_service()
    results = service.users().messages().list(userId='me', q="in:inbox newer_than:7d").execute()
    messages = results.get('messages', [])

    replies = []
    for msg in messages:
        msg_data = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
        headers = msg_data['payload']['headers']
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
        from_email = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
        snippet = msg_data.get('snippet', '')

        replies.append({
            'from': from_email,
            'subject': subject,
            'snippet': snippet
        })

    return replies
