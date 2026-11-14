import sys
from common import write, pill, GRAPH_JS
R = sys.argv[1]

# ---------------- Actions ----------------
write(R, "Button", 'group="Actions" height=150', """
<div class="ng-col ng-col--loose">
 <div class="ng-row">
  <button class="ng-btn ng-btn--steer">Approve plan</button>
  <button class="ng-btn">Pause</button>
  <button class="ng-btn">Finish now</button>
  <button class="ng-btn ng-btn--quiet">Cancel</button>
  <button class="ng-btn ng-btn--danger">Delete investigation</button>
  <button class="ng-btn" disabled>Resume</button>
  <button class="ng-btn is-sent">Pausing…</button>
 </div>
 <div class="ng-row">
  <button class="ng-btn ng-btn--sm ng-btn--steer">Instruct</button>
  <button class="ng-btn ng-btn--sm">Ignore branch <span class="ng-kbd">X</span></button>
  <button class="ng-btn ng-btn--sm">Go deeper <span class="ng-kbd">D</span></button>
  <button class="ng-btn ng-btn--sm ng-btn--quiet">Fit graph</button>
 </div>
 <p class="ng-small ng-muted">One steer button per view. <span class="ng-mono">is-sent</span> is the state between the click and the event that confirms it.</p>
</div>
""", """
# Button

Triggers a command. Class `ng-btn`, with one modifier: `ng-btn--steer` (the single primary action of a view), `ng-btn--quiet` (toolbar and dismissals), `ng-btn--danger` (the two irreversible actions: delete an investigation, re-run a node). Add `ng-btn--sm` inside panels, toolbars and node rows.

You provide the label and, optionally, a trailing `ng-kbd` shortcut hint.

- Label with the verb the event log will use: "Pause", "Ignore branch", "Approve plan". Never "OK" or "Submit".
- At most one `ng-btn--steer` per view. On the board it is the composer's "Send instruction"; in plan review it is "Approve plan".
- A command is acknowledged when recorded, not when it takes effect. After the click, set `is-sent` and the present participle ("Pausing…") until the matching event arrives. Never flip the status pill optimistically.
- `disabled` only for actions that cannot apply in the current state, and say why in a tooltip ("Nothing is paused").
""")

write(R, "Field", 'group="Actions" height=600', """
<div class="ng-col ng-col--loose" style="max-width:640px">
 <div class="ng-field"><label class="ng-field__label" for="f1">Spending limit</label>
  <input id="f1" class="ng-input ng-input--mono" value="$5.00" style="max-width:140px">
  <span class="ng-field__hint">Reaching it pauses the investigation and asks you what to do.</span></div>
 <div class="ng-field"><span class="ng-field__label">Effort</span>
  <div class="ng-row"><div class="ng-seg"><button class="ng-seg__opt">Low</button><button class="ng-seg__opt is-on">Medium</button><button class="ng-seg__opt">High</button></div>
  <span class="ng-mono ng-muted">depth 4 · 40 nodes · 8 sources/node · 2 independent sources to confirm</span></div></div>
 <div class="ng-field"><span class="ng-field__label">OpenRouter API key</span>
  <div class="ng-keyfield"><span class="ng-pill ng-pill--ok"><i>✓</i>Key set</span><span class="ng-mono ng-faint ng-grow">Stored on this machine. It cannot be shown again.</span><button class="ng-btn ng-btn--sm">Replace</button></div></div>
 <div class="ng-field"><label class="ng-field__label" for="f2">Excluded domains</label>
  <input id="f2" class="ng-input ng-input--mono is-error" value="reddit.com, quora" >
  <span class="ng-field__hint is-error">"quora" is not a domain. Write it as quora.com.</span></div>
 <label class="ng-toggle is-on"><span class="ng-toggle__track"></span>Always fetch pages again for this investigation</label>
 <div class="ng-field" style="max-width:380px"><label class="ng-field__label" for="f3">Strong model</label>
  <div class="ng-combo"><input id="f3" class="ng-input ng-input--mono" role="combobox" aria-expanded="true" value="son 5.5">
   <ul class="ng-menu ng-combo__list" role="listbox">
    <li class="ng-menu__item is-hover" role="option"><b>anthropic/claude-<mark>son</mark>net-<mark>5.5</mark></b><span>$3 / $15</span><small>Anthropic: Claude Sonnet 5.5 · 1M context</small></li>
    <li class="ng-menu__item" role="option"><b>openai/gpt-<mark>5.5</mark>-<mark>s</mark>w<mark>on</mark></b><span>no price</span><small>OpenAI: GPT-5.5 Swon · 400k context</small></li>
   </ul></div></div>
</div>
""", """
# Field

Form controls for the new-investigation form and Settings: `ng-field` wraps a `ng-field__label`, one control and a `ng-field__hint`. Controls: `ng-input` (add `ng-input--mono` for money, domains, model ids), `ng-textarea`, `ng-select`, `ng-seg` (segmented choice), `ng-toggle`, `ng-keyfield` (write-only secret), `ng-combo` (searchable picker).

You provide the label, the value and a hint that states the consequence of the setting.

- Inputs sit in `sunken` with a `line-strong` border. Errors switch the border and hint to `danger` and say how to fix the value.
- `ng-seg` is for Effort and model presets only: three options, mutually exclusive, with the resulting budget shown beside it in `ng-mono`.
- `ng-keyfield` never renders a key. It shows "Key set" or "No key" and a Replace button. Replace swaps the row for an empty `ng-input--mono` that is cleared on save.
- Settings save on change. There is no Save button; show "Saved" in the hint for two seconds.
- `ng-combo` picks one value from a list too long for `ng-select`, such as a provider's models. An `ng-input--mono` with `role="combobox"` over an `ng-menu ng-combo__list`. Typing filters by fuzzy match: words in any order, letters in order with gaps; matched letters are `mark`ed. Each `ng-menu__item` holds the id in `b`, a right-aligned fact in `span` (price), and a `small` line (name, context). Arrow keys move `is-hover`, Enter picks, Escape restores the saved value. Picking saves at once, like any other setting.
""")

