// Regenerates docs/meeting-notes-gcp-KT.pptx.
//
//   npm i pptxgenjs && node docs/kt-deck.js
//
// The .pptx is committed because it is the deliverable; this file is committed
// because a binary nobody can rebuild is a dead end. Figures in the deck come
// from the verification run — update them here, not by editing the .pptx, or
// the two drift apart.
const pptxgen = require("pptxgenjs");

const INK = "12151C", SURF = "1A1E27", RAISED = "232833";
const TEXT = "E6E9EF", MUTED = "98A1B3", FAINT = "6B7484";
const BLUE = "6EA8FE", GREEN = "5DDBA4", AMBER = "E0A458", RED = "F28B93";
const PAPER = "FFFFFF", PINK = "171A21";

const H = "Cambria", B = "Calibri", M = "Courier New";

const p = new pptxgen();
p.layout = "LAYOUT_WIDE";           // 13.3 x 7.5
p.author = "meeting-notes-gcp";
p.title = "Meeting Memory Graph — KT";

const W = 13.3, HT = 7.5, MX = 0.75;

// ── helpers ─────────────────────────────────────────────────────────────────
function dark(s) { s.background = { color: INK }; }
function light(s) { s.background = { color: PAPER }; }

// the motif: a node dot, like the graph draws
function dot(s, x, y, color, size) {
  s.addShape(p.ShapeType.ellipse, {
    x, y, w: size || 0.13, h: size || 0.13, fill: { color }, line: { color, width: 0 },
  });
}

function title(s, text, onDark) {
  s.addText(text, {
    x: MX, y: 0.52, w: W - MX * 2, h: 0.85, fontFace: H, fontSize: 34, bold: true,
    color: onDark ? TEXT : PINK, align: "left", valign: "middle", margin: 0,
  });
}

function kicker(s, text, color) {
  s.addText(text.toUpperCase(), {
    x: MX, y: 0.22, w: W - MX * 2, h: 0.3, fontFace: M, fontSize: 10.5,
    color: color || BLUE, charSpacing: 1.6, margin: 0, valign: "middle",
  });
}

function note(s, t) { s.addNotes(t); }

// ── 1. title ────────────────────────────────────────────────────────────────
let s = p.addSlide(); dark(s);
[[BLUE, 0], [GREEN, 0.26], [AMBER, 0.52]].forEach(([c, dx]) => dot(s, MX + dx, 2.28, c, 0.17));
s.addText("Meeting Memory Graph", {
  x: MX, y: 2.62, w: 10.6, h: 1.15, fontFace: H, fontSize: 48, bold: true,
  color: TEXT, margin: 0, valign: "middle",
});
s.addText("Meetings in. A graph that answers questions out.", {
  x: MX, y: 3.78, w: 9.6, h: 0.5, fontFace: B, fontSize: 19, color: MUTED, margin: 0,
});
s.addText("Knowledge transfer  ·  meeting-notes-gcp  ·  v6", {
  x: MX, y: 6.3, w: 8, h: 0.34, fontFace: M, fontSize: 11.5, color: FAINT, margin: 0,
});
note(s, "A pipeline that reads a Google Workspace account and turns meetings into a property graph. Built and verified locally; not yet deployed to GCP. Everything in this deck was measured on a real run, not estimated.");

// ── 2. what it is ───────────────────────────────────────────────────────────
s = p.addSlide(); light(s);
kicker(s, "What it is", "2F6FD0");
title(s, "A graph, not a folder of notes");
s.addText([
  { text: "Gmail, Calendar and Meet go in. An LLM extracts structure. The result is stored as a property graph — meetings, people, topics, decisions and commitments as nodes; who attended what and what produced what as edges.", fontSize: 15 },
], { x: MX, y: 1.62, w: 6.5, h: 1.5, fontFace: B, color: "5C6472", margin: 0, lineSpacing: 22 });

s.addText("The graph answers what a document store cannot:", {
  x: MX, y: 3.15, w: 6.5, h: 0.3, fontFace: B, fontSize: 13, bold: true, color: PINK, margin: 0,
});
const asks = [
  ["Who is central to this workstream?", BLUE],
  ["What did we decide about the SOW?", GREEN],
  ["What am I on the hook for?", AMBER],
];
asks.forEach(([q, c], i) => {
  const y = 3.6 + i * 0.62;
  dot(s, MX + 0.02, y + 0.14, c, 0.15);
  s.addText(q, { x: MX + 0.34, y, w: 6.1, h: 0.42, fontFace: B, fontSize: 14.5, color: PINK, margin: 0, valign: "middle", italic: true });
});

