# HUNT — Aminat's job application workspace

HUNT is being rebuilt around the workflow you requested: find recent relevant roles, prepare a full tailored CV and story-led application, identify a hiring contact, then apply only after reviewing the exact application.

The source changes in this checkout are **not deployed** to the hosted phone dashboard yet. The current hosted release and the code here may differ until a new private deployment is made.

## Job discovery

The hosted source now searches configured Greenhouse, Ashby and Lever boards; We Work Remotely; Remotive; Jobicy; Startup Jobs RSS; RemoteOK; a16z portfolio jobs; and YC Work at a Startup Recruiting & HR/Operations remote pages. YC detail pages provide structured role, location and datePosted metadata. Aggregator/listing dates remain separate from employer-original dates.

The Opportunities view has a `Recent remote posts · all status` filter so a fresh role is visible even when location, pay or employer-original date is unconfirmed. The stricter verified view remains separate. Current approval gates require explicit Nigeria/global eligibility, at least USD $2,500/month, no existing application, an open/current job, and an exact package version. These gates do not hide recent leads in the new view.

LinkedIn and X are not scraped or searched with private account sessions. They need approved platform access or a separate authorized search connector. Do not send account passwords, cookies or API keys in chat. YC Work at a Startup is the YC job source; the former “VC Bucket” reference was a misunderstanding.

The 48-hour source-post window controls which recent leads are surfaced. Nigeria eligibility, remote scope, salary and employer-original posting time are separate evidence checks. Unverified leads remain visible in the verification queue rather than being presented as confirmed matches.

## Application materials

HUNT preserves the full master CV. For each job, it changes the target-role headline and summary, then adds up to three role-matched, source-verbatim project highlights near the top. The original work history, projects, training and qualifications remain in the document. The writing model receives approved fact excerpts and selected project excerpts, never the full CV.

Cover letters begin with the employer's actual role need, tell a short evidence-based story, and include a small set of relevant project bullets. Claims and numbers must trace to source evidence; prose still requires your review.

## Contacts and applying

Apollo People API Search can return professional titles and LinkedIn profiles without credits, but it does not return email addresses. Apollo documents free-account API eligibility as conditional on a work email and other requirements. Email enrichment is a separate API call that may consume credits. HUNT does not reveal an email or message anyone automatically. To enable search, create an Apollo API key in your account, then add it as the private Worker secret `APOLLO_API_KEY`; do not share the key or your password in chat.

Employer-form submission is not yet connected to the hosted workflow. A Lever browser adapter and an exact-approval execution ledger exist in the local source, but they are not wired into the production application workflow. Hosted Gmail synchronization and Google Sheet writes are also not connected. Do not treat a prepared draft, queued review, or tracker read as an application submission.

## Private access and local run

Workspace API data is owner-only. The public page shell is not permission to read application packages or the CV. Keep exports and the local database private.

Double-click `Start HUNT.command` to run the local dashboard at `http://127.0.0.1:8765/`. Keep its Terminal open.

## Verification

Run the local Python suite with:

```sh
HUNT_HTTP_TESTS=1 python3 -m unittest discover -p 'test*.py'
```

Hosted Worker tests live under `cloud/test_*.mjs` and use mocked providers; they do not prove live Apollo access, external tracker writes, LinkedIn/X coverage, or employer submissions.