# ---------------- Status ----------------
inv = [("", "○", "Draft"), ("steer", "✎︎", "Plan review"), ("live", "●", "Running"), ("warn", "‖", "Paused · by you"), ("warn", "‖", "Paused · spending limit"), ("live", "◐", "Synthesising"), ("ok", "✓", "Completed"), ("", "■", "Stopped")]
node = [("ghost", "◌", "Proposed"), ("danger ng-pill--hollow", "⊘", "Rejected"), ("", "○", "Pending"), ("live", "●", "Running"), ("live ng-pill--hollow", "◔", "Waiting on children"), ("warn", "‖", "Paused"), ("ok", "✓", "Completed"), ("danger", "✕", "Failed")]
inc = [("", "", "Included"), ("steer ng-pill--hollow", "⦸", "Ignored by you"), ("ghost", "↺", "Superseded by re-plan")]
def pills(rows): return "".join(pill(k, g, t) if g else f'<span class="ng-muted ng-small">{t} (no pill)</span>' for k, g, t in rows)
write(R, "StatusPill", 'group="Status" height=190', f"""
<div class="ng-col ng-col--loose">
 <div class="ng-col"><span class="ng-label">Investigation</span><div class="ng-row">{pills(inv)}</div></div>
 <div class="ng-col"><span class="ng-label">Node · execution</span><div class="ng-row">{pills(node)}</div></div>
 <div class="ng-col"><span class="ng-label">Node · inclusion</span><div class="ng-row">{pills(inc)}</div></div>
</div>
""", """
# StatusPill

Shows one lifecycle state as a glyph and a word. Class `ng-pill` plus a tone: `--live`, `--ok`, `--warn`, `--danger`, `--steer`, or none (idle); `--ghost` makes the border dashed, `--hollow` drops the wash.

You provide the state. The glyph, word and tone are fixed by the tables below and never vary by screen.

| Investigation | Glyph | Tone |
|---|---|---|
| Draft | ○ | idle |
| Plan review | ✎︎ | steer (it is waiting for the user) |
| Running | ● (pulses) | live |
| Paused | ‖ | warn, always with its origin: "by you", "spending limit", "model service unavailable", "search unavailable", "key rejected" |
| Synthesising | ◐ | live |
| Completed | ✓ | ok |
| Stopped | ■ | idle |

| Node execution | Glyph | Tone |
|---|---|---|
| Proposed | ◌ | idle, ghost |
| Rejected | ⊘ | danger, hollow |
| Pending | ○ | idle |
| Running | ● (pulses) | live |
| Waiting on children | ◔ | live, hollow |
| Paused | ‖ | warn |
| Completed | ✓ | ok |
| Failed | ✕ | danger |

Inclusion is a second, independent pill shown only when a node is not Included: "Ignored by you" (steer, hollow) or "Superseded by re-plan" (ghost).

- Always glyph plus word. Colour never carries a state alone.
- A paused investigation always says who paused it. A system pause repeats its reason in the SystemPause banner.
- Do not invent states or soften words ("In progress", "Done"). Use the domain vocabulary exactly.
""")

write(R, "ActivityLine", 'group="Status" height=210', """
<div class="ng-col" style="max-width:620px">
 <div class="ng-activity"><span class="ng-activity__verb">Planning</span><span class="ng-activity__what">3 searches, then compare first-hand accounts</span></div>
 <div class="ng-activity"><span class="ng-activity__verb">Searching</span><span class="ng-activity__what">"great wall" naked eye orbit astronaut statement</span></div>
 <div class="ng-activity"><span class="ng-activity__verb">Reading</span><span class="ng-activity__what">nasa.gov/vision/space/workinginspace/great_wall.html</span></div>
 <div class="ng-activity"><span class="ng-activity__verb">Extracting</span><span class="ng-activity__what">4 claims from esa.int/…/Great_Wall_of_China_seen_from_space</span></div>
 <div class="ng-activity"><span class="ng-activity__verb">Reasoning</span><span class="ng-activity__what">2 sources disagree on what the 2004 photo shows</span></div>
 <div class="ng-activity"><span class="ng-activity__verb">Aggregating</span><span class="ng-activity__what">3 of 3 children complete</span></div>
 <div class="ng-activity"><span class="ng-activity__verb">Waiting</span><span class="ng-activity__what">on 2 children: D2b, D2c</span></div>
 <div class="ng-activity"><span class="ng-activity__verb is-retry">Retrying 2 of 3</span><span class="ng-activity__what">esa.int timed out · full browser next</span></div>
</div>
""", """
# ActivityLine

One line saying what a running node is doing right now: an uppercase verb in `live` and the object in `ink-muted`, all in `mono`. Class `ng-activity` with `ng-activity__verb` and `ng-activity__what`.

You provide the activity and its detail from the latest activity event.

- Verbs are the eight domain activities only: Planning, Searching, Reading, Extracting, Reasoning, Aggregating, Waiting, Retrying n of m.
- The detail is always concrete: the query in quotes, the page as host and path, the count of claims. Never "Working…".
- Retrying uses `is-retry` (`warn`) and names the next fetch step: "full browser next", "hardened browser next", "last attempt".
- One line, truncated with an ellipsis at the end so the host stays visible. The full text is in the node's trail.
- Streamed model text is not an activity line. It appears only in the inspector's Trail tab while the node is open and is never stored.
""")

claims = [("ok", "✓✓", "Confirmed"), ("ok ng-pill--hollow", "✓", "Supported"), ("", "?", "Unverified"), ("warn", "⇄", "Contested"), ("danger", "✕", "Refuted")]
write(R, "ClaimStatus", 'group="Status" height=170', f"""
<div class="ng-col ng-col--loose">
 <div class="ng-col"><span class="ng-label">Claim status</span><div class="ng-row">{pills(claims)}</div></div>
 <div class="ng-col"><span class="ng-label">Premise outcome</span><div class="ng-row">{pill("ok", "✓", "Premise confirmed")}{pill("danger", "✕", "Premise refuted")}{pill("", "?", "Could not be verified")}</div></div>
 <div class="ng-col"><span class="ng-label">Source credibility</span><div class="ng-row"><span class="ng-tag ng-tag--solid">PRIMARY</span><span class="ng-tag">REPUTABLE</span><span class="ng-tag ng-tag--dashed">WEAK</span><span class="ng-mono ng-muted">2 independent · 5 pages (4 repeat one wire report)</span></div></div>
</div>
""", """
# ClaimStatus

The evidence vocabulary: five claim statuses, three premise outcomes and three source credibility classes. Statuses are `ng-pill`; credibility is `ng-tag` (`--solid` Primary, plain Reputable, `--dashed` Weak).

You provide the status computed by the evidence service. The UI never derives one.

| Status | Glyph | Tone | Meaning |
|---|---|---|---|
| Confirmed | ✓✓ | ok | enough independent sources for the chosen effort |
| Supported | ✓ | ok, hollow | supported, below the confirmation bar |
| Unverified | ? | idle | single or weak source only |
| Contested | ⇄ | warn | credible sources disagree |
| Refuted | ✕ | danger | credible evidence shows it is false |

- Source counts state independence, not pages: "2 independent · 5 pages". Independence is by origin.
- Credibility weight goes from filled to outline to dashed, so it reads without colour.
- A refuted premise is `danger` wherever it appears and is repeated at the top of the report under "Where you were wrong".
- Confidence on a verdict uses `ng-conf` (three bars and a word), not these pills.
""")

