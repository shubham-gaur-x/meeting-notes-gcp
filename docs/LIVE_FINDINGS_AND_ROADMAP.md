# Live Findings & Optimization Roadmap

> **Context**: Documented during live end-to-end testing with real Google Workspace (Calendar + Gmail), Jira Cloud (`MDP`), and Gemini 2.5 Flash / Memgraph integration on August 25, 2026.

---

## 1. Person & Owner Identity Resolution
### Observation
Action item and attendee owners currently vary across different representations:
* `Michael Baylard` (Display Name)
* `michael.baylard@onixnet.com` (Canonical Work Email)
* `Michael` (First Name shorthand from LLM extraction)

### Impact
* Splinters nodes in Memgraph: A single person can exist as multiple `:Person` nodes or have disjoint `:OWNED_BY` relationships.
* Makes filtering action items by owner fragmented in the dashboard and Jira pusher.

### Recommendation / Solution
* Enhance `meeting_notes/person_resolver.py` with alias normalization:
  * Maintain a local alias map (`first_name` $\rightarrow$ canonical email) when unique within the attendee list.
  * Canonicalize all extracted owner names against `meeting.attendees` emails before writing `:ActionItem` nodes to Memgraph.

---

## 2. Ingestion Filtering & Email Classification (Noise Reduction)
### Observation
The pipeline currently ingests and classifies non-meeting / transactional emails:
* **2FA & Verification Codes**: (e.g., automated login codes, security tokens).
* **Automated Operational Reminders**: (e.g., "Submit your timecard", payroll alerts).
* **Company-Wide Surveys & Newsletters**: Low-priority informational announcements without actionable tasks.

### Recommendation / Solution
* **Pre-Classification Fast Filter** in `meeting_notes/sources/gmail.py`:
  * Ignore emails from `no-reply@`, `noreply@`, `notifications@`, and known auth providers.
  * Regex filter for common OTP / verification patterns (e.g., `your verification code is`, `one-time passcode`).
* **Classifier Score Tuning**:
  * Adjust `classifier_score_threshold` (currently 0.40) or add negative keywords for operational/administrative announcements.
  * Flag surveys as `low_priority` / informational-only so they don't spawn Jira tickets.

---

## 3. UI / Dashboard UX Improvements
### Observations & Proposed Features
1. **Action Items Table**:
   * **Sortable Columns**: Sort by Task, Owner, Confidence, Priority, and Due Date.
   * **Filterable Controls**: Filter by Owner, Priority level, and Review status.
   * **Inline Actions**: Allow one-click status updates (Complete, Dismiss, Delete, File to Jira) directly from the dashboard so users don't have to manually locate tickets in Jira.
2. **Card Rendering & Empty Labels**:
   * **Organization Nodes**: Fix empty bubble/card rendering when an `Organization` node lacks a distinct name or label.
   * **Text Clamping**: Ensure long meeting titles or attendee lists expand gracefully on hover/click without overflowing.

---

## 4. Summary of Discussion Items for Shubham

| Topic | Proposed Action | Estimated Effort |
| :--- | :--- | :--- |
| **PR #1 (Ready)** | Parallelize embedding passes in `pipeline.py` via `asyncio.gather` | Already tested & pushed |
| **Person Normalization** | Canonicalize action item owners against attendee email roster | Small (~30 LOC) |
| **Noise Filtering** | Add pre-filters in `sources/gmail.py` for 2FA, OTP, and `no-reply` senders | Small (~40 LOC) |
| **Dashboard Enhancements** | Add table sorting, priority filters, and inline Jira task actions | Medium (~100 LOC) |
