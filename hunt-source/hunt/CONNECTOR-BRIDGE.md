# Connected Google refresh protocol

HUNT has no access to the desktop app's private OAuth credentials. Connected Gmail/Drive reads happen through Codex's authorized connectors. This protocol lets a later Codex run refresh the local workspace without exporting credentials or giving the website broad Google access.

1. Confirm Gmail profile is `majekadegbeaminat85@gmail.com` using its connected account. Never use another account.
2. Read metadata for tracker `1H8Dgplggg8wkuNoK-lIVJ602AzQHjkXzpOVQ3ONgKeo`. Resolve the actual `Applications` tab and its bounds again.
3. Read a bounded populated range beginning at A1, covering columns A:J and current records. Start with A1:J200; expand only if the final row is populated. Do not read unrelated files or mail.
4. Save a private intermediate JSON file under the parent workspace's `work/` with `sheet_id`, `email`, `verified_at` (current ISO UTC time), and `rows` (header plus plain values returned by the connector). Use a structured file-write tool; never interpolate source text in a shell command.
5. Run `python3 hunt.py sync-snapshot --seed <absolute intermediate path>`. The importer checks account and tracker identity, updates changed records with audit events, preserves absent records, and keeps separate application dates separate.
6. For Gmail reconciliation, search recruiting messages since the last verified Google snapshot, using a bounded result count and pagination. Exclude authentication codes, newsletters, unrelated correspondence, and sensitive attachments. Read candidate messages to verify their meaning. Never infer a rejection from silence or a generic newsletter.
7. Only when the company, role and exact application event can be matched, create a normalized event object with `id`, `at`, `company`, `role`, `body` (relevant text only) and `evidence` (Gmail message URL). Leave uncertain associations in review. Save the normalized array under `work/`, then run `python3 hunt.py reconcile --seed <absolute path>`.
8. Gmail reconciliation changes the local workspace only. Do not write the live Sheet automatically. For a requested Sheet update, reread exact target cells including formulas/validation, compare against expected previous values, apply only the intended changes, preserve earlier evidence in notes, and verify the write with a connector read-back. Reconcile the Sheet back into HUNT afterward.
9. Never send email, submit applications, approve packages, accept interviews, or infer a recipient. Scheduled refresh does not authorize these actions.

The current release has verified the Google connectors, completed the three requested live tracker corrections, and tested this bridge locally. Future scheduled bridge execution is not a separately verified unattended Google integration.