write(R, "BudgetMeter", 'group="Status" height=120', """
<div class="ng-row" style="gap:var(--space-5);align-items:flex-start">
 <div class="ng-meter" style="width:150px"><div class="ng-meter__top"><span class="ng-label">Spend</span><span class="ng-meter__val">$1.84 <span>/ $5.00</span></span></div><div class="ng-meter__track"><div class="ng-meter__fill" style="width:37%"></div></div></div>
 <div class="ng-meter" style="width:120px"><div class="ng-meter__top"><span class="ng-label">Nodes</span><span class="ng-meter__val">16 <span>/ 40</span></span></div><div class="ng-meter__track"><div class="ng-meter__fill" style="width:40%"></div></div></div>
 <div class="ng-meter" style="width:100px"><div class="ng-meter__top"><span class="ng-label">Depth</span><span class="ng-meter__val">3 <span>/ 4</span></span></div><div class="ng-meter__track"><div class="ng-meter__fill" style="width:75%"></div></div></div>
 <div class="ng-meter ng-meter--warn" style="width:150px"><div class="ng-meter__top"><span class="ng-label">Spend</span><span class="ng-meter__val">$4.31 <span>/ $5.00</span></span></div><div class="ng-meter__track"><div class="ng-meter__fill" style="width:86%"></div></div></div>
 <div class="ng-meter ng-meter--danger" style="width:150px"><div class="ng-meter__top"><span class="ng-label">Spend</span><span class="ng-meter__val">$5.00 <span>/ $5.00</span></span></div><div class="ng-meter__track"><div class="ng-meter__fill" style="width:100%"></div></div></div>
</div>
""", """
# BudgetMeter

A used-of-limit readout with a 4px bar: spend against the spending limit, nodes against the node limit, depth against the depth limit. Class `ng-meter`; add `ng-meter--warn` from 80% and `ng-meter--danger` at the limit.

You provide the label, the spent value and the limit.

- Money is always two decimals in `mono` with tabular figures. Limits are shown in `ink-faint` after a slash.
- The board header shows three meters: Spend, Nodes, Depth. The inspector shows the selected branch's own Spend and Nodes.
- If a model has no known price, append "≈" before the spend and link to Settings → Models. An estimate is never shown as exact.
- At the spending limit the meter turns `danger` and the SystemPause banner appears. The meter alone never explains a pause.
""")

# ---------------- Graph ----------------
def gnode(cls, kind, nid, state, q, sub="", extra=""):
    s = f'<div class="ng-node__sub">{sub}</div>' if sub else ""
    return f'<div class="ng-node ng-node--{cls}">{extra}<div class="ng-node__top"><span class="ng-node__kind">{kind}</span><span>{nid}</span><span class="ng-node__state">{state}</span></div><div class="ng-node__q">{q}</div>{s}</div>'
gn = "".join([
 gnode("proposed", "DEEP", "N1", "◌ Proposed", "School textbooks, 1950–2000"),
 gnode("rejected", "DEEP", "N2", "⊘ Rejected", "History of the Wall's construction"),
 gnode("pending", "VER", "V1", "○ Pending", "Re-check naked-eye resolution at 400 km", "after D3"),
 gnode("running", "DEEP", "D2b", '<span class="ng-pulse">●</span> Running', "Leroy Chiao photograph, 2004", "EXTRACTING 4 claims · nasa.gov"),
 gnode("waiting", "DEEP", "D2", "◔ Waiting", "What astronauts report", "2 of 4 children complete", '<span class="ng-node__mark">✎︎ 1</span><span class="ng-node__fold">−</span>'),
 gnode("paused", "DEEP", "D3", "‖ Paused", "What limits visibility: width, contrast, acuity"),
 gnode("done", "PRM", "P1", "✓ Completed", "Visible to the naked eye from low Earth orbit", "Premise refuted · high"),
 gnode("failed", "DEEP", "D5", "✕ Failed", "Chinese-language press coverage, 2003", "No route left · re-run"),
 gnode("excluded", "DIV", "D4", "⦸ Ignored", "Other structures visible from orbit"),
 gnode("excluded", "DEEP", "D2x", "↺ Superseded", "Space-agency press releases"),
 gnode("done is-selected", "DEEP", "D1a", "✓ Completed", "Pre-spaceflight origins, 1754–1932", "4 claims · medium"),
])
write(R, "GraphNode", 'group="Graph" height=330', f"""
<div style="display:grid;grid-template-columns:repeat(auto-fill,172px);gap:var(--space-5) var(--space-4)">{gn}</div>
""", """
# GraphNode

One node of the task graph: 172px wide, three lines. Line 1 is kind code, node id and state; line 2 the question (two lines at most); line 3 the activity while running, or the verdict summary once complete. Class `ng-node` plus `ng-node--proposed | rejected | pending | running | waiting | paused | done | failed | excluded`, and `is-selected`.

You provide the node's kind, id, question, execution status, inclusion and its latest activity or verdict.

| Kind | Code |
|---|---|
| Premise check | PRM |
| Divergent | DIV |
| Deep-dive | DEEP |
| Verification | VER |
| Synthesis | SYN |

- Running fills with `live-wash` and a `live` border; its glyph pulses. Waiting keeps the `live` border on a plain surface. Completed stays neutral with an `ok` state word, so a finished graph is calm and the live work stands out.
- Proposed is dashed and unfilled: it does not exist until the orchestrator approves it. Rejected is dashed, struck through, and keeps its reason in the inspector.
- Ignored and Superseded use `ng-node--excluded`: hatched and greyed, never hidden. Their edges use `ng-edge--off`.
- `ng-node__mark` ("✎︎ 1") in `steer` shows that the user has instructed this node, with the count. Descendants that only inherit the instruction show no mark; the inspector lists it as inherited.
- `ng-node__fold` collapses a branch ("−") or shows the hidden count ("+4").
- Selection is a 2px `ink` outline. It is never `steer` or `live`: selecting is not steering.
- The question is never rewritten or shortened by the UI beyond the two-line clamp. The full text and the justification are in the inspector.
""")

write(R, "GraphCanvas", 'group="Graph" height=400', """
<div class="ng-col">
<div id="g" class="ng-canvas" style="height:330px;border:1px solid var(--line);border-radius:var(--radius-md)"></div>
<div class="ng-legend">
 <span><svg viewBox="0 0 36 8"><path class="ng-edge" d="M0 4H36"/></svg>Decomposition: parent split its question</span>
 <span><svg viewBox="0 0 36 8"><path class="ng-edge ng-edge--dep" d="M0 4H36"/></svg>Dependency: waits for, and receives, the result</span>
 <span><svg viewBox="0 0 36 8"><path class="ng-edge ng-edge--live" d="M0 4H36"/></svg>Path to running work</span>
 <span><svg viewBox="0 0 36 8"><path class="ng-edge ng-edge--off" d="M0 4H36"/></svg>Excluded branch</span>
</div></div>
<script>""" + GRAPH_JS + """
ngGraph(document.getElementById('g'), [
 {id:'R', k:'SYN', s:'waiting', st:'◔ Waiting', q:'Why is the Great Wall visible from space?', x:16, y:124, sub:'3 of 5 children complete'},
 {id:'P1', k:'PRM', s:'done', st:'✓ Completed', q:'Visible to the naked eye from low Earth orbit', x:236, y:12, sub:'Premise refuted · high'},
 {id:'D2', k:'DEEP', s:'waiting', st:'◔ Waiting', q:'What astronauts report', x:236, y:112, sub:'1 of 2 children complete', mark:'✎︎ 1', fold:'−'},
 {id:'D3', k:'DEEP', s:'done', st:'✓ Completed', q:'What limits visibility', x:236, y:212, fold:'+3'},
 {id:'D2a', k:'DEEP', s:'done', st:'✓ Completed', q:'Yang Liwei, 2003', x:456, y:60},
 {id:'D2b', k:'DEEP', s:'running', st:'● Running', q:'Leroy Chiao photograph, 2004', x:456, y:138, sub:'EXTRACTING 4 claims · nasa.gov'},
 {id:'D2x', k:'DEEP', s:'excluded', st:'↺ Superseded', q:'Space-agency press releases', x:456, y:238},
 {id:'V1', k:'VER', s:'pending', st:'○ Pending', q:'Re-check resolution at 400 km', x:676, y:212}
],[['R','P1'],['R','D2','live'],['R','D3'],['D2','D2a'],['D2','D2b','live'],['D2','D2x','off'],['D3','V1','dep']]);
</script>
""", """
# GraphCanvas

The live task graph: nodes laid out left to right by depth on a dotted 16px ground, joined by two kinds of edge. Class `ng-canvas` holding one `svg` of `ng-edge` paths and absolutely placed `ng-node` elements.

You provide node positions from the layout and the edge list. The canvas computes no research state.

- Depth runs left to right, so the root goal is always at the left edge and reading order matches the path in a node's brief.
- Decomposition is a solid `line-strong` curve from parent to child. Dependency is a dashed `ink-muted` line with an arrowhead pointing at the node that waits.
- The chain of edges from the root to each running node is `ng-edge--live`. This is the "highlight active work" aid and is on by default.
- Edges into Ignored or Superseded nodes are `ng-edge--off`.
- New nodes appear in place as Proposed (dashed) and become solid on approval. Nothing animates beyond the running glyph's pulse; with `prefers-reduced-motion` that stops too.
- Toolbar actions above the canvas: Fit, Collapse completed, Show excluded (on by default), Follow active. Collapsed branches show `ng-node__fold` with the hidden count.
- Click selects a node and opens it in the inspector. Double-click folds its branch. Right-click or `.` opens NodeActions.
""")