s.addShape(p.ShapeType.roundRect, {
  x: 7.75, y: 1.62, w: 4.8, h: 4.55, rectRadius: 0.09,
  fill: { color: INK }, line: { color: INK, width: 0 },
});
s.addText("At a glance", {
  x: 8.1, y: 1.92, w: 4.1, h: 0.3, fontFace: M, fontSize: 10.5, color: FAINT, charSpacing: 1.4, margin: 0,
});
const facts = [["96", "meetings"], ["263", "facts, all embedded"], ["67", "people, 6 orgs"], ["665", "tests passing"], ["13,005", "lines of source"]];
facts.forEach(([n, l], i) => {
  const y = 2.42 + i * 0.75;
  s.addText(n, { x: 8.1, y, w: 1.55, h: 0.44, fontFace: H, fontSize: 23, bold: true, color: BLUE, margin: 0, valign: "middle" });
  s.addText(l, { x: 9.72, y, w: 2.6, h: 0.44, fontFace: B, fontSize: 13, color: MUTED, margin: 0, valign: "middle" });
});
note(s, "The point of a graph is relationships. A folder of notes can store the same text but cannot tell you who is central, or trace a decision back to the meeting that produced it.");

// ── 3. why v6 ───────────────────────────────────────────────────────────────
s = p.addSlide(); light(s);
kicker(s, "Lineage", "2F6FD0");
title(s, "Why this was rebuilt");
s.addText("v5 worked. It ran entirely on a laptop. Two dependencies made it undeployable — and those two are the whole reason v6 exists.", {
  x: MX, y: 1.6, w: 11.5, h: 0.6, fontFace: B, fontSize: 15, color: "5C6472", margin: 0,
});

const changes = [
  ["Airbyte is gone", "Ingestion is four connectors we own, running as Cloud Run Jobs. v5 leaned on a hosted product for this.", BLUE],
  ["No in-process scheduler", "v5 ran APScheduler inside its own web service. v6 uses Cloud Scheduler triggering stateless jobs — nothing depends on a long-lived process staying alive.", GREEN],
];
changes.forEach(([h, d, c], i) => {
  const x = MX + i * 6.0;
  s.addShape(p.ShapeType.roundRect, { x, y: 2.5, w: 5.55, h: 2.35, rectRadius: 0.09, fill: { color: "F3F5F9" }, line: { color: "E4E9F0", width: 1 } });
  dot(s, x + 0.42, 2.88, c, 0.16);
  s.addText(h, { x: x + 0.42, y: 3.18, w: 4.7, h: 0.4, fontFace: H, fontSize: 19, bold: true, color: PINK, margin: 0 });
  s.addText(d, { x: x + 0.42, y: 3.66, w: 4.75, h: 1.0, fontFace: B, fontSize: 13.5, color: "5C6472", margin: 0 });
});
s.addText("Everything else — Memgraph, the extraction prompts, the Cypher, the test suite — was carried across on purpose rather than rewritten.", {
  x: MX, y: 5.35, w: 11.5, h: 0.5, fontFace: B, fontSize: 14, color: "5C6472", margin: 0, italic: true,
});
note(s, "This is the key framing: v6 is a port, not a rewrite. Justify every file that does NOT come across.");

// ── 4. data flow ────────────────────────────────────────────────────────────
s = p.addSlide(); dark(s);
kicker(s, "Architecture", BLUE);
title(s, "How data moves", true);
s.addText("Six stages, each a separate process. Order is real — each stage only sees what the previous one committed.", {
  x: MX, y: 1.5, w: 11.5, h: 0.4, fontFace: B, fontSize: 13.5, color: MUTED, margin: 0,
});
const stages = [
  ["1", "Ingest", "Four connectors → one staging table, watermarked", "sources/*.py"],
  ["2", "Claim", "SKIP LOCKED batch claim — exactly-once, no queue", "db.py"],
  ["3", "Classify", "Rules-based score. No LLM, no cost. Most email is not a meeting", "classifier.py"],
  ["4", "Extract", "Vertex Gemini → structured JSON → validated models", "extractor.py"],
  ["5", "Resolve + write", "People resolved, then ONE transaction into the graph", "graph_client.py"],
  ["6", "Enrich + act", "Facts, embeddings, causality. Jira tickets for commitments", "memory/*.py"],
];
stages.forEach(([n, h, d, f], i) => {
  const y = 2.12 + i * 0.79;
  s.addShape(p.ShapeType.roundRect, { x: MX, y, w: 11.8, h: 0.68, rectRadius: 0.07, fill: { color: SURF }, line: { color: RAISED, width: 1 } });
  s.addText(n, { x: MX + 0.28, y, w: 0.4, h: 0.68, fontFace: M, fontSize: 13, color: BLUE, margin: 0, valign: "middle" });
  s.addText(h, { x: MX + 0.78, y, w: 2.5, h: 0.68, fontFace: H, fontSize: 15, bold: true, color: TEXT, margin: 0, valign: "middle" });
  s.addText(d, { x: MX + 3.3, y, w: 6.3, h: 0.68, fontFace: B, fontSize: 12.5, color: MUTED, margin: 0, valign: "middle" });
  s.addText(f, { x: MX + 9.7, y, w: 1.95, h: 0.68, fontFace: M, fontSize: 10.5, color: FAINT, margin: 0, valign: "middle", align: "right" });
});
note(s, "Walk the colleague down this list. The two things worth pausing on: SKIP LOCKED gives exactly-once without a message queue, and stage 5 is a single ACID transaction so a meeting lands complete or not at all.");

