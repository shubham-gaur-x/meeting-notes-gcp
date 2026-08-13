# Google Workspace authentication

Read this before touching anything auth-related.

**The situation:** the GCP project hosting the infrastructure is Shubham's **personal** project.
The data being read belongs to the **Onix Workspace** account, `shubham.gaur@onixnet.com`.
That split is supported and normal — but it has two consequences that shape the design, and one
of them can stop the project dead.

---

## 1. Why the split matters

A GCP project and a Google account are independent. You can create an OAuth client in any
project and consent as any account, and Pub/Sub topics work across project boundaries — Gmail's
push service can publish into a topic in a different project as long as it has permission.

What the split *does* determine is the OAuth client's **user type**:

| Where the GCP project lives | User type available | Verification | Refresh token lifetime |
|---|---|---|---|
| Personal (outside the Workspace org) | **External** only | Required for restricted scopes | **7 days** while in Testing |
| Inside the Onix Workspace org | **Internal** | Not required | Does not expire |

We are in the top row today and the bottom row later. Everything below follows from that.

---

## 2. Hard stop: the Workspace admin may block you

Google Workspace has an admin control at **Security → Access and data control → API controls**.
If "unconfigured third-party apps" is set to block — which many enterprises do — then an OAuth
client from an unknown personal GCP project cannot access Onix data at all, no matter how
correct the code is.

**This is why Phase 0.5 exists.** Find out before building on top of it.

If you're blocked, the ask is small and specific:

> Under Security → Access and data control → API controls → Manage Third-Party App Access,
> please add OAuth client ID `<id>` as **Trusted** for these scopes: `gmail.readonly`,
> `calendar.readonly`, `meetings.space.readonly`.

Note that Workspace trust and Google verification are **two separate gates**. Being marked
Trusted by the Onix admin does not remove the 7-day expiry — that is a function of the OAuth
app's publishing status, not the Workspace setting. You may well need both.

---

## 3. The 7-day refresh token problem

An OAuth app with **External** user type and **Testing** publishing status issues refresh
tokens that expire after exactly 7 days. Confirmed behaviour, not a rumour — and it is why v5
already has `scripts/refresh_gcal_token.py` and `scripts/refresh_meet_token.py` sitting in its
scripts directory.

### Why we can't just publish to Production

Gmail scopes are **restricted** scopes. Moving an app with restricted scopes to Production
requires Google's verification process plus a third-party security assessment. That is not
proportionate for this project.

### How we live with it

1. `jobs/refresh_tokens.py` runs on Cloud Scheduler every 6 hours. It exchanges the stored
   refresh token, writes the new access token to Secret Manager, and records the refresh
   token's issue date.
2. When the refresh token is within 24 hours of its 7-day expiry, the job **alerts** — a
   log-based Cloud Monitoring alert.
3. Re-consent is manual and takes about two minutes: run `scripts/auth_spike.py --reconsent`,
   approve in the browser, and the new token is written to Secret Manager.

The important part is that expiry is **loud**. A pipeline that silently stops for four days
before anyone notices is worse than one that pages you weekly.

### The permanent fix

Move to an Onix-owned GCP project. The OAuth client becomes **Internal**, and the expiry, the
test-user list, and the verification requirement all disappear at once. This is a concrete,
non-hypothetical argument to put in front of your manager alongside the cost one.

---

## 4. Scopes

Request the minimum. Every additional scope makes an admin allowlist request harder to approve.

| Scope | Why | Restricted? |
|---|---|---|
| `https://www.googleapis.com/auth/gmail.readonly` | Read meeting-related mail | Yes |
| `https://www.googleapis.com/auth/calendar.readonly` | Read events and attendees | Yes |
| `https://www.googleapis.com/auth/meetings.space.readonly` | Read conference records and transcripts | Yes |
| `https://www.googleapis.com/auth/pubsub` | Pull the transcript subscription | No |

All read-only. This system never writes to Gmail or Calendar, and saying so plainly helps when
asking for approval.

---

## 5. Phase 0.5 runbook

### 5.1 GCP project setup