# ---------------- Steering ----------------
write(R, "RunControls", 'group="Steering" height=250', f"""
<div class="ng-col ng-col--loose">
 <div class="ng-row"><span style="width:150px">{pill("steer","✎︎","Plan review")}</span><button class="ng-btn ng-btn--steer">Approve plan</button><button class="ng-btn ng-btn--quiet">Discard draft</button></div>
 <div class="ng-row"><span style="width:150px">{pill("live","●","Running")}</span><button class="ng-btn">‖ Pause</button><button class="ng-btn">Finish now</button><button class="ng-btn ng-btn--quiet">Stop</button></div>
 <div class="ng-row"><span style="width:150px">{pill("warn","‖","Paused · by you")}</span><button class="ng-btn ng-btn--steer">Resume</button><button class="ng-btn">Finish now</button><button class="ng-btn ng-btn--quiet">Stop</button></div>
 <div class="ng-row"><span style="width:150px">{pill("live","◐","Synthesising")}</span><span class="ng-small ng-muted">No controls. The report is being written from the evidence store.</span></div>
 <div class="ng-row"><span style="width:150px">{pill("","■","Stopped")}</span><button class="ng-btn ng-btn--steer">Resume</button><button class="ng-btn">Finish into a report</button></div>
 <div class="ng-row"><span style="width:150px">{pill("ok","✓","Completed")}</span><button class="ng-btn">Open report</button><button class="ng-btn ng-btn--quiet">Export Markdown</button></div>
</div>
""", """
# RunControls

The investigation-level commands, shown at the right of the board header. Which buttons appear is fixed by the investigation's state.

You provide the investigation state. Each button sends one command.

| State | Controls |
|---|---|
| Plan review | **Approve plan**, Discard draft |
| Running | Pause, Finish now, Stop |
| Paused | **Resume**, Finish now, Stop |
| Synthesising | none |
| Stopped | **Resume**, Finish into a report |
| Completed | Open report, Export Markdown |

- Pause: no new work starts; running steps finish. The button reads "Pausing…" until the paused event arrives.
- Finish now: stops exploring and writes the report from what exists. The report will say it was ended early. No confirmation.
- Stop: ends execution without a report and keeps everything. It is resumable, so there is no confirmation.
- None of these asks "Are you sure?". Each is reversible or resumable, and the event log records it.
- Resume is the steer button whenever the investigation is waiting for the user.
""")

write(R, "NodeActions", 'group="Steering" height=440', """
<div class="ng-row" style="align-items:flex-start;gap:var(--space-5)">
<div class="ng-menu">
 <div class="ng-menu__item is-hover"><b>Add instruction</b><span class="ng-kbd">I</span><small>Guide this node and its 4 descendants.</small></div>
 <div class="ng-menu__item"><b>Go deeper</b><span class="ng-kbd">D</span><small>Grant this branch more budget.</small></div>
 <div class="ng-menu__item"><b>Run only this branch</b><span class="ng-kbd">F</span><small>The rest of the graph waits.</small></div>
 <div class="ng-menu__item"><b>Pause branch</b><span class="ng-kbd">Space</span><small>Running steps finish first.</small></div>
 <div class="ng-menu__sep"></div>
 <div class="ng-menu__item"><b>Ignore branch</b><span class="ng-kbd">X</span><small>Stops it and keeps its findings out of the report. You can restore it.</small></div>
 <div class="ng-menu__item is-disabled"><b>Re-run node</b><span class="ng-kbd">R</span><small>Available once the node has completed or failed.</small></div>
</div>
<div class="ng-col" style="width:300px">
 <span class="ng-label">Same menu on an ignored node</span>
 <div class="ng-menu"><div class="ng-menu__item is-hover"><b>Restore branch</b><span class="ng-kbd">X</span><small>Brings back this node and its 2 descendants with the results they already had.</small></div></div>
 <span class="ng-label" style="margin-top:var(--space-3)">Re-run asks once, inline</span>
 <div class="ng-banner ng-banner--danger"><span class="ng-banner__g">!</span><div class="ng-col ng-grow"><span class="ng-banner__t">Re-run D1a?</span><span class="ng-small">Its verdict and 4 claims are discarded. Fetched pages are reused.</span><div class="ng-row"><button class="ng-btn ng-btn--sm ng-btn--danger">Re-run node</button><button class="ng-btn ng-btn--sm ng-btn--quiet">Keep result</button></div></div></div>
</div></div>
""", """
# NodeActions

The node-level interventions, as a menu (`ng-menu`) opened from a node and as the action row at the top of the inspector. Every item is a verb, a one-line consequence and a shortcut.

You provide the selected node, its branch size and its state. The menu decides which items apply.

| Action | Key | Applies when | Effect |
|---|---|---|---|
| Add instruction | I | always, except the root once research has started | opens the InstructionComposer aimed at this node |
| Go deeper | D | node is Included | grants the branch more budget; the BudgetMeter in the inspector shows the new limit |
| Run only this branch | F | investigation is Running | everything outside the branch waits; the header shows "Running only D2 · Run everything" |
| Pause / Resume branch | Space | node is Pending, Running or Waiting / Paused | suspends or continues this branch only |
| Ignore / Restore branch | X | always | toggles inclusion for the whole branch |
| Re-run node | R | node is Completed or Failed | discards the result and runs it again |

- The consequence line always names the scope: "this node and its 4 descendants".
- Ignore, Restore, Pause, Go deeper and Run only this branch apply at once with no confirmation, because each can be undone.
- Re-run node is the one destructive node action. It asks once, inline in the inspector, with a `danger` banner. No modal.
- Items that do not apply stay visible, disabled, with the reason as their consequence line.
- After a command the item shows the `is-sent` wording ("Ignoring…") until the event arrives.
""")