// ── 5. module map, core ─────────────────────────────────────────────────────
s = p.addSlide(); light(s);
kicker(s, "Module map  ·  1 of 2", "2F6FD0");
title(s, "Four modules own the outside world");
s.addText("Nothing else may talk to these systems. Enforced by tests and by a guardrail gate.", {
  x: MX, y: 1.56, w: 11.5, h: 0.35, fontFace: B, fontSize: 14, color: "5C6472", margin: 0,
});
const owners = [
  ["db.py", "The only module containing SQL", "539"],
  ["graph_client.py", "The only module with generic Cypher", "1,246"],
  ["graph_algorithms.py", "The only module calling MAGE procedures", "176"],
  ["jira_client.py", "The only module talking to Jira", "366"],
  ["llm_client.py", "The only module constructing an LLM client", "436"],
  ["config.py", "The only module reading os.environ", "155"],
];
owners.forEach(([f, d, n], i) => {
  const y = 2.16 + i * 0.62;
  s.addShape(p.ShapeType.roundRect, { x: MX, y, w: 11.8, h: 0.52, rectRadius: 0.06, fill: { color: i % 2 ? "F7F8FA" : "FFFFFF" }, line: { color: "E4E9F0", width: 1 } });
  dot(s, MX + 0.26, y + 0.19, BLUE, 0.14);
  s.addText(f, { x: MX + 0.6, y, w: 3.1, h: 0.52, fontFace: M, fontSize: 13, color: PINK, margin: 0, valign: "middle" });
  s.addText(d, { x: MX + 3.8, y, w: 6.4, h: 0.52, fontFace: B, fontSize: 13.5, color: "5C6472", margin: 0, valign: "middle" });
  s.addText(n + " lines", { x: MX + 10.2, y, w: 1.4, h: 0.52, fontFace: M, fontSize: 11, color: "8A92A1", margin: 0, valign: "middle", align: "right" });
});
s.addText("Why it matters: when Jira changes, there is exactly one file to open.", {
  x: MX, y: 6.05, w: 11.5, h: 0.4, fontFace: B, fontSize: 14, color: PINK, margin: 0, italic: true,
});
note(s, "This is the single most useful thing for a new person to internalise. It makes the codebase navigable: any question of the form 'where does X happen' has one answer.");

// ── 6. module map, rest ─────────────────────────────────────────────────────
s = p.addSlide(); light(s);
kicker(s, "Module map  ·  2 of 2", "2F6FD0");
title(s, "The rest of the package");
const groups = [
  ["Pipeline", BLUE, ["pipeline.py — one process(), per-source adapters", "classifier.py — is this worth extracting?", "person_resolver.py — attendee to canonical person", "dedup.py — is this commitment already open?"]],
  ["Memory", GREEN, ["semantic.py — durable facts and preferences", "episodic.py — order, and what caused what", "procedural.py — recurring meeting shapes", "vector.py — 768-dim search", "retrieval.py — natural-language answers"]],
  ["Sources", AMBER, ["gmail.py — one record per thread", "calendar.py — invitees with real addresses", "meet.py — conference records, transcripts", "jira.py — status flowing back"]],
  ["Surface", "C792EA", ["api/main.py — FastAPI, scales to zero", "api/routers/*.py — read endpoints", "dashboard.html — 7 tabs, no build step", "jobs/*.py — 7 Cloud Run entrypoints"]],
];
groups.forEach(([g, c, items], i) => {
  const x = MX + (i % 2) * 6.0, y = 1.68 + Math.floor(i / 2) * 2.55;
  s.addShape(p.ShapeType.roundRect, { x, y, w: 5.55, h: 2.3, rectRadius: 0.09, fill: { color: "F7F8FA" }, line: { color: "E4E9F0", width: 1 } });
  dot(s, x + 0.34, y + 0.32, c, 0.15);
  s.addText(g, { x: x + 0.66, y: y + 0.16, w: 3.5, h: 0.4, fontFace: H, fontSize: 17, bold: true, color: PINK, margin: 0, valign: "middle" });
  s.addText(items.map((t, k) => ({ text: t, options: { bullet: true, breakLine: k < items.length - 1 } })), {
    x: x + 0.36, y: y + 0.66, w: 5.0, h: 1.5, fontFace: B, fontSize: 11.5, color: "5C6472", margin: 0, paraSpaceAfter: 4,
  });
});
note(s, "Skim this. The detail is in the KT document; the point here is the shape of the package.");