```bash
gcloud config set project "$GCP_PROJECT_ID"
gcloud services enable \
  gmail.googleapis.com \
  calendar-json.googleapis.com \
  meet.googleapis.com \
  pubsub.googleapis.com
```

### 5.2 OAuth consent screen

Console → APIs & Services → OAuth consent screen:

- User type: **External**
- Publishing status: **Testing**
- Test users: add `shubham.gaur@onixnet.com`
- Scopes: the four above

### 5.3 OAuth client

Console → Credentials → Create credentials → OAuth client ID → **Desktop app**.
Download the JSON. **Never commit it.** `client_secret*.json` is in `.gitignore`.

### 5.4 The spike

`scripts/auth_spike.py` should:

1. Run a local loopback consent flow with `access_type=offline` and `prompt=consent`.
2. Print the refresh token and store it in Secret Manager.
3. Make one real call against each of:
   - Gmail — `users.messages.list`, `maxResults=1`
   - Calendar — `events.list`, `maxResults=1`
   - Meet — `conferenceRecords.list`, `pageSize=1`
4. Print a clear pass/fail per API.

Two useful details: pass `prompt=consent` explicitly or Google may not return a refresh token
on a repeat authorisation, and use a loopback redirect (`http://localhost:PORT`) since the
out-of-band flow is deprecated. v5's `scripts/refresh_gcal_token.py` has a working loopback
handler worth reading.

### 5.5 Record the outcome

Append to `docs/DECISIONS.md`:

- Did admin controls allow the app, or did you need an allowlist?
- Is Meet transcription enabled on the tenant? Did `conferenceRecords.list` return anything?
- The date the refresh token was issued, so the 7-day clock is known.

---

## 6. Meet transcripts

Meet transcription is a Workspace feature, not a personal-Gmail one, and it must be enabled by
an admin and turned on for a given meeting. The Meet REST API exposes transcripts through
`conferenceRecords.transcripts` and `conferenceRecords.transcripts.entries`.

Live capture uses the Google Workspace Events API subscription for
`google.workspace.meet.transcript.v2.fileGenerated`, delivered to a Cloud **Pub/Sub pull**
subscription. Pull, not push — no inbound endpoint required, and it's the pattern v5's
`meet_ingest.py` already proved.

**If transcripts aren't available**, Gmail and Calendar still work and the pipeline is still
valuable. Build the `Source` seam so `sources/meet.py` is a no-op when unconfigured — exactly
how v5's `meet_ingest.pull_and_stage` degrades — and light it up when the tenant supports it.

---

## 7. Secret handling

| Secret | Secret Manager id | Rotation |
|---|---|---|
| OAuth client secret | `google-oauth-client-secret` | Rare |
| Refresh token | `google-refresh-token` | **Every 7 days** while on personal GCP |
| Access token | `google-access-token` | Every 6 hours, by the job |
| Jira API token | `jira-api-token` | Manual |
| Postgres password | `postgres-password` | Terraform-managed |
| Memgraph password | `memgraph-password` | Terraform-managed |
| GitHub webhook secret | `github-webhook-secret` | Manual |

Rules:

- Cloud Run injects these as environment variables. Application code reads them through
  `config.py` and nowhere else.
- Never log a token, not even truncated.
- Never commit `client_secret*.json`, `token.json`, or a `.tfvars` containing a secret.
- The refresh-token secret should have a short version-retention policy — old versions are
  expired credentials and there's no reason to keep them.

---

## 8. Migration to the Onix project

When the Onix GCP project is approved:

1. Create a new OAuth client **inside** the Onix Workspace org → user type **Internal**.
2. No verification, no test-user list, no 7-day expiry.
3. Consent once as `shubham.gaur@onixnet.com`. Store the refresh token in the new project's
   Secret Manager.
4. `jobs/refresh_tokens.py` keeps running, but the expiry alert should stop firing. Leave the
   job in place — access tokens still need refreshing.
5. Delete the personal project's secrets and the data in it.

Everything else — the code, the Terraform, the scopes — is unchanged. That is the whole point
of treating portability as a design constraint from day one.