write(R, "InstructionComposer", 'group="Steering" height=560', """
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:var(--space-4);align-items:start">
<div class="ng-col"><span class="ng-label">Aimed at a coordinator</span>
 <div class="ng-composer"><div class="ng-composer__head">✎︎ Instruct D2 <span>· What astronauts report · reaches 4 nodes</span></div>
 <textarea id="c1" aria-label="Instruction for D2">Only first-hand statements from people who were in orbit. Skip agency press releases.</textarea>
 <div class="ng-composer__foot"><span class="ng-grow">Takes effect at each node's next step. D2 will re-plan its children.</span><span class="ng-kbd">⌘↵</span><button class="ng-btn ng-btn--sm ng-btn--steer">Send instruction</button></div></div>
</div>
<div class="ng-col"><span class="ng-label">It reads like a conclusion</span>
 <div class="ng-composer"><div class="ng-composer__head">✎︎ Instruct P1 <span>· Visible from low Earth orbit · reaches 1 node</span></div>
 <textarea id="c2" aria-label="Instruction for P1">The wall is obviously visible, just confirm it.</textarea>
 <div class="ng-composer__foot"><span class="ng-grow ng-warn">You can change what is investigated, not what is concluded. Netgrip will check this as a hypothesis.</span><button class="ng-btn ng-btn--sm ng-btn--steer">Send anyway</button></div></div>
</div>
<div class="ng-col"><span class="ng-label">Sent, waiting for the step to end</span>
 <div class="ng-instr ng-instr--queued"><div class="ng-instr__meta"><span>You · 14:02:11</span><span>queued · applies when D2b finishes READING</span></div><div class="ng-instr__text">Only first-hand statements from people who were in orbit. Skip agency press releases.</div></div>
</div>
<div class="ng-col"><span class="ng-label">Applied: what the re-plan changed</span>
 <div class="ng-instr"><div class="ng-instr__meta"><span>You · 14:02:11</span><span>applied 14:02:19 · #0412</span></div><div class="ng-instr__text">Only first-hand statements from people who were in orbit. Skip agency press releases.</div>
 <div class="ng-diff" style="margin-top:var(--space-2)"><span class="ng-diff__k">= kept        D2a Yang Liwei, 2003 (result kept)</span><span class="ng-diff__k">= kept        D2b Leroy Chiao photograph, 2004</span><span class="ng-diff__s">↺ superseded  D2x Space-agency press releases</span><span class="ng-diff__n">+ proposed    D2c ESA Proba image, 2004: who identified it</span></div>
 <div class="ng-row" style="margin-top:var(--space-2)"><button class="ng-btn ng-btn--sm">Restore D2x</button><button class="ng-btn ng-btn--sm ng-btn--quiet">Show in graph</button></div></div>
</div>
<div class="ng-col"><span class="ng-label">Locked: the root, after research has started</span>
 <div class="ng-composer is-locked"><div class="ng-composer__head">✎︎ Instruct R <span>· the whole investigation</span></div>
 <div class="ng-composer__foot"><span class="ng-grow">The root goal cannot be re-planned once research is running. Instruct a branch, or stop and start a new investigation.</span></div></div>
</div>
</div>
""", """
# InstructionComposer

Where the user steers with words. A bordered `steer` box (`ng-composer`) with a head naming the target and reach, a textarea, and a foot that states when the instruction takes effect. It is the only place on the board that takes free text.

You provide the target node, the size of its branch, and whether the target has children (which decides the foot copy).

**Placement.** In plan review it is docked under the graph and aimed at the root. On the board it is pinned to the bottom of the inspector and aimed at the selected node. `I` focuses it; `⌘↵` sends; `Esc` returns focus to the graph and keeps the draft.

**The four states of an instruction**

1. Draft: text in the composer. Kept per node until sent or cleared.
2. Queued: the command is recorded. The instruction appears above the composer as `ng-instr--queued` with what it is waiting for ("applies when D2b finishes READING"). Instructions never interrupt a step.
3. Applied: `ng-instr` filled with `steer-wash`, stamped with the event sequence number. If the target is a coordinator, an `ng-diff` lists what the re-plan kept, superseded and proposed.
4. Inherited: on every descendant the same instruction appears as `ng-instr--inherited` with "from D2". It cannot be edited there.

**Rules**

- The head always states reach: "reaches 4 nodes". An instruction applies to the node and all its descendants.
- A re-plan applies at once, without a confirmation step. The diff is the receipt, and each superseded child has a Restore button.
- Instructions change scope and direction only. When the text reads like a conclusion, the foot turns `warn` and says so; the user may still send it, and it is treated as a hypothesis.
- Instructions are never deleted or edited after sending. A new instruction is added after the old one; the node's Instructions list shows them in order.
- The root is instructable only during plan review. After approval its composer is `is-locked` and explains what to do instead.
- Everything the user excluded this way is listed in the report under "Limits of this investigation".
""")

write(R, "Instruction", 'group="Steering" height=250', """
<div class="ng-col" style="max-width:560px">
 <div class="ng-instr"><div class="ng-instr__meta"><span>You · 14:02:11</span><span>on D2 · applied #0412</span></div><div class="ng-instr__text">Only first-hand statements from people who were in orbit. Skip agency press releases.</div></div>
 <div class="ng-instr ng-instr--inherited"><div class="ng-instr__meta"><span>Inherited from D2</span><span>You · 14:02:11</span></div><div class="ng-instr__text">Only first-hand statements from people who were in orbit. Skip agency press releases.</div></div>
 <div class="ng-instr ng-instr--inherited"><div class="ng-instr__meta"><span>Inherited from R · plan review</span><span>You · 13:48:40</span></div><div class="ng-instr__text">Leave out tourism marketing. Include what the claim's origin was.</div></div>
 <div class="ng-instr ng-instr--queued"><div class="ng-instr__meta"><span>You · 14:09:55</span><span>queued · applies at D3's next step</span></div><div class="ng-instr__text">Use the Wall's width in the Badaling section, not the average.</div></div>
</div>
""", """
# Instruction

A sent instruction, shown verbatim. Class `ng-instr` (given here, applied), `ng-instr--inherited` (dashed, from an ancestor), `ng-instr--queued` (dashed, waiting for a step boundary).

You provide the instruction text, when it was sent, the node it was given to and its application event.

- The text is the user's own words, unedited, in `ink` on `steer-wash`. Meta is `steer` in `mono-sm`.
- Order in the inspector: inherited instructions first, from the root down, then the node's own, oldest first. This is the order the agent reads them in its brief.
- Every instruction links to its event in the log by sequence number.
- The same block appears in the report's "Limits of this investigation" for any instruction that narrowed the research.
""")

