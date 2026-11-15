# Application runner setup

The desktop runner connects HUNT's exact reviewed Word CV to the application execution ledger and a public Lever form adapter. It is not an enabled autonomous cloud service. No real application has been submitted during verification.

## What is connected

- Owner-only `/api/application-context` supplies the selected job, package and document version without returning the full workspace.
- The downloaded CV must match both the package identity and document SHA-256. Files and review records are private on disk.
- A plan binds the complete inspected form, verified answers, attachment hashes and job/package versions.
- Approval and execution recheck pause, hidden status, current master CV, writing profile, job version, 48-hour freshness, remote eligibility, USD 2,500 monthly floor and duplicate application history.
- Before the final click, the browser reads back every filled answer and file hash again. A changed answer/file blocks submission.
- Inspection cannot POST application data. Filling cannot POST to the final application endpoint. Visible CAPTCHA/security challenges stop the adapter.
- Submission needs explicit positive employer confirmation. Interrupted or uncertain attempts are not automatically retried.

## Current limits

Only public Lever forms are supported. Greenhouse, Ashby and other providers are not implemented. Employer-page loading has not passed live verification on this Mac. There is no scheduled autonomous submission, cloud browser connection, owner web approval screen, or confirmed-form receipt reconciliation into the hosted tracker yet. Existing manual application and tracker actions remain available.

## Desktop commands

Run from the HUNT folder. Existing private owner credentials are read in memory from the same local HUNT runtime file; do not paste secrets into CLI arguments or chat. The runner uses the installed Playwright/Chrome runtime when available.

```sh
python3 application_runner.py inspect --job-id JOB_ID --package-id PACKAGE_ID
python3 application_runner.py plan --job-id JOB_ID --package-id PACKAGE_ID --answers-file PRIVATE_ANSWERS_JSON
python3 application_runner.py show --plan-id PLAN_ID
python3 application_runner.py approve --plan-id PLAN_ID --expected-hash EXACT_PLAN_HASH --actor OWNER_IDENTITY
python3 application_runner.py execute --plan-id PLAN_ID
```

`inspect` only reads a form and saves a private review file. `plan` reads the form, downloads the exact CV, and saves a review or needs-input plan without filling the employer form. `approve` authorizes the exact plan for a bounded period. `execute` can disclose approved answers/upload files and submit; run it only after reviewing and approving that exact application.

The answers file maps inspected question IDs to explicit evidence-backed answers, and selects the inspected resume upload field. Do not guess work authorization, sponsorship, compensation, demographic answers or consent.

```json
{
  "cv_question_id": "id:resume",
  "answers": {
    "id:name": {"value": "OWNER_CONFIRMED_NAME", "source": "owner_answer", "verified": true}
  }
}
```

These are illustrative placeholders, not application-ready values. An unknown required field keeps the plan in `needs_input`.

## Verification

The actual isolated Chrome test submitted once to a controlled loopback fixture, matched the exact approved file hash, observed a confirmation receipt, and proved that replay cannot submit twice. The production DOM extractor passed against controlled HTML, including hidden resume inputs and security challenges. These fixture results do not prove a real employer submission.
