# # services/email_storage.py
# import json
# import os

# STORAGE_FILE = "sent_emails.json"

# def save_email(entry):
#     if os.path.exists(STORAGE_FILE):
#         with open(STORAGE_FILE, "r") as f:
#             data = json.load(f)
#     else:
#         data = []

#     data.append(entry)

#     with open(STORAGE_FILE, "w") as f:
#         json.dump(data, f, indent=4)

# def load_emails():
#     if os.path.exists(STORAGE_FILE):
#         with open(STORAGE_FILE, "r") as f:
#             return json.load(f)
#     return []


import json
import os

STORAGE_FILE = "sent_emails.json"

def save_email(entry):
    if os.path.exists(STORAGE_FILE):
        with open(STORAGE_FILE, "r") as f:
            data = json.load(f)
    else:
        data = []

    # Ensure reply field exists
    entry.setdefault("replies", [])
    data.append(entry)

    with open(STORAGE_FILE, "w") as f:
        json.dump(data, f, indent=4)

def save_reply(sent_email_id, reply_entry):
    if os.path.exists(STORAGE_FILE):
        with open(STORAGE_FILE, "r") as f:
            data = json.load(f)
    else:
        data = []

    for email in data:
        if email.get("id") == sent_email_id:
            email.setdefault("replies", []).append(reply_entry)
            break

    with open(STORAGE_FILE, "w") as f:
        json.dump(data, f, indent=4)

def load_emails():
    if os.path.exists(STORAGE_FILE):
        with open(STORAGE_FILE, "r") as f:
            return json.load(f)
    return []


import os
import pickle

REPLIES_FILE = "replies.pkl"

def save_replies(replies: list):
    with open(REPLIES_FILE, "wb") as f:
        pickle.dump(replies, f)

def load_replies():
    if os.path.exists(REPLIES_FILE):
        with open(REPLIES_FILE, "rb") as f:
            return pickle.load(f)
    return []

# ✅ Fix: implement this missing function
def load_new_replies(thread_ids: list):
    """
    Return only new replies that match thread_ids.
    If no thread_ids are provided, return all replies.
    """
    all_replies = load_replies()
    if not thread_ids:
        return all_replies
    return [r for r in all_replies if r.get("threadId") not in thread_ids]