write(R, "SystemPause", 'group="Steering" height=420', """
<div class="ng-col ng-col--loose" style="max-width:760px">
 <div class="ng-banner ng-banner--warn"><span class="ng-banner__g">‖</span><div class="ng-col ng-grow"><span class="ng-banner__t">Paused: the spending limit of $5.00 was reached</span><span class="ng-small">9 of 16 nodes are complete. Nothing is lost. Choose how to continue.</span>
  <div class="ng-row"><label class="ng-row ng-row--tight ng-small" for="cap">New limit <input id="cap" class="ng-input ng-input--mono" value="$8.00" style="width:84px"></label><button class="ng-btn ng-btn--sm ng-btn--steer">Raise limit and resume</button><button class="ng-btn ng-btn--sm">Finish now</button><button class="ng-btn ng-btn--sm ng-btn--quiet">Stop</button></div></div></div>
 <div class="ng-banner ng-banner--warn"><span class="ng-banner__g">‖</span><div class="ng-col ng-grow"><span class="ng-banner__t">Paused: the model service stopped responding</span><span class="ng-small">OpenRouter returned errors for 6 minutes from 02:14. Netgrip stopped retrying so it would not spend without progress.</span>
  <div class="ng-row"><button class="ng-btn ng-btn--sm ng-btn--steer">Resume</button><button class="ng-btn ng-btn--sm ng-btn--quiet">Show the errors in the log</button></div></div></div>
 <div class="ng-banner ng-banner--danger"><span class="ng-banner__g">✕</span><div class="ng-col ng-grow"><span class="ng-banner__t">Paused: the search API key was rejected</span><span class="ng-small">Tavily answered "invalid key". Replace the key, then resume.</span>
  <div class="ng-row"><button class="ng-btn ng-btn--sm ng-btn--steer">Open Settings → Keys</button><button class="ng-btn ng-btn--sm" disabled>Resume</button></div></div></div>
 <div class="ng-banner"><span class="ng-banner__g ng-live">↻</span><div class="ng-col ng-grow"><span style="font-weight:600">Picked up where it stopped</span><span class="ng-small ng-muted">Netgrip was shut down at 23:40 with 8 nodes running. They are running again and reuse the pages already fetched.</span></div><button class="ng-btn ng-btn--sm ng-btn--quiet">Dismiss</button></div>
</div>
""", """
# SystemPause

A banner (`ng-banner`) for the moments Netgrip stops or restarts on its own and the user must know why. It sits between the board header and the three panes, full width.

You provide the pause reason and origin from the pause event, and the counts for the body line.

| Reason | Tone | Actions |
|---|---|---|
| Spending limit reached | warn | Raise limit and resume (with the new limit field), Finish now, Stop |
| Model or search service unavailable | warn | Resume, Show the errors in the log |
| Key rejected or credit exhausted | danger | Open Settings → Keys; Resume stays disabled until the key changes |
| Recovered after a shutdown | neutral | Dismiss (informational; the run continued by itself) |

- The title starts with "Paused:" and states the cause in plain words. The body says what is safe ("Nothing is lost") and what Netgrip did.
- The header pill repeats the origin: "Paused · spending limit".
- The banner stays until the user acts. It is not a toast and cannot be dismissed while the investigation is paused by the system.
- A user pause shows no banner. The pill "Paused · by you" is enough.
- A page that could not be fetched never raises a banner. That is a line in the node's trail and a count in the report.
""")

# ---------------- Board ----------------
def q(n, title, meta, side="", cls=""):
    return f'<div class="ng-qrow {cls}"><span class="ng-qrow__n">{n}</span><span class="ng-qrow__q">{title}</span><span class="ng-qrow__side">{side}</span><span class="ng-qrow__meta">{meta}</span></div>'
QUEUE = f"""
<div class="ng-queue__head"><span class="ng-label ng-live">Now</span><span class="ng-queue__count">4 running · 6 slots</span></div>
{q('<span class="ng-live ng-pulse">●</span>', "D1b Textbook and media repetition", '<span class="ng-live">READING</span> britannica.com/topic/Great-Wall-of-China', "2:41")}
{q('<span class="ng-live ng-pulse">●</span>', "D2b Leroy Chiao photograph, 2004", '<span class="ng-live">EXTRACTING</span> 4 claims · nasa.gov', "1:12", "is-selected")}
{q('<span class="ng-warn">●</span>', "D2c ESA Proba image, 2004", '<span class="ng-warn">RETRYING 2 OF 3</span> esa.int timed out', "0:48")}
{q('<span class="ng-live ng-pulse">●</span>', "D3 What limits visibility", '<span class="ng-live">SEARCHING</span> "visual acuity" arcminute 400 km', "0:09")}
<div class="ng-queue__head"><span class="ng-label">Next</span><span class="ng-queue__count">3 in order</span></div>
{q("1", "V1 Re-check resolution at 400 km", "○ waits for D3 (dependency)")}
{q("2", "N1 School textbooks, 1950–2000", "◌ proposed by D1b · awaiting the orchestrator")}
{q("3", "R Synthesis", "◔ waits for D1, D2, D3, V1")}
<div class="ng-queue__head"><span class="ng-label ng-ok">Done</span><span class="ng-queue__count">6 · newest first</span></div>
{q('<span class="ng-ok">✓</span>', "D2a Yang Liwei, 2003", "Said he could not see it · high", "13:58")}
{q('<span class="ng-ok">✓</span>', "D1a Pre-spaceflight origins", "Claim predates spaceflight by 180 years · medium", "13:57")}
{q('<span class="ng-ok">✓</span>', "D1 Where does the claim come from?", "Split into 2 lines of inquiry", "13:54")}
{q('<span class="ng-danger">✕</span>', "P2 Visible from the Moon", "Premise refuted · high", "13:53")}
{q('<span class="ng-danger">✕</span>', "P1 Visible from low Earth orbit", "Premise refuted · high", "13:52")}
<div class="ng-queue__head"><span class="ng-label">Not running</span><span class="ng-queue__count">3</span></div>
{q("⦸", "D4 Other structures visible from orbit", "Ignored by you · 14:00 · Restore", "", "is-off")}
{q("↺", "D2x Space-agency press releases", "Superseded by your instruction on D2 · Restore", "", "is-off")}
{q("⊘", "N2 History of the Wall's construction", "Rejected: does not help answer the root goal", "", "is-off")}
"""
write(R, "ExecutionOrder", 'group="Board" height=700 width=320', f'<div class="ng-panel" style="width:284px;overflow:hidden">{QUEUE}</div>', """
# ExecutionOrder

The left pane of the board: the same nodes as the graph, ordered by time instead of by structure. Four sections, always in this order: **Now**, **Next**, **Done**, **Not running**. Rows are `ng-qrow` under sticky `ng-queue__head` section heads.

You provide the node list with status, activity, wait reason, verdict summary and timestamps. Order within Next comes from the scheduler, not from the UI.

| Section | Holds | Row meta | Side |
|---|---|---|---|
| Now | Running nodes | the ActivityLine | time in this run |
| Next | Pending and Proposed nodes, and coordinators waiting to aggregate, in the order they will start | why it has not started: "waits for D3 (dependency)", "waits for a free slot", "awaiting the orchestrator" | position |
| Done | Completed and Failed nodes, newest first | verdict summary and confidence, or the failure reason | time finished |
| Not running | Ignored, Superseded, Rejected and Paused nodes | who excluded it and a Restore link | none |

- The Now head shows the slots in use: "4 running · 6 slots". When the investigation is paused, Now is empty and the head reads "Nothing runs while paused".
- With "Run only this branch" on, nodes outside the branch move to Next with "waits: you are running only D2".
- A refuted premise in Done uses the `danger` cross, because the finding matters more than the fact that the node completed.
- Selecting a row selects the node in the graph and the inspector, and the graph pans to it. Selection is shared by all three panes.
- Next is the place to answer "what happens after this?". Never hide it, even when empty: "Nothing queued. The orchestrator is deciding."
""")