// ── 7. graph schema ─────────────────────────────────────────────────────────
s = p.addSlide(); dark(s);
kicker(s, "Data model", BLUE);
title(s, "What the graph holds", true);
const layers = [
  ["Core", BLUE, "Meeting · Person · Organization · Topic · Decision · ActionItem", "ATTENDED · DISCUSSED · PRODUCED · FOLLOWS_UP · ASSIGNED_TO"],
  ["Memory", GREEN, "Fact · Preference · Procedure · MemorySession", "HAS_FACT · KNOWS · PRECEDED_BY · CAUSED_BY"],
  ["Governance", AMBER, "PersonReview · Blocker", "NEEDS_REVIEW · RAISES_BLOCKER"],
  ["Provenance", "C792EA", "Ticket · PullRequest · AgentRun", "TICKETED_AS · IMPLEMENTS · RESOLVED_BY"],
];
layers.forEach(([n, c, nodes, edges], i) => {
  const y = 1.66 + i * 1.09;
  s.addShape(p.ShapeType.roundRect, { x: MX, y, w: 11.8, h: 0.95, rectRadius: 0.07, fill: { color: SURF }, line: { color: RAISED, width: 1 } });
  dot(s, MX + 0.3, y + 0.41, c, 0.15);
  s.addText(n, { x: MX + 0.62, y, w: 1.7, h: 0.95, fontFace: H, fontSize: 15, bold: true, color: TEXT, margin: 0, valign: "middle" });
  s.addText(nodes, { x: MX + 2.4, y: y + 0.14, w: 9.2, h: 0.36, fontFace: M, fontSize: 10.5, color: TEXT, margin: 0, valign: "middle" });
  s.addText(edges, { x: MX + 2.4, y: y + 0.48, w: 9.2, h: 0.36, fontFace: M, fontSize: 10.5, color: FAINT, margin: 0, valign: "middle" });
});
s.addText("Every node has a deterministic uuid5 id — so reprocessing MERGEs rather than duplicating.", {
  x: MX, y: 6.25, w: 11.5, h: 0.4, fontFace: B, fontSize: 13.5, color: MUTED, margin: 0, italic: true,
});
note(s, "Deterministic ids are why the pipeline is safe to re-run. Same source record always produces the same node id.");

// ── 8. governance ───────────────────────────────────────────────────────────
s = p.addSlide(); light(s);
kicker(s, "The rule to explain out loud", "B3641A");
title(s, "Naming a person is opt-in");
s.addText("Person.tracked defaults to false. Every per-person analytic filters on it — PageRank, centrality, community membership, the graph view. Aggregates are the default.", {
  x: MX, y: 1.62, w: 6.7, h: 1.1, fontFace: B, fontSize: 15.5, color: "5C6472", margin: 0, lineSpacing: 23,
});
s.addShape(p.ShapeType.roundRect, { x: MX, y: 2.95, w: 6.7, h: 1.62, rectRadius: 0.09, fill: { color: "FBEEE0" }, line: { color: "F0DCC0", width: 1 } });
s.addText("This is why the dashboard's \"Most connected people\" panel reads empty.", {
  x: MX + 0.4, y: 3.12, w: 5.9, h: 0.45, fontFace: B, fontSize: 14.5, bold: true, color: "8A4A12", margin: 0, valign: "middle",
});
s.addText("That is the gate working, not a bug. The panel says so directly. Set tracked on someone and they appear.", {
  x: MX + 0.4, y: 3.6, w: 5.9, h: 0.7, fontFace: B, fontSize: 13.5, color: "8A4A12", margin: 0,
});
s.addShape(p.ShapeType.roundRect, { x: 7.9, y: 1.62, w: 4.65, h: 2.83, rectRadius: 0.09, fill: { color: INK }, line: { color: INK, width: 0 } });
s.addText("Verified live", { x: 8.24, y: 1.88, w: 4, h: 0.3, fontFace: M, fontSize: 10.5, color: FAINT, charSpacing: 1.4, margin: 0 });
[["0 of 67", "people opted in", GREEN], ["0", "named on any per-person surface", GREEN], ["1", "shared predicate, reused", BLUE]].forEach(([n, l, c], i) => {
  const y = 2.36 + i * 0.72;
  s.addText(n, { x: 8.24, y, w: 1.7, h: 0.42, fontFace: H, fontSize: 19, bold: true, color: c, margin: 0, valign: "middle" });
  s.addText(l, { x: 10.0, y, w: 2.4, h: 0.42, fontFace: B, fontSize: 12, color: MUTED, margin: 0, valign: "middle" });
});
s.addText("Found in review: three surfaces spelled this rule separately and one of them did not spell it at all. The predicate is now written once and reused, so a fourth surface inherits it.", {
  x: MX, y: 4.85, w: 11.7, h: 0.7, fontFace: B, fontSize: 13.5, color: "5C6472", margin: 0, italic: true,
});
note(s, "Governance is a first-class feature here, not an afterthought. Aggregates by default; naming individuals requires explicit opt-in via the roster file.");

