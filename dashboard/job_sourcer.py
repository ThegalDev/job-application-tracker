import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import datetime
import os
import urllib3

# Suppress InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURATION ---
EMAIL_USER = "majekadegbeaminat85@gmail.com"
EMAIL_PASS = "dwtm skpy zfge zhoy"  # App Password
USER_EMAIL = "majekadegbeaminat85@gmail.com"

# --- SCRAPERS ---

def scrape_python_org():
    """Scrapes Python.org for jobs matching keywords."""
    print("Scanning Python.org...")
    jobs = []
    url = "https://www.python.org/jobs/"
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Python.org job list is in <ol class="list-recent-jobs">
        job_list = soup.find('ol', class_='list-recent-jobs')
        if job_list:
            for li in job_list.find_all('li'):
                h2 = li.find('h2')
                if h2:
                    link = h2.find('a')
                    title = link.text.strip()
                    job_url = "https://www.python.org" + link['href']
                    
                    # Check for keywords (Intern, Junior, Entry)
                    # Exclude Senior roles
                    keywords = ['intern', 'junior', 'entry', 'graduate', 'trainee']
                    excluded_keywords = ['senior', 'lead', 'principal', 'staff', 'architect', 'manager', 'head']
                    
                    title_lower = title.lower()
                    if any(k in title_lower for k in keywords) and not any(ex in title_lower for ex in excluded_keywords):
                        jobs.append({'source': 'Python.org', 'title': title, 'url': job_url})
    except Exception as e:
        print(f"Error scraping Python.org: {e}")
    
    return jobs

def scrape_academic_positions():
    """Scrapes AcademicPositions.com for PhDs in Social Science/AI."""
    print("Scanning AcademicPositions...")
    jobs = []
    # Search for "AI HR" or "Artificial Intelligence Human Resources"
    url = "https://academicpositions.com/jobs?q=Artificial+Intelligence+Human+Resources&type=phd"
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, verify=False)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # This selector might need adjustment based on their current layout
        # Looking for article or div with job info
        # Generic fallback: look for links containing "PhD" and "Social"
        
        for link in soup.find_all('a', href=True):
            title = link.get_text().strip()
            if "PhD" in title:
                full_url = "https://academicpositions.com" + link['href'] if link['href'].startswith('/') else link['href']
                jobs.append({'source': 'AcademicPositions', 'title': title, 'url': full_url})
                
    except Exception as e:
        print(f"Error scraping AcademicPositions: {e}")

    return jobs[:10] # Limit to top 10

# --- EMAILER ---

def send_email(jobs):
    if not jobs:
        print("No new jobs found matching criteria.")
        return

    print(f"Found {len(jobs)} jobs. Sending email...")
    
    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = USER_EMAIL
    msg['Subject'] = f"Job Sourcer Summary - {datetime.date.today()}"

    body = "<h2>Job Sourcer Daily Summary</h2><ul>"
    for job in jobs:
        body += f"<li><b>[{job['source']}]</b> <a href='{job['url']}'>{job['title']}</a></li>"
    body += "</ul>"

    msg.attach(MIMEText(body, 'html'))

    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Failed to send email: {e}")

# --- MAIN ---

import time

if __name__ == "__main__":
    print("Starting Job Sourcer (Runs every 24 hours)...")
    
    while True:
        print(f"\n--- Running Sourcing Cycle: {datetime.datetime.now()} ---")
        all_jobs = []
        all_jobs.extend(scrape_python_org())
        all_jobs.extend(scrape_academic_positions())
        
        send_email(all_jobs)
        
        print("Cycle complete. Sleeping for 24 hours...")
        time.sleep(86400) # Sleep for 24 hours (60 * 60 * 24)