LOG = """
<div class="ng-log__row"><span class="ng-log__t">14:02:31</span><span class="ng-log__seq">#0419</span><span class="ng-log__who">D2c</span><span><span class="ng-warn">RETRYING 2 OF 3</span> esa.int timed out after 30 s · full browser next</span></div>
<div class="ng-log__row ng-log__row--eph"><span class="ng-log__t">14:02:30</span><span class="ng-log__seq">live</span><span class="ng-log__who">D2b</span><span>…the caption says the photo was taken with a 180 mm lens, so it is not a naked-eye</span></div>
<div class="ng-log__row"><span class="ng-log__t">14:02:27</span><span class="ng-log__seq">#0418</span><span class="ng-log__who">D2b</span><span>claim added · "Chiao photographed a section of the Wall from the ISS in November 2004" · Supported</span></div>
<div class="ng-log__row ng-log__row--orc"><span class="ng-log__t">14:02:22</span><span class="ng-log__seq">#0416</span><span class="ng-log__who">Orchestrator</span><span>approved D2c · "ESA Proba image, 2004: who identified it" · budget $0.30</span></div>
<div class="ng-log__row ng-log__row--orc"><span class="ng-log__t">14:02:20</span><span class="ng-log__seq">#0414</span><span class="ng-log__who">Orchestrator</span><span>rejected N2 · "History of the Wall's construction" · does not help answer the root goal</span></div>
<div class="ng-log__row"><span class="ng-log__t">14:02:19</span><span class="ng-log__seq">#0413</span><span class="ng-log__who">D2</span><span>re-planned · kept D2a, D2b · superseded D2x · proposed D2c</span></div>
<div class="ng-log__row ng-log__row--you"><span class="ng-log__t">14:02:11</span><span class="ng-log__seq">#0412</span><span class="ng-log__who">You</span><span>instructed D2 · "Only first-hand statements from people who were in orbit. Skip agency press releases."</span></div>
<div class="ng-log__row ng-log__row--you"><span class="ng-log__t">14:00:02</span><span class="ng-log__seq">#0398</span><span class="ng-log__who">You</span><span>ignored branch D4 · 1 node · $0.04 spent</span></div>
<div class="ng-log__row ng-log__row--sys"><span class="ng-log__t">13:59:40</span><span class="ng-log__seq">#0395</span><span class="ng-log__who">Netgrip</span><span>page unobtainable · xinhuanet.com/english/2003-10/… · 3 attempts · D2a continued with another source</span></div>
<div class="ng-log__row"><span class="ng-log__t">13:58:51</span><span class="ng-log__seq">#0391</span><span class="ng-log__who">D2a</span><span>completed · verdict: Yang said he looked and could not see it · high · $0.21</span></div>
"""
write(R, "EventLog", 'group="Board" height=290', f"""
<div class="ng-panel" style="overflow:hidden">
 <div class="ng-panel__head"><span class="ng-label">Event log</span>
  <div class="ng-row ng-row--tight"><span class="ng-tag ng-tag--solid">All</span><span class="ng-tag ng-tag--steer">You 7</span><span class="ng-tag">Orchestrator</span><span class="ng-tag">Selected node</span><span class="ng-tag">Claims</span><span class="ng-tag">Problems 2</span></div>
  <span class="ng-right ng-mono ng-faint">current to #0419</span><button class="ng-btn ng-btn--sm ng-btn--quiet">Follow ●</button></div>
 <div class="ng-log" style="padding:var(--space-1) 0">{LOG}</div>
</div>
""", """
# EventLog

The investigation's recorded history, newest first, docked under the graph. One row per durable event: time, sequence number, who, what. Class `ng-log` with `ng-log__row` and an actor modifier.

You provide events from the snapshot and the live stream. The log renders them; it never summarises.

| Actor | Modifier | Who colour |
|---|---|---|
| You | `ng-log__row--you` | `steer`, on a `steer-wash` row: every intervention is findable at a glance |
| Orchestrator | `ng-log__row--orc` | `live` |
| A node (its id) | none | `ink` |
| Netgrip (the system) | `ng-log__row--sys` | `warn`: pauses, recovery, unobtainable pages |
| Streamed model text | `ng-log__row--eph` | italic `ink-faint`, sequence "live". Not stored; it disappears on reload |

- Sentence shape: verb first, then the object, then quoted text or numbers. "instructed D2", "approved D2c", "claim added", "completed".
- Filters are tags in the head: All, You, Orchestrator, Selected node, Claims, Problems. Counts appear when non-zero.
- "current to #0419" is the last sequence number applied. After a reconnect the log fills the gap silently; if the gap is long it inserts `ng-log__gap` ("42 events while this tab was closed").
- Follow keeps the newest row in view. Scrolling turns it off; the button turns it back on.
- Clicking a row selects its node. Clicking a sequence number in an Instruction or a report citation scrolls here.
- Keys, prompts to models and page bodies never appear in the log.
""")

write(R, "Verdict", 'group="Board" height=250', """
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:var(--space-4);align-items:start">
<div class="ng-panel"><div class="ng-panel__body ng-col">
 <div class="ng-row"><span class="ng-label">Verdict</span><span class="ng-conf ng-right"><span class="ng-conf__bars"><b class="is-on"></b><b class="is-on"></b><b class="is-on"></b></span>High confidence</span></div>
 <p>Yang Liwei, China's first astronaut, said after his October 2003 flight that he looked for the Wall and could not see it.</p>
 <div class="ng-row ng-mono ng-muted"><span>3 claims</span><span>·</span><span>2 independent sources</span><span>·</span><span>$0.21</span><span>·</span><span>1 page unobtainable</span></div>
</div></div>
<div class="ng-panel"><div class="ng-panel__body ng-col">
 <div class="ng-row"><span class="ng-label">Verdict</span><span class="ng-tag ng-tag--dashed">OFF TOPIC</span><span class="ng-conf ng-right"><span class="ng-conf__bars"><b class="is-on"></b><b></b><b></b></span>Low confidence</span></div>
 <p class="ng-muted">The Wall's total length was re-measured at 21,196 km in 2012.</p>
 <p class="ng-small ng-muted">Kept out of the report: it does not bear on visibility from orbit.</p>
</div></div>
<div class="ng-panel"><div class="ng-panel__body ng-col">
 <div class="ng-row"><span class="ng-label">No verdict</span><span class="ng-pill ng-pill--danger ng-right"><i>✕</i>Failed</span></div>
 <p>Both searches returned nothing usable and the orchestrator's second approach also failed.</p>
 <div class="ng-row"><button class="ng-btn ng-btn--sm">Re-run node</button><button class="ng-btn ng-btn--sm">Add instruction</button><button class="ng-btn ng-btn--sm ng-btn--quiet">Ignore branch</button></div>
</div></div>
</div>
""", """
# Verdict

A node's short conclusion and its confidence, shown at the top of the inspector as soon as it exists. A `ng-panel` with a "Verdict" label, an `ng-conf` readout, the verdict text in `body`, and one `mono` line of counts.

You provide the verdict text, confidence, claim and source counts, spend, and any relevance flag.

- Confidence is three bars and a word: Low, Medium, High. It is never a percentage.
- The counts line reports independent sources, spend and pages that could not be obtained.
- A verdict flagged off topic keeps its text in `ink-muted`, carries the dashed "OFF TOPIC" tag and says why it is kept out of the report.
- A failed node has no verdict. Say what was tried and offer the three ways out: Re-run node, Add instruction, Ignore branch.
- The verdict is the agent's text, shown as written. The UI adds no praise, hedging or summary of its own.
""")