// ── 9. dev agent intro ──────────────────────────────────────────────────────
s = p.addSlide(); dark(s);
kicker(s, "The part worth demoing", GREEN);
title(s, "It writes the code too", true);
s.addText("Engineering commitments become Jira tickets. An agent picks them up and opens pull requests.", {
  x: MX, y: 1.5, w: 11.5, h: 0.4, fontFace: B, fontSize: 15, color: MUTED, margin: 0,
});
const steps = [
  ["Find", "Labelled tickets in the active sprint"],
  ["Clone", "The repo the TICKET names — not a fixed one"],
  ["Work", "Headless Gemini CLI in an isolated git worktree"],
  ["Judge", "Seven gates, then an independent reviewer"],
  ["Ship", "Opens a PR, moves the ticket to In Review"],
];
steps.forEach(([h, d], i) => {
  const x = MX + i * 2.38;
  s.addShape(p.ShapeType.roundRect, { x, y: 2.25, w: 2.18, h: 2.3, rectRadius: 0.09, fill: { color: SURF }, line: { color: RAISED, width: 1 } });
  s.addShape(p.ShapeType.ellipse, { x: x + 0.82, y: 2.52, w: 0.54, h: 0.54, fill: { color: RAISED }, line: { color: GREEN, width: 1.25 } });
  s.addText(String(i + 1), { x: x + 0.82, y: 2.52, w: 0.54, h: 0.54, fontFace: M, fontSize: 13, color: GREEN, align: "center", valign: "middle", margin: 0 });
  s.addText(h, { x: x + 0.16, y: 3.22, w: 1.86, h: 0.36, fontFace: H, fontSize: 15, bold: true, color: TEXT, align: "center", margin: 0 });
  s.addText(d, { x: x + 0.16, y: 3.6, w: 1.86, h: 0.85, fontFace: B, fontSize: 11.5, color: MUTED, align: "center", margin: 0 });
});
s.addShape(p.ShapeType.roundRect, { x: MX, y: 4.95, w: 11.8, h: 0.95, rectRadius: 0.07, fill: { color: "15302A" }, line: { color: "1D4438", width: 1 } });
s.addText("It never merges. CLOSED is written only when a human actually merges the PR. That is the checkpoint.", {
  x: MX + 0.42, y: 4.95, w: 11, h: 0.95, fontFace: B, fontSize: 15, bold: true, color: GREEN, margin: 0, valign: "middle",
});
note(s, "The repo comes from the ticket description, so one agent serves many repositories. The worktree is the isolation boundary; the gates decide what ships.");

// ── 10. two layers ──────────────────────────────────────────────────────────
s = p.addSlide(); light(s);
kicker(s, "Safety", "2F6FD0");
title(s, "Two layers decide whether it ships");
s.addShape(p.ShapeType.roundRect, { x: MX, y: 1.68, w: 5.75, h: 3.65, rectRadius: 0.09, fill: { color: "F7F8FA" }, line: { color: "E4E9F0", width: 1 } });
dot(s, MX + 0.36, 2.02, BLUE, 0.16);
s.addText("Seven deterministic gates", { x: MX + 0.68, y: 1.86, w: 4.6, h: 0.4, fontFace: H, fontSize: 17, bold: true, color: PINK, margin: 0, valign: "middle" });
s.addText("Pure functions over the diff — a planted violation is a unit test.", { x: MX + 0.38, y: 2.32, w: 5.1, h: 0.35, fontFace: B, fontSize: 12, color: "8A92A1", margin: 0, italic: true });
const gates = ["Tests green", "Lint and types clean", "Diff within budget", "No protected paths touched", "No new dependencies", "No secrets", "Module boundaries respected"];
s.addText(gates.map((g, i) => ({ text: g, options: { bullet: true, breakLine: i < gates.length - 1 } })), {
  x: MX + 0.38, y: 2.76, w: 5.1, h: 2.2, fontFace: B, fontSize: 13, color: "5C6472", margin: 0, paraSpaceAfter: 5,
});
s.addShape(p.ShapeType.roundRect, { x: 6.9, y: 1.68, w: 5.65, h: 3.65, rectRadius: 0.09, fill: { color: "F7F8FA" }, line: { color: "E4E9F0", width: 1 } });
dot(s, 7.26, 2.02, GREEN, 0.16);
s.addText("An independent reviewer", { x: 7.58, y: 1.86, w: 4.6, h: 0.4, fontFace: H, fontSize: 17, bold: true, color: PINK, margin: 0, valign: "middle" });
s.addText("A second model reads the ticket, the diff, and the gate evidence.", { x: 7.28, y: 2.32, w: 5.0, h: 0.35, fontFace: B, fontSize: 12, color: "8A92A1", margin: 0, italic: true });
s.addText([
  { text: "Only high-severity findings block.", options: { bullet: true, breakLine: true } },
  { text: "Anything less is surfaced for the human, not acted on.", options: { bullet: true, breakLine: true } },
  { text: "If it cannot run, the run is not blocked — the deterministic gates already passed.", options: { bullet: true } },
], { x: 7.28, y: 2.76, w: 5.0, h: 2.2, fontFace: B, fontSize: 13, color: "5C6472", margin: 0, paraSpaceAfter: 6 });
s.addText("A gate that cannot run counts as a FAILURE, never a skip. If either layer objects the run ends at NEEDS_HUMAN — terminal — and the PR is left open, because the work is real.", {
  x: MX, y: 5.62, w: 11.8, h: 0.75, fontFace: B, fontSize: 14, color: PINK, margin: 0,
});
note(s, "Asymmetry worth explaining: deterministic gates fail closed, the LLM reviewer fails open. An outage of the model should not halt the pipeline when the hard checks already passed and a human still reviews before merge.");

