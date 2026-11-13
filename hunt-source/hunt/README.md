> Current verified status: see ../HUNT-live-fix-status.md. Earlier descriptions below are historical where they conflict.

# HUNT — Aminat’s career workspace

Open the private phone dashboard: https://hunt-aminat-career-workspace.youremowriter.chatgpt.site

Sign in with the owner ChatGPT account. The console is private. It contains 72 preserved application records, verified evidence, job research and current drafts. No employer messages or applications have been sent.

## Test it step by step

1. Open Overview. Confirm 72 applications. “Salary-qualified priorities” can correctly be zero: HUNT blocks approval when pay is unknown or below $2,500/month.
2. Open Applications. Check Moniepoint People Business Partner, Ben Talent Acquisition Partner and Sieve Talent Ops show their verified rejections. micro1 HR & People Operations Expert remains AI interview completed.
3. Open Opportunities and review a role. Check its original employer link, location eligibility, compensation status, weighted score and evidence. AI relevance is labelled as inference.
4. Open Agents & schedule. Inspect the latest pipeline run: it read 40 recruiting messages and all 72 tracker records. A successful read is not a sent application.
5. To test discovery, choose Run the agent workflow. The phone console queues work for the Mac runner; queued means waiting, not completed. Keep this Mac and Codex available, then inspect the run result.
6. Open Application studio to read the current draft. Unknown compensation blocks approval. Rejecting or recording review does not send anything.
7. Open Reports & actions to inspect next actions and daily/weekly reports. Ambiguous mail events need review; HUNT does not silently guess their application.
8. Pause HUNT if needed. The phone pause is synced to the runner. Unpause to resume processing.

## What is automatic

Registered desktop operations run at 07:00, 08:00, 12:00, 16:00 and 18:00 Africa/Lagos; weekly review Friday 18:30. Future scheduled execution has not yet been observed. This Mac and Codex must be available. The current phone runner checks for commands about once a minute. Independent always-on cloud execution remains pending.

## Google and AI access

HUNT has its own authorized Google connection: recruitment Gmail read access and Google Sheets access. The adapter restricts spreadsheet operations to the specified application tracker. The first runtime reconciliation read 40 messages and preserved all 72 records, with zero Sheet writes. Sending is disabled and no Gmail send scope was granted.

The approved OpenAI integration uses only the eight verified work-experience excerpts and public job descriptions. API response storage is disabled. Keys, Google client secrets and refresh credentials remain outside this deliverable folder. Do not move the app without arranging its credentials securely.

## Local dashboard

Double-click Start HUNT.command. The private local dashboard opens at http://127.0.0.1:8765/. Keep its Terminal open. The phone dashboard is separately hosted; its worker does not run the Python agents itself.

## Verification and limits

174 local tests passed, including nine HTTP integration checks. Hosted access-control/storage tests passed. The latest private deployment succeeded. Browser review confirmed the overview loaded with 72 applications; the entire phone action journey is not yet fully verified.

Full PRD acceptance is pending: independent cloud execution, token lifecycle monitoring, continuous external tracker writes, remaining approved application/calendar adapters, notifications and outcome-learning verification. See HUNT-v2-status.md in the parent outputs folder for current acceptance status. Local records use restricted file permissions; the audit chain is verified but not externally anchored.

Developer verification: HUNT_HTTP_TESTS=1 python3 -m unittest discover -p 'test*.py'. Runtime data stays in data/. Keep all exports private.
