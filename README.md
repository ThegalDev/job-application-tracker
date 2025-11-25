# Job Manager — Dashboard

Summary
- Lightweight local job-application dashboard built with Flask plus background services for email monitoring and job sourcing. Data is persisted as CSV under dashboard/data/.

Repository location
- c:\Users\user\Desktop\Programming\Python\graph\job_manager\dashboard

Contents
- app.py — main Flask application and API
- server.py — alternate server runner (production/dev entry)
- email_monitor.py — background service to poll/parse job emails and append to CSV
- job_sourcer.py — background job-sourcing script (scrapers / aggregators)
- requirements.txt — Python dependencies
- test_api.py — lightweight API tests
- data/applications.csv — persisted job/application records (CSV)
- static/index.html — front-end UI
- __pycache__/ — compiled files

Quick start (Windows, PowerShell)
1. Open PowerShell and change to the dashboard folder:
   ```powershell
   cd 'c:\Users\user\Desktop\Programming\Python\graph\job_manager\dashboard'
   ```
2. Create and activate virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
3. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
4. Run the web app:
   ```powershell
   python app.py
   # or for server.py-based runner:
   python server.py
   ```
5. Open a browser at:
   - http://127.0.0.1:5000/ (or the host/port printed by the server)

Background services
- Email monitor:
  ```powershell
  python email_monitor.py
  ```
- Job sourcer:
  ```powershell
  python job_sourcer.py
  ```
Note: These scripts may require credentials or configuration. Inspect the top of each file to identify required environment variables or config values before running.

Data format
- Primary data file: data/applications.csv
- Recommended columns (typical tracker): id, company, role, date_applied, status, source, contact, notes
- Inspect the actual CSV header:
  ```powershell
  Get-Content .\data\applications.csv -TotalCount 2
  ```
- Concurrency: avoid multiple processes writing to the CSV simultaneously. Use file locking or single writer pattern if running services and the web app concurrently.

API (typical)
- The Flask app exposes routes to read/write application records. Common endpoints you may find or add:
  - GET /api/applications — list applications
  - GET /api/applications/<id> — retrieve single record
  - POST /api/applications — add new record (JSON or form)
  - PUT /api/applications/<id> — update record
  - DELETE /api/applications/<id> — remove record
- Check app.py for exact route names and payload formats.

Testing
- Run API tests:
  ```powershell
  python test_api.py
  ```
- Add tests next to code under test and run them inside the virtualenv.

Development notes
- Edit app.py to change endpoints and CSV read/write logic.
- Edit static/index.html for UI changes.
- Log output from services to troubleshoot (add or view logging calls).
- Secure credentials: do not hardcode secrets. Use environment variables:
  ```powershell
  $env:JOB_EMAIL_USER='user@example.com'
  $env:JOB_EMAIL_PASS='secret'
  ```
- If you change the CSV schema, update all readers/writers and tests.

Security & privacy
- Background monitors may access email or external sites. Do not commit credentials or personal data to version control.
- Respect third-party terms of service and rate limits when scraping or using APIs.

Contributing
- Create a branch per feature/fix.
- Run tests before committing.
- Document schema changes and configuration requirements.

Suggested next steps / TODO
- Add example .env or README section with required environment variables for email/API credentials.
- Add a small locking layer around CSV writes or migrate to a lightweight DB (SQLite) if concurrent access is expected.
- Expand test coverage for background services and edge cases for CSV schema migrations.

License
- No license file included. Add LICENSE to clarify reuse terms.

Contact
- Inspect code in this folder for the maintainer or open issues in your repo management system.// filepath: c:\Users\user\Desktop\Programming\Python\graph\job_manager\dashboard\README.md
# Job Manager — Dashboard

Summary
- Lightweight local job-application dashboard built with Flask plus background services for email monitoring and job sourcing. Data is persisted as CSV under dashboard/data/.

Repository location
- c:\Users\user\Desktop\Programming\Python\graph\job_manager\dashboard

Contents
- app.py — main Flask application and API
- server.py — alternate server runner (production/dev entry)
- email_monitor.py — background service to poll/parse job emails and append to CSV
- job_sourcer.py — background job-sourcing script (scrapers / aggregators)
- requirements.txt — Python dependencies
- test_api.py — lightweight API tests
- data/applications.csv — persisted job/application records (CSV)
- static/index.html — front-end UI
- __pycache__/ — compiled files

Quick start (Windows, PowerShell)
1. Open PowerShell and change to the dashboard folder:
   ```powershell
   cd 'c:\Users\user\Desktop\Programming\Python\graph\job_manager\dashboard'
   ```
2. Create and activate virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
3. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
4. Run the web app:
   ```powershell
   python app.py
   # or for server.py-based runner:
   python server.py
   ```
5. Open a browser at:
   - http://127.0.0.1:5000/ (or the host/port printed by the server)

Background services
- Email monitor:
  ```powershell
  python email_monitor.py
  ```
- Job sourcer:
  ```powershell
  python job_sourcer.py
  ```
Note: These scripts may require credentials or configuration. Inspect the top of each file to identify required environment variables or config values before running.

Data format
- Primary data file: data/applications.csv
- Recommended columns (typical tracker): id, company, role, date_applied, status, source, contact, notes
- Inspect the actual CSV header:
  ```powershell
  Get-Content .\data\applications.csv -TotalCount 2
  ```
- Concurrency: avoid multiple processes writing to the CSV simultaneously. Use file locking or single writer pattern if running services and the web app concurrently.

API (typical)
- The Flask app exposes routes to read/write application records. Common endpoints you may find or add:
  - GET /api/applications — list applications
  - GET /api/applications/<id> — retrieve single record
  - POST /api/applications — add new record (JSON or form)
  - PUT /api/applications/<id> — update record
  - DELETE /api/applications/<id> — remove record
- Check app.py for exact route names and payload formats.

Testing
- Run API tests:
  ```powershell
  python test_api.py
  ```
- Add tests next to code under test and run them inside the virtualenv.

Development notes
- Edit app.py to change endpoints and CSV read/write logic.
- Edit static/index.html for UI changes.
- Log output from services to troubleshoot (add or view logging calls).
- Secure credentials: do not hardcode secrets. Use environment variables:
  ```powershell
  $env:JOB_EMAIL_USER='user@example.com'
  $env:JOB_EMAIL_PASS='secret'
  ```
- If you change the CSV schema, update all readers/writers and tests.

Security & privacy
- Background monitors may access email or external sites. Do not commit credentials or personal data to version control.
- Respect third-party terms of service and rate limits when scraping or using APIs.

Contributing
- Create a branch per feature/fix.
- Run tests before committing.
- Document schema changes and configuration requirements.

Contact
- Inspect code in this folder for the maintainer or open issues in your repo management system.