// ── 11. proven ──────────────────────────────────────────────────────────────
s = p.addSlide(); dark(s);
kicker(s, "Verified end to end", GREEN);
title(s, "One ticket, start to finish", true);
const chain = [
  ["Ticket MNV-108", "picked up from Jira, labelled dev-agent"],
  ["Implemented", "in a per-ticket git worktree"],
  ["Committed and pushed", "branch agent/MNV-108"],
  ["Pull request opened", "against the repo the ticket named"],
  ["7 gates passed", "reviewer approved, 1 non-blocking finding"],
  ["Jira moved to In Review", "run reached SHIPPED — terminal, attempt 1"],
  ["Provenance written", "AgentRun -[:PRODUCED]-> PullRequest"],
];
chain.forEach(([h, d], i) => {
  const y = 1.68 + i * 0.68;
  dot(s, MX + 0.06, y + 0.26, GREEN, 0.15);
  s.addText(h, { x: MX + 0.42, y, w: 4.3, h: 0.55, fontFace: B, fontSize: 14.5, bold: true, color: TEXT, margin: 0, valign: "middle" });
  s.addText(d, { x: MX + 4.8, y, w: 7.0, h: 0.55, fontFace: B, fontSize: 13, color: MUTED, margin: 0, valign: "middle" });
});
s.addText("Six bugs surfaced only by running it. None had a failing test.", {
  x: MX, y: 6.5, w: 11.5, h: 0.4, fontFace: B, fontSize: 14, color: AMBER, margin: 0, italic: true,
});
note(s, "This is the demo. Show PR #1 on GitHub, the Jira ticket in In Review, and the AgentRun node in the graph.");

// ── 12. dashboard ───────────────────────────────────────────────────────────
s = p.addSlide(); light(s);
kicker(s, "The surface", "2F6FD0");
title(s, "Seven tabs, each a real question");
const tabs = [
  ["Overview", "What happened? Counters over a selectable window"],
  ["Meetings", "What was decided, who was there — click any row"],
  ["Action Items", "What do I owe? Filter by owner, links to Jira"],
  ["Workstreams", "Clusters the graph found, named by their topics"],
  ["Graph", "The graph itself — force-directed, hover for names"],
  ["Ask", "Anything else, in natural language"],
  ["Needs You", "What the system chose to ask about rather than guess"],
];
tabs.forEach(([t, d], i) => {
  const y = 1.66 + i * 0.66;
  s.addShape(p.ShapeType.roundRect, { x: MX, y, w: 11.8, h: 0.56, rectRadius: 0.06, fill: { color: i % 2 ? "F7F8FA" : "FFFFFF" }, line: { color: "E4E9F0", width: 1 } });
  dot(s, MX + 0.26, y + 0.21, i === 4 ? GREEN : BLUE, 0.14);
  s.addText(t, { x: MX + 0.6, y, w: 2.4, h: 0.56, fontFace: H, fontSize: 14.5, bold: true, color: PINK, margin: 0, valign: "middle" });
  s.addText(d, { x: MX + 3.1, y, w: 8.4, h: 0.56, fontFace: B, fontSize: 13, color: "5C6472", margin: 0, valign: "middle" });
});
s.addText("localhost:8080/dashboard  ·  no build step, no CDN, renders in the viewer's theme", {
  x: MX, y: 6.32, w: 11.5, h: 0.4, fontFace: M, fontSize: 11.5, color: "8A92A1", margin: 0,
});
note(s, "Open it live rather than screenshotting. The Ask tab does a real vector search plus a Vertex call — give it about twenty seconds.");

