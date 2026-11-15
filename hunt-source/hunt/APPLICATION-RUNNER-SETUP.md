# Mac application worker

The owner authorized automatic submissions under standing instructions on 15 November 2026. Per-application owner approval is not required. Internal exact-plan hashes still bind the actual CV, form and answers to each execution.

The Mac login agent `com.hunt.application-worker` checks every 60 seconds while the user is logged in and the Mac is awake. The private runtime is in `~/Library/Application Support/HUNT/application-worker`; credentials are kept in owner-only private files, not in the LaunchAgent plist or Git. The installer copies only the required runtime code and verified CV source. Use HUNT’s existing Pause control to stop new agent actions.

## What runs automatically

The worker considers current priority Lever roles that pass the 48-hour original publication, Nigeria/worldwide remote eligibility, verified USD 2,500 monthly pay, priority score, hidden employer/role and duplicate checks. It can request HUNT’s existing tailored draft pipeline, download the exact Word CV, inspect the form, and fill only facts verifiable from the current source CV. Only direct name, email and phone fields are currently automatically mapped. Required unknown answers, ambiguous resume fields, security challenges and unsupported forms pause that role without guessing.

Standing authorization is rechecked before approval and during execution. Revocation or a changed CV/answer/form stops the final submission. An uncertain attempt cannot automatically submit again. A durable local journal prevents repeatedly drafting or inspecting the same blocked job version.

A positive employer confirmation is stored locally before publication to HUNT. Receipt publication has a separate durable outbox so network retry cannot resubmit the employer application. Hosted Applications shows an Employer confirmation section; Google tracker writes remain idempotent. An on-page receipt is explicitly separate from an employer email. Test receipts are rejected by the real receipt importer.

## Limits and evidence

Only public Lever forms are supported. Greenhouse and Ashby adapters are not implemented. Real employer-page loading has not passed verification on this Mac; therefore no real submission is claimed. The standing-authorization end-to-end check submitted once to a controlled local form, verified exact file bytes, captured a confirmation and prevented duplicate submission. Its clearly labeled JSON and screenshot are in `artifacts/tailored-cv-sample` and no email was sent.

The supplied CV sample uses the actual CV assembly/Word export path with a source-grounded demonstration summary. It demonstrates preservation and document generation, not a new model-generated employer application. See its changes.md for exact scope.

The earlier CLI inspect/plan/show/approve/execute commands remain diagnostic/manual tools. The installed worker uses standing authorization, not per-application human approval.
