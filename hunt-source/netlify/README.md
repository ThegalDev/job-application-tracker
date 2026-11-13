# HUNT on Netlify

Deploy this directory as the Netlify base directory. Build: `npm run build`; publish: `public`; functions: `netlify/functions`.

The build copies the sibling `hunt` source. Both directories must exist in the checkout. Node22 and Netlify Blobs are required.

The first backend invocation migrates the public HUNT snapshot and packages into Netlify's durable store. Later invocations use Netlify storage; this is not a continuing reverse proxy. The original host is preserved as the migration source until deployment is verified.

Public viewing requires no login. Owner controls require a private `HUNT_OWNER_KEY` environment secret; the existing login endpoint exchanges that key for a secure24-hour cookie. Background service access requires a separate `HUNT_SERVICE_KEY`. Never put either key in source. `OPENAI_API_KEY` is optional for existing approved-fact drafting and must be a private runtime secret. Full master-CV tailoring additionally needs a verified master-CV import; packages already prepared retain their full CV content.

Scheduled discovery runs at07:00,12:00,18:00 Africa/Lagos. Application submission and Gmail sending remain unfinished; moving hosts does not implement those features.