// ── 13. what works ──────────────────────────────────────────────────────────
s = p.addSlide(); light(s);
kicker(s, "Status  ·  built", "1F8A5F");
title(s, "What works today");
s.addText("Every figure below is from a verification run against a real corpus — 25 of 25 end-to-end checks passing.", {
  x: MX, y: 1.56, w: 11.5, h: 0.35, fontFace: B, fontSize: 14, color: "5C6472", margin: 0,
});
const built = [
  ["Ingestion", "144 records staged from Gmail, Calendar, Meet"],
  ["Pipeline", "96 meetings written, zero extraction failures"],
  ["Memory layers", "263 facts, all embedded; 768-dim search working"],
  ["Graph algorithms", "PageRank, communities, quality — 604 nodes scored"],
  ["API and dashboard", "17 of 17 endpoints, 7 tabs, no console errors"],
  ["Jira push", "23 tickets created with confidence and dedup gates"],
  ["Dev agent", "PR opened autonomously, gates and reviewer passed"],
  ["Terraform", "821 lines, durable and ephemeral tiers — written"],
];
built.forEach(([h, d], i) => {
  const x = MX + (i % 2) * 6.0, y = 2.12 + Math.floor(i / 2) * 1.05;
  s.addShape(p.ShapeType.roundRect, { x, y, w: 5.55, h: 0.86, rectRadius: 0.07, fill: { color: "E2F3EA" }, line: { color: "CBE7D8", width: 1 } });
  dot(s, x + 0.3, y + 0.36, "1F8A5F", 0.15);
  s.addText(h, { x: x + 0.62, y: y + 0.08, w: 4.7, h: 0.34, fontFace: H, fontSize: 14.5, bold: true, color: "14523A", margin: 0, valign: "middle" });
  s.addText(d, { x: x + 0.62, y: y + 0.42, w: 4.75, h: 0.36, fontFace: B, fontSize: 12, color: "2C6B50", margin: 0, valign: "middle" });
});
note(s, "Emphasise that these are measured, not estimated. The verification script runs 25 checks across staging, graph, memory, invariants, nightly output, Jira and every endpoint.");

// ── 14. pending ─────────────────────────────────────────────────────────────
s = p.addSlide(); light(s);
kicker(s, "Status  ·  pending", "B3641A");
title(s, "What is not done");
s.addShape(p.ShapeType.roundRect, { x: MX, y: 1.6, w: 11.8, h: 1.12, rectRadius: 0.09, fill: { color: "FBE6E8" }, line: { color: "F2CDD1", width: 1 } });
dot(s, MX + 0.36, 2.02, "B3323C", 0.17);
s.addText("Nothing is deployed", { x: MX + 0.7, y: 1.76, w: 5, h: 0.42, fontFace: H, fontSize: 19, bold: true, color: "8C2129", margin: 0, valign: "middle" });
s.addText("No Terraform has been applied. No Cloud Run service or job exists. Everything you have seen runs on a laptop against local Postgres and Memgraph, using Vertex for inference.", {
  x: MX + 0.7, y: 2.16, w: 10.7, h: 0.5, fontFace: B, fontSize: 13.5, color: "8C2129", margin: 0,
});
const gaps = [
  ["Jira status flowing back", "Wired to the drain, but the ingest job has never run — every action item still reads \"created\""],
  ["Scope gate for the agent", "It also edited an unrelated passing test. Seven gates allowed it, correctly by their own rules"],
  ["Cloud Run Job timeout", "The drain took 56 min for 144 records; jobs default to 10 min. Needs an explicit timeout"],
  ["Cross-source duplicates", "A calendar invite and the Gmail thread about it still produce two meetings"],
  ["Sequential embeddings", "Three independent passes run one after another — about 40s per meeting recoverable"],
];
gaps.forEach(([h, d], i) => {
  const y = 2.98 + i * 0.74;
  s.addShape(p.ShapeType.roundRect, { x: MX, y, w: 11.8, h: 0.62, rectRadius: 0.06, fill: { color: "FBEEE0" }, line: { color: "F0DCC0", width: 1 } });
  dot(s, MX + 0.28, y + 0.24, "B3641A", 0.14);
  s.addText(h, { x: MX + 0.62, y, w: 3.3, h: 0.62, fontFace: B, fontSize: 13.5, bold: true, color: "8A4A12", margin: 0, valign: "middle" });
  s.addText(d, { x: MX + 4.0, y, w: 7.6, h: 0.62, fontFace: B, fontSize: 12, color: "8A4A12", margin: 0, valign: "middle" });
});
note(s, "Be direct about this. The architecture is written and tested; it has never been stood up. Deploying is the next real milestone.");

