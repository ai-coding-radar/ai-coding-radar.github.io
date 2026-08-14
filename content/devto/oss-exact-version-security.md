# Fail-closed npm and PyPI vulnerability checks in n8n

A dependency scan is only useful when it answers two different questions:

1. Did the public vulnerability sources report a finding for the exact version
   I run?
2. Did every required source answer successfully?

Treating a timeout as "zero vulnerabilities" makes a dashboard look clean at
the exact moment it has stopped checking. This workflow keeps those states
separate and can run on a daily n8n schedule without maintaining a scanner
server.

## Use exact installed versions

Start with the versions from your lockfile or deployment inventory, not a
range and not the registry's current `latest` tag:

```json
{
  "packages": [
    {"name": "lodash", "ecosystem": "npm", "version": "4.17.20"},
    {"name": "requests", "ecosystem": "PyPI", "version": "2.31.0"}
  ],
  "includeDownloads": true,
  "includeVulnerabilities": true,
  "includeRepository": true,
  "includeCisaKev": true
}
```

An exact version lets OSV answer for what is actually deployed. The result also
contains the registry's latest version, but it never silently replaces the
version you requested.

## Import the workflow

Download the tested five-node n8n workflow:

https://raw.githubusercontent.com/Jarvis-Dong/oss-package-health-monitor/main/examples/n8n-oss-exact-version-scan.json

After import:

1. Create an n8n **Header Auth** credential named `Authorization` with value
   `Bearer YOUR_APIFY_API_TOKEN` and attach it to the HTTP Request node.
2. Replace the two sample packages with your exact installed versions.
3. Replace the final no-op node with Slack, email, Teams, Notion, a database,
   or a private webhook.
4. Test once, then activate the daily schedule.

The public workflow export deliberately contains no token, cookie, credential
ID, or destination URL.

## Route findings without hiding failures

The filter forwards a row when any of these conditions is true:

- `vulnerabilities` contains an OSV record;
- `cisaKevMatches` contains a CVE listed in CISA KEV;
- `status` is `partial` or `error` because a required source failed;
- `isLatest` is `false`, so the installed version can be reviewed.

An OSV error leaves `vulnerabilities` and `vulnerabilityCount` as `null`. It is
not converted into an empty list. That distinction is what makes the workflow
fail closed instead of producing a false clean result.

The Actor queries public npm and PyPI registry metadata, the
[OSV API](https://osv.dev/), and the
[CISA Known Exploited Vulnerabilities catalog](https://www.cisa.gov/known-exploited-vulnerabilities-catalog).
It does not access private packages or automatically change dependencies.

## Try the API with visible pricing

The public Actor and exact-version example are available here:

- Actor: https://apify.com/ai-coding-radar/oss-package-health-monitor
- Example: https://apify.com/ai-coding-radar/oss-package-health-monitor/examples/scan-installed-npm-and-pypi-versions-for-cves
- Source and Make recipe: https://github.com/Jarvis-Dong/oss-package-health-monitor

The published price is `$0.0015` per returned package record plus the small
Actor-start event shown on the Store page. Start with a short dependency list,
keep the source-status fields in downstream alerts, and treat the output as
point-in-time evidence rather than a security certification.
