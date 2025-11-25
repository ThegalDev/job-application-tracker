import imaplib
import email
from email.header import decode_header
import time
import csv
import os
import requests
from datetime import datetime

# --- CONFIGURATION ---
EMAIL_USER = "majekadegbeaminat85@gmail.com"
EMAIL_PASS = "dwtm skpy zfge zhoy"
IMAP_SERVER = "imap.gmail.com"
CHECK_INTERVAL = 30  # Check every 30 seconds

DATA_FILE = "data/applications.csv"
API_URL = "http://localhost:8000/log"

def decode_str(s):
    if isinstance(s, bytes):
        return s.decode("utf-8", errors="ignore")
    return str(s)

def check_emails():
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_USER, EMAIL_PASS)

        # 1. Check INBOX for Responses
        mail.select("inbox")
        status, messages = mail.search(None, '(UNSEEN)')
        if status == "OK":
            for e_id in messages[0].split():
                process_inbox_email(mail, e_id)

        # 2. Check SENT for New Applications
        mail.select('"[Gmail]/Sent Mail"')
        status, messages = mail.search(None, 'ALL')
        if status == "OK":
            email_ids = messages[0].split()[-5:]
            for e_id in email_ids:
                process_sent_email(mail, e_id)

        mail.logout()
    except Exception as e:
        print(f"Error checking email: {e}")

def process_inbox_email(mail, e_id):
    try:
        _, msg_data = mail.fetch(e_id, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        subject, encoding = decode_header(msg["Subject"])[0]
        if isinstance(subject, bytes):
            subject = subject.decode(encoding if encoding else "utf-8")
        
        sender = msg.get("From")
        body = get_body(msg).lower()
        subject_lower = subject.lower()
        
        new_status = None
        
        # STRICTER RULES
        # Only mark Interview if explicitly in Subject OR specific phrases in Body
        if "interview" in subject_lower:
            new_status = "Interview"
        elif "invitation to interview" in body or "schedule an interview" in body or "interview availability" in body:
            new_status = "Interview"
        
        # Rejection is usually clearer
        elif "unfortunately" in body or "regret to inform" in body or "moved forward with other candidates" in body:
            new_status = "Rejected"
        
        elif "offer" in subject_lower:
            new_status = "Offer"

        if new_status:
            update_status(sender, subject, new_status)
    except Exception as e:
        print(f"Error processing inbox: {e}")

def process_sent_email(mail, e_id):
    try:
        _, msg_data = mail.fetch(e_id, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        
        # Safety Check for Subject
        if msg["Subject"] is None:
            print(f"Skipping email {e_id}: No Subject")
            return

        subject, encoding = decode_header(msg["Subject"])[0]
        if isinstance(subject, bytes):
            subject = subject.decode(encoding if encoding else "utf-8")
        
        # Safety Check for Recipient
        recipient = msg.get("To")
        if not recipient:
            recipient = "Unknown"
            
        print(f"Checking sent email: '{subject}' to '{recipient}'")
        
        keywords = ["application", "resume", "internship", "role", "position"]
        if any(k in subject.lower() for k in keywords):
            if not is_already_logged(recipient, subject):
                print(f"Found Sent Application: {subject} to {recipient}")
                
                company = "Unknown"
                if "@" in recipient:
                    try:
                        domain = recipient.split("@")[1]
                        company = domain.split(".")[0].capitalize()
                    except IndexError:
                        company = "Unknown"
                
                log_data = {
                    "company": company,
                    "role": subject,
                    "url": "Email Outreach",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "status": "Applied"
                }
                try:
                    requests.post(API_URL, json=log_data)
                except Exception as req_err:
                    print(f"Failed to log application: {req_err}")

    except Exception as e:
        print(f"Error processing sent email {e_id}: {e}")

def get_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(errors="ignore")
    
    payload = msg.get_payload(decode=True)
    if payload:
        return payload.decode(errors="ignore")
    return ""

def update_status(sender, subject, new_status):
    if not os.path.exists(DATA_FILE): return
    
    rows = []
    found = False
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            company = row["Company"].lower()
            # Check if Company Name is in the Sender Email or Subject
            # e.g. "Google" in "recruiting@google.com"
            if company and len(company) > 2 and (company in str(sender).lower() or company in str(subject).lower()):
                if row["Status"] == "Applied":
                    row["Status"] = new_status
                    found = True
                    print(f"Updated {row['Company']} to {new_status}")
            rows.append(row)
    
    if found:
        with open(DATA_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

def is_already_logged(recipient, subject):
    if not os.path.exists(DATA_FILE): return False
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["URL"] == "Email Outreach" and row["Role"] == subject:
                return True
    return False

if __name__ == "__main__":
    print("Starting Email Monitor (Stricter Mode)...")
    while True:
        check_emails()
        time.sleep(CHECK_INTERVAL)