// ── 15. bugs ────────────────────────────────────────────────────────────────
s = p.addSlide(); dark(s);
kicker(s, "Hand this over", AMBER);
title(s, "Where this codebase hides failure", true);
s.addShape(p.ShapeType.roundRect, { x: MX, y: 1.6, w: 11.8, h: 1.32, rectRadius: 0.09, fill: { color: "33260F" }, line: { color: "4A3714", width: 1 } });
s.addText("Green tests, wrong data", { x: MX + 0.42, y: 1.76, w: 6, h: 0.38, fontFace: H, fontSize: 17, bold: true, color: AMBER, margin: 0, valign: "middle" });
s.addText("A test asserted extract_overrides() returned the right dict, and it did. The bug was one layer up: model_copy(update=…) does not validate, so attendees stayed raw dicts and getattr silently returned defaults. Every attendee vanished into the review queue — no exception, no log line.", {
  x: MX + 0.42, y: 2.16, w: 11.0, h: 0.68, fontFace: B, fontSize: 12.5, color: "E8D5B0", margin: 0,
});
const bugs = [
  ["Ground truth thrown away", "Calendar returns exact invitee addresses; the adapter passed a count. Person nodes went 6 to 67"],
  ["Producer and consumer disagreed", "Tickets were created unlabelled; the agent selected on that exact label. Each half looked correct alone"],
  ["A query that matched nothing", "Candidate JQL required openSprints() — matches nothing on a Kanban board"],
  ["Counting values, not items", "collect(DISTINCT a.done) reported three completed actions as one"],
  ["Order-dependence, no retry", "Items extracted before any Person existed could never match an owner. Nothing re-tried them"],
];
bugs.forEach(([h, d], i) => {
  const y = 3.12 + i * 0.66;
  dot(s, MX + 0.06, y + 0.24, AMBER, 0.13);
  s.addText(h, { x: MX + 0.4, y, w: 3.9, h: 0.54, fontFace: B, fontSize: 13, bold: true, color: TEXT, margin: 0, valign: "middle" });
  s.addText(d, { x: MX + 4.4, y, w: 7.4, h: 0.54, fontFace: B, fontSize: 12, color: MUTED, margin: 0, valign: "middle" });
});
s.addText("The pattern: none were caught by tests. All were caught by running it and reading the output.", {
  x: MX, y: 6.52, w: 11.5, h: 0.4, fontFace: B, fontSize: 14, bold: true, color: GREEN, margin: 0,
});
note(s, "This is the most valuable slide for a new maintainer. The lesson is that this system's failures are silent — they produce plausible data rather than exceptions.");

// ── 16. start here ──────────────────────────────────────────────────────────
s = p.addSlide(); dark(s);
[[BLUE, 0], [GREEN, 0.26], [AMBER, 0.52]].forEach(([c, dx]) => dot(s, MX + dx, 1.5, c, 0.17));
s.addText("Where to start", {
  x: MX, y: 1.84, w: 9, h: 0.9, fontFace: H, fontSize: 38, bold: true, color: TEXT, margin: 0, valign: "middle",
});
const start = [
  ["1", "Read CLAUDE.md", "The authoritative spec — boundaries, schema, conventions"],
  ["2", "Run make doctor", "Tells you exactly what is missing before anything fails"],
  ["3", "Run make demo", "Tier 0 — the whole pipeline offline, no credentials at all"],
  ["4", "Open the dashboard", "localhost:8080/dashboard — click every tab"],
  ["5", "Skim docs/DECISIONS.md", "24 ADRs. Why things are the way they are"],
];
start.forEach(([n, h, d], i) => {
  const y = 2.98 + i * 0.72;
  s.addText(n, { x: MX, y, w: 0.4, h: 0.6, fontFace: M, fontSize: 13, color: BLUE, margin: 0, valign: "middle" });
  s.addText(h, { x: MX + 0.46, y, w: 3.6, h: 0.6, fontFace: B, fontSize: 15, bold: true, color: TEXT, margin: 0, valign: "middle" });
  s.addText(d, { x: MX + 4.2, y, w: 7.6, h: 0.6, fontFace: B, fontSize: 13, color: MUTED, margin: 0, valign: "middle" });
});
s.addText("Tests run offline. No account anywhere is needed to see it work.", {
  x: MX, y: 6.66, w: 11.5, h: 0.4, fontFace: B, fontSize: 13.5, color: FAINT, margin: 0, italic: true,
});
note(s, "Close here. The fastest path to understanding is running tier 0 and clicking through the dashboard — it needs nothing but a clone and a venv.");

p.writeFile({ fileName: "meeting-notes-gcp-KT.pptx" }).then(f => console.log("wrote", f));
