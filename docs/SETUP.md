# Setup

Three tiers. Each is one command, each is additive, and each is honest about what
it actually proves. **Start at tier 0** — it needs no credentials at all.

If you are ever unsure what is missing, ask:

```bash
make doctor
```

It names every gap and gives you a runnable fix for each. That is its whole job.

| Tier | Command | Credentials needed | What it proves |
|---|---|---|---|
| 0 | `make demo` | none | the pipeline, graph writes, algorithms, memory layers, API, dashboard |
| 1 | `make demo LLM=gemini` | one free API key | genuine LLM extraction and embeddings |
| 2 | `make deploy ENV=personal` | GCP + Google Workspace + Jira | the actual product, deployed |

**Tier 0 passing does not mean tier 2 works.** They prove different things. A green
tier 0 says the logic is sound; it says nothing about your cloud setup.

---

## Prerequisites

- **Python 3.11+**
- **Docker** — for the local Postgres and Memgraph
- Tier 2 only: **gcloud** and **terraform**

---

## Tier 0 — local, no credentials

```bash
git clone <this repo>
cd meeting-notes-gcp

python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

cp .env.example .env      # no edits needed for tier 0
make doctor               # confirms Docker, ports, Python version
make demo-up              # starts Postgres + Memgraph
make demo                 # runs the pipeline over sample meetings
```

The LLM step uses `LLM_BACKEND=fake`, which replays recorded fixtures from
`sample_data/llm_fixtures/`. No API key, no network, deterministic. The graph you
get is real — built by the real pipeline from real recorded extractions.

Inspect it in Memgraph Lab at **http://localhost:3000**.

```bash
make demo-down            # stop the stack
make demo-down ARGS=-v    # stop it and delete its data
```

> **Status:** `make demo` is not wired up yet — the pipeline lands in Phase 6 and
> the dashboard in Phase 8 (`docs/PHASE_PLAN.md`). `make demo-up`, `make doctor`,
> and the test suite all work today. The target deliberately fails with an
> explanation rather than pretending to succeed.

---

## Tier 1 — real LLM

Everything from tier 0, but real extraction instead of replayed fixtures.

1. Get a free key at **https://aistudio.google.com/apikey** (no GCP project, no
   billing).
2. Put it in `.env`:
   ```
   LLM_BACKEND=gemini
   GEMINI_API_KEY=your-key-here
   ```
3. Check and run:
   ```bash
   make doctor TIER=1
   make demo
   ```

Prefer local models? Set `LLM_BACKEND=lmstudio` and run LM Studio with both a chat
model and `text-embedding-nomic-embed-text-v1.5`. Embeddings must be **768
dimensions** in every backend — the Memgraph vector indexes are built for 768.

---

## Tier 2 — deploy to your own GCP

This is the real thing, and it is the only tier with an unavoidable manual step.

### The part nobody can automate

**Google exposes no API for creating an OAuth consent screen or a Desktop OAuth
client with restricted Gmail scopes.** Terraform cannot do it, and neither can we.
`google_iap_brand` / `google_iap_client` cover neither case. So this is hand-work
in the console, once, and `make doctor TIER=2` will tell you if you have not done
it yet.

Full walkthrough: **`docs/GOOGLE_AUTH.md` §5.** In short:

1. Create a GCP project and enable the Gmail, Calendar, Meet, and Pub/Sub APIs.
2. Console → Google Auth Platform → **Audience**: user type External, publishing
   status Testing, and add your Workspace address as a **test user**.
3. Console → **Data Access**: add the four scopes (`gmail.readonly`,
   `calendar.readonly`, `meetings.space.readonly`, `pubsub`).
4. Console → **Clients** → Create client → **Desktop app**. Copy the client ID and
   secret into `.env`.

> Google's console splits this across separate **Audience** and **Data Access**
> pages rather than one linear wizard. If you are following an older guide that
> describes a single "OAuth consent screen" flow, that is why it looks different.

### Then

```bash
make auth-spike           # consent in the browser; stores a refresh token
```

You will see **"Google hasn't verified this app"**. That is expected for an
External + Testing app. Click **Advanced → Go to … (unsafe)**.

The spike then makes one real call against Gmail, Calendar, and Meet and prints
PASS/FAIL for each. It never prints the token.

### The 7-day clock

While the OAuth app is External + Testing, **the refresh token expires every 7
days**. There is no way around it on a personal project. `make doctor TIER=2` warns
you before it dies; to renew:

```bash
make auth-spike ARGS=--reconsent
```

The permanent fix is moving to an Onix-owned project where the client can be
**Internal** — no verification, no expiry (`docs/GOOGLE_AUTH.md` §8, Phase 10).

### Infrastructure

```bash
cp terraform/envs/personal.example.tfvars terraform/envs/personal.tfvars
$EDITOR terraform/envs/personal.tfvars     # project id, region, billing account

make doctor TIER=2                         # verify before spending money
make tf-init
make tf-plan  ENV=personal
make tf-apply ENV=personal
```

Real `.tfvars` files are gitignored because they carry project ids; the
`*.example.tfvars` alongside them are committed so the required variables are
discoverable.

> **Cost warning.** Tiers 0 and 1 cost nothing. Tier 2 creates **always-on**
> resources — Cloud SQL and the Memgraph VM bill 24/7 whether you use them or not.
> The Terraform includes a budget alert from the first apply. Set
> `budget_amount_usd` to a number you are actually comfortable with.

---

## Troubleshooting

**`make doctor` warns that a port is in use.** Something already listens on 5432,
7687, 7444, or 8080. If it is this project's own stack, that is fine. Otherwise
stop it, or run `make demo-down`.

**`Error 401: invalid_client` during consent.** The client ID in `.env` does not
match a real OAuth client — usually a typo, or the client was created in a
different project than the one you are pointed at. Newly created clients can also
take a few minutes to propagate.

**Consent succeeds but the API calls 403.** The scopes on the consent screen do not
match the four the code requests, or your Workspace admin has restricted
third-party app access. See `docs/GOOGLE_AUTH.md` §2.

**Everything worked yesterday and fails today.** The 7-day refresh token. Run
`make auth-spike ARGS=--reconsent`.

---

## Where things are

| File | What it is |
|---|---|
| `CLAUDE.md` | Authoritative rules, module boundaries, graph schema |
| `docs/PHASE_PLAN.md` | The build order |
| `docs/ARCHITECTURE.md` | Target architecture and the GCP resource inventory |
| `docs/GOOGLE_AUTH.md` | OAuth in full, including the 7-day problem |
| `docs/DECISIONS.md` | ADR log — why things are the way they are |