write(R, "ClaimCard", 'group="Board" height=420', f"""
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:var(--space-4);align-items:start">
<div class="ng-claim">
 <div class="ng-row">{pill("ok","✓✓","Confirmed")}<span class="ng-mono ng-faint ng-right">C-031 · from D2a</span></div>
 <div class="ng-claim__text">Yang Liwei said he did not see the Great Wall from orbit during Shenzhou 5.</div>
 <div class="ng-col" style="gap:2px"><span class="ng-label">Supports · 2 independent</span>
  <div class="ng-src"><span class="ng-tag ng-tag--solid">PRIMARY</span><span class="ng-src__url">nasa.gov/vision/space/workinginspace/great_wall.html</span><span>2005-05-09</span></div>
  <div class="ng-src"><span class="ng-tag">REPUTABLE</span><span class="ng-src__url">chinadaily.com.cn/en/doc/2003-10/17/…</span><span>2003-10-17</span></div>
  <div class="ng-src ng-src--lost"><span class="ng-tag ng-tag--dashed">LOST</span><span class="ng-src__url">xinhuanet.com/english/2003-10/…</span><span>unobtainable</span></div></div>
</div>
<div class="ng-claim">
 <div class="ng-row">{pill("warn","⇄","Contested")}<span class="ng-mono ng-faint ng-right">C-044 · from D2c</span></div>
 <div class="ng-claim__text">A 2004 ESA Proba satellite image shows the Great Wall.</div>
 <div class="ng-col" style="gap:2px"><span class="ng-label">Supports · 1</span>
  <div class="ng-src"><span class="ng-tag ng-tag--solid">PRIMARY</span><span class="ng-src__url">esa.int/…/Great_Wall_of_China_seen_from_space</span><span>2004-05-11</span></div>
  <span class="ng-label" style="margin-top:var(--space-1)">Contradicts · 1</span>
  <div class="ng-src ng-src--against"><span class="ng-tag ng-tag--solid">PRIMARY</span><span class="ng-src__url">esa.int/…/Great_Wall_correction</span><span>2004-05-19</span></div></div>
 <p class="ng-small ng-muted">The later page says the line in the image is a river. Published 8 days apart; the newer one is not stale.</p>
 <div class="ng-row"><span class="ng-mono ng-faint">also contradicts C-012 in D1b</span><button class="ng-btn ng-btn--sm ng-right">Verify this claim</button></div>
</div>
</div>
""", """
# ClaimCard

One atomic claim with its status and the sources for and against it. Class `ng-claim`; sources are `ng-src` rows (credibility tag, host and path, publication date).

You provide the claim text, status, id, producing node, and its supporting and contradicting sources with credibility and dates.

- Head: the ClaimStatus pill at left; the claim id and producing node at right in `mono`.
- Sources are grouped under "Supports · n independent" and "Contradicts · n". Contradicting URLs are `danger`. A page that could not be obtained is listed, struck through, tagged LOST.
- Dates are publication dates in ISO form. For time-sensitive questions, a stale source gets "retrieved 2026-11-12 · published 2019" in `warn`.
- A contradiction with a claim in another branch is named with that claim's id and node. Contradictions are shown, never resolved by the UI.
- "Verify this claim" proposes a Verification node. It is the only action on a claim.
- Clicking a source opens the stored page version used by this investigation, not the live web page.
""")

write(R, "Brief", 'group="Board" height=330', """
<div class="ng-panel" style="max-width:420px"><div class="ng-panel__body">
<dl class="ng-brief" style="margin:0">
 <dt>Root goal</dt><dd>Why is the Great Wall of China visible from space with the naked eye?</dd>
 <dt>Path</dt><dd class="ng-col" style="gap:2px"><span class="ng-muted">R → answer the question as asked</span><span class="ng-muted">D2 → first-hand reports decide whether the premise holds</span><span>D2b → the one photograph often cited as proof</span></dd>
 <dt>Why</dt><dd>If the 2004 photo needed a long lens, it does not support naked-eye visibility.</dd>
 <dt>Task</dt><dd>Establish who took the photo, with what lens, and what it shows.</dd>
 <dt>Out of scope</dt><dd class="ng-muted">Satellite and radar imagery. Other structures.</dd>
 <dt>Done when</dt><dd class="ng-muted">Lens and date are confirmed by a primary source.</dd>
 <dt>Known</dt><dd><span class="ng-mono ng-muted">C-031, C-027 · result of D2a</span></dd>
 <dt>Budget</dt><dd><span class="ng-mono">$0.14 / $0.30 · 3 / 8 sources</span></dd>
</dl></div></div>
""", """
# Brief

What a node was given: root goal, path, justification, own task, scope fence, definition of done, what is already known, and budget. A definition list, `ng-brief`.

You provide the node's stored brief. Show it as the agent received it.

- Rows, in this order: Root goal, Path, Why, Task, Out of scope, Done when, Known, Budget. Instructions are shown separately, as Instruction blocks, directly under the brief.
- Root goal is the user's prompt, verbatim, on every node at every depth.
- Path lists one line per ancestor; ancestors in `ink-muted`, the node itself in `ink`.
- "Why" is the node's justification. It is the first thing to read when judging whether a node has drifted, so it also appears under the question at the top of the inspector.
- Known lists claim ids and dependency results, not their text. Each is a link.
- The brief is read-only. To change a node's direction, add an instruction.
""")

# ---------------- Report ----------------
write(R, "ReportStatement", 'group="Report" height=330', f"""
<div class="ng-report">
 <section><h2 class="ng-title">The answer</h2>
 <p>It is not. No astronaut has reported seeing the Great Wall unaided from low Earth orbit<a class="ng-cite is-open" href="#c31">C-031</a><a class="ng-cite" href="#c27">C-027</a>, and the Wall is too narrow to resolve by eye from 400 km<a class="ng-cite" href="#c52">C-052</a>. <span class="ng-hedge">One 2004 photograph may show a section of it</span><a class="ng-cite" href="#c40">C-040</a>, taken through a 180 mm lens.</p>
 <div class="ng-well"><span class="ng-ink">C-031</span> · Confirmed · 2 independent sources · from D2a Yang Liwei, 2003 · nasa.gov, chinadaily.com.cn</div></section>
 <section><div class="ng-banner ng-banner--danger"><span class="ng-banner__g">✕</span><div class="ng-col ng-grow"><span class="ng-banner__t">Where you were wrong</span><span>Your question assumed the Wall is visible from space with the naked eye. The evidence refutes that.<a class="ng-cite" href="#p1">P1</a></span></div></div></section>
</div>
""", """
# ReportStatement

Report prose in which every statement carries its claims. Class `ng-report`; citations are `ng-cite` chips with the claim id; statements below Confirmed are wrapped in `ng-hedge`.

You provide the stored report structure: statements with the claim ids they rest on.

- Report text is `body` at 15/24 in a 680px column. Section titles use `title`.
- Every sentence that states a fact ends with at least one `ng-cite`. Clicking one opens the claim inline in an `ng-well` (status, independent sources, producing node, hosts) and selects the node on the board.
- A statement whose claim is Supported, Unverified or Contested gets the dashed `warn` underline (`ng-hedge`) and wording that says so: "may", "one source reports". It is never written as plain fact.
- "Where you were wrong" is a `danger` banner directly under the answer whenever a premise was refuted. It quotes the assumption and cites the premise node.
- Section order is fixed: The answer, Where you were wrong, Key findings, What could not be verified, Limits of this investigation.
""")
print("components ok")
