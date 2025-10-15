import json, os
from datetime import datetime

def save_log(user, to, subject):
    log_dir = "data/logs"
    os.makedirs(log_dir, exist_ok=True)
    entry = {"to": to, "subject": subject, "timestamp": str(datetime.now())}
    path = f"{log_dir}/{user.replace('@', '_')}.json"
    data = []
    if os.path.exists(path):
        with open(path, 'r') as f:
            data = json.load(f)
    data.append(entry)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
