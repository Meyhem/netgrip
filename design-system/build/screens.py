import sys
from common import write, pill, GRAPH_JS
from components import QUEUE, LOG
R = sys.argv[1]

def top(active, pools=True):
    nav = "".join(f'<a href="#" class="{"is-on" if n == active else ""}">{n}</a>' for n in ["Investigations", "Settings"])
    p = '<div class="ng-pools"><span>models <b>5</b>/8</span><span>search <b>1</b>/4</span><span>browsers <b>4</b>/6</span><span>today <b>$3.12</b></span></div>' if pools else ""
    return f'<header class="ng-top"><span class="ng-brand">net<i>grip</i></span><nav class="ng-nav">{nav}</nav>{p}</header>'
def meter(label, val, lim, pct, cls="", w=130):
    return f'<div class="ng-meter {cls}" style="width:{w}px"><div class="ng-meter__top"><span class="ng-label">{label}</span><span class="ng-meter__val">{val} <span>/ {lim}</span></span></div><div class="ng-meter__track"><div class="ng-meter__fill" style="width:{pct}%"></div></div></div>'
def screen(name, h, body, readme, w=1440):
    write(R, name, f'group="Screens" page width={w} height={h}', f'<div class="ng-app" style="height:{h}px;width:{w}px">{body}</div>', readme, body_class="ng")

# ================= Investigations =================
def row(title, sub, st, effort, nodes, spend, disk, when, cls="", act=""):
    return f'<tr class="{cls}"><td><div class="ng-col" style="gap:2px"><span class="ng-heading">{title}</span><span class="ng-mono ng-muted ng-clip" style="max-width:520px">{sub}</span></div></td><td>{st}</td><td>{effort}</td><td class="is-num">{nodes}</td><td class="is-num">{spend}</td><td class="is-num">{disk}</td><td class="is-num">{when}</td><td>{act}</td></tr>'
rows = "".join([
 row("Why is the Great Wall of China visible from space with the naked eye?", '<span class="ng-live">4 running</span> · D2b EXTRACTING 4 claims · nasa.gov', pill("live", '<span class="ng-pulse">●</span>', "Running"), "Medium", "9 / 16", "$1.84 / $5.00", "38 MB", "0:22:10", "is-hover", '<button class="ng-btn ng-btn--sm">‖ Pause</button>'),
 row("Do air-source heat pumps still work below −15 °C?", "Plan ready: 2 premises, 5 lines of inquiry. Research has not started.", pill("steer", "✎︎", "Plan review"), "High", "0 / 8", "$0.06 / $10.00", "0.1 MB", "waiting", "", '<button class="ng-btn ng-btn--sm ng-btn--steer">Review plan</button>'),
 row("Compare the solid-state battery timelines carmakers announced for 2027", '<span class="ng-warn">Model service stopped responding at 02:14.</span> Nothing is lost.', pill("warn", "‖", "Paused · model service"), "High", "31 / 52", "$7.40 / $15.00", "212 MB", "3:41:07", "", '<button class="ng-btn ng-btn--sm ng-btn--steer">Resume</button>'),
 row("Is the 10,000 steps a day target based on evidence?", '<span class="ng-danger">1 premise refuted</span> · answer: partly · high confidence', pill("ok", "✓", "Completed"), "Medium", "22 / 22", "$2.95", "96 MB", "Nov 10", "", '<button class="ng-btn ng-btn--sm">Open report</button>'),
 row("Which EU countries tax unrealised crypto gains?", "Stopped by you at 14 of 30 nodes. Resume or finish into a report.", pill("", "■", "Stopped"), "Low", "14 / 30", "$0.88", "41 MB", "Nov 8", "", '<button class="ng-btn ng-btn--sm">Finish into a report</button>'),
 row("How reliable are consumer sleep trackers at staging sleep?", "Not started. Prompt and settings saved.", pill("", "○", "Draft"), "Medium", "–", "–", "0 MB", "Nov 7", "", '<button class="ng-btn ng-btn--sm">Continue</button>'),
])
screen("ScreenInvestigations", 760, top("Investigations") + f"""
<main class="ng-page"><div class="ng-page__in" style="max-width:1280px">
 <div class="ng-row"><h1 class="ng-display">Investigations</h1><span class="ng-mono ng-muted">2 active of 5 allowed · 387 MB on disk</span><button class="ng-btn ng-btn--steer ng-right">New investigation <span class="ng-kbd" style="border-color:var(--on-steer);color:var(--on-steer)">N</span></button></div>
 <div class="ng-row"><div class="ng-seg"><button class="ng-seg__opt is-on">All 6</button><button class="ng-seg__opt">Needs you 2</button><button class="ng-seg__opt">Running 1</button><button class="ng-seg__opt">Finished 2</button></div><input class="ng-input" id="search" placeholder="Search prompts and reports" style="max-width:280px" aria-label="Search"></div>
 <div class="ng-panel"><table class="ng-table"><thead><tr><th>Prompt</th><th>State</th><th>Effort</th><th style="text-align:right">Nodes</th><th style="text-align:right">Spend</th><th style="text-align:right">Disk</th><th style="text-align:right">Run time</th><th></th></tr></thead><tbody>{rows}</tbody></table></div>
 <p class="ng-small ng-muted">Disk counts shared pages for every investigation that uses them, so the column can add up to more than the total.</p>
</div></main>
""", """
# ScreenInvestigations

The home screen: every investigation as one table row, with its state, what it is doing or waiting for, and the one action that moves it forward.

**Regions**

1. Top bar: wordmark, Investigations / Settings, and the shared pools readout (`models 5/8 · search 1/4 · browsers 4/6 · today $3.12`).
2. Title row: `display` title, active count against the parallel limit, total disk, and the steer button "New investigation" (`N`).
3. Filter row: `ng-seg` with All, Needs you, Running, Finished; a search input.
4. Table: Prompt, State, Effort, Nodes, Spend, Disk, Run time, action.

**Row rules**

- Line 1 is the prompt, verbatim, in `heading`. Line 2 is `mono`: for Running, the count of running nodes and one live ActivityLine; for Plan review, what the plan holds; for Paused, the reason in `warn` and "Nothing is lost"; for Completed, refuted premises in `danger` and the answer's confidence.
- The action column holds exactly one button, chosen by state: Pause, Review plan, Resume, Open report, Finish into a report, Continue. Rows that wait for the user use `ng-btn--steer`.
- "Needs you" filters to Plan review and any Paused row. Its count is also the browser tab title: "(2) Netgrip".
- Sort: needs you first, then running, then by last activity.
- Row click opens the board (or the report for Completed). Delete lives in the row's overflow menu and in the board; it opens the app's only modal, on `scrim`, naming the prompt and the disk space that will be freed, with a `ng-btn--danger` "Delete investigation".
- At the parallel limit, "New investigation" stays enabled; the new one waits as a Draft and the title row says "5 active of 5 allowed".

**Empty state.** No table. The prompt box from ScreenNewInvestigation sits in its place under the line "Ask a question or state a claim. Netgrip will check it, including the parts you take for granted."
""")

# ================= New investigation =================
def tier(name, does, model, share, note=""):
    return f'<tr><td><span class="ng-heading">{name}</span><div class="ng-small ng-muted">{does}</div></td><td><select class="ng-select ng-input--mono" aria-label="{name} model"><option>{model}</option></select>{note}</td><td class="is-num">{share}</td></tr>'
screen("ScreenNewInvestigation", 1130, top("Investigations") + f"""
<main class="ng-page"><div class="ng-page__in" style="max-width:1120px;display:grid;grid-template-columns:1fr 340px;gap:var(--space-6);align-items:start">
 <div class="ng-col ng-col--loose">
  <div class="ng-col"><span class="ng-mono ng-muted">Investigations / New</span><h1 class="ng-display">What should Netgrip find out?</h1></div>
  <div class="ng-field"><label class="ng-field__label" for="prompt">Your question or claim</label>
   <textarea id="prompt" class="ng-textarea" style="min-height:104px;font-size:15px;line-height:22px">Why is the Great Wall of China visible from space with the naked eye?</textarea>
   <span class="ng-field__hint">Kept word for word. Anything you assume here is checked first, and you are told if it is wrong.</span></div>
  <div class="ng-field"><span class="ng-field__label">Effort</span>
   <div class="ng-row"><div class="ng-seg"><button class="ng-seg__opt">Low</button><button class="ng-seg__opt is-on">Medium</button><button class="ng-seg__opt">High</button></div><span class="ng-mono ng-muted">depth 4 · 40 nodes · 8 sources/node · 4 in parallel · 2 independent sources to confirm</span></div>
   <span class="ng-field__hint">These values are provisional. Change them in Settings → Effort.</span></div>
  <div class="ng-field"><span class="ng-field__label">Models</span>
   <div class="ng-row"><div class="ng-seg"><button class="ng-seg__opt">Economy</button><button class="ng-seg__opt is-on">Balanced</button><button class="ng-seg__opt">Maximum quality</button></div><span class="ng-small ng-muted">Preset from Settings. Override any tier for this run.</span></div>
   <div class="ng-panel"><table class="ng-table"><thead><tr><th>Tier</th><th>Model</th><th style="text-align:right">Share of cost</th></tr></thead><tbody>
    {tier("Strong", "Orchestrator, final synthesis, judging contradictions", "anthropic/claude-opus-5.5", "≈ 25%")}
    {tier("Standard", "The agent inside each node", "anthropic/claude-sonnet-5.5", "≈ 45%")}
    {tier("Fast", "Reading pages, extracting claims", "anthropic/claude-haiku-5.5", "≈ 25%")}
    {tier("Verifier", "Independent re-check of important claims", "openai/gpt-5.2", "≈ 5%", '<div class="ng-field__hint">A different model family from Strong, so it does not repeat the same mistake.</div>')}
   </tbody></table></div></div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-4)">
   <div class="ng-field"><label class="ng-field__label" for="excl">Exclude domains</label><input id="excl" class="ng-input ng-input--mono" value="reddit.com, quora.com"><span class="ng-field__hint">Listed in the report as a limit.</span></div>
   <div class="ng-field"><label class="ng-field__label" for="pref">Prefer</label><select id="pref" class="ng-select"><option>No preference</option><option>Primary sources only</option></select></div>
   <div class="ng-field"><label class="ng-field__label" for="fresh">Reuse fetched pages up to</label><select id="fresh" class="ng-select"><option>1 day old (default)</option><option>Always fetch again</option></select><span class="ng-field__hint">Choose "Always fetch again" for questions about current events.</span></div>
   <div class="ng-field"><label class="ng-field__label" for="cap">Spending limit</label><input id="cap" class="ng-input ng-input--mono" value="$5.00"><span class="ng-field__hint">Reaching it pauses and asks you. Planning counts towards it.</span></div>
  </div>
 </div>
 <aside class="ng-panel" style="position:sticky;top:0"><div class="ng-panel__head"><span class="ng-label">Before you start</span></div><div class="ng-panel__body ng-col ng-col--loose">
  <div class="ng-col"><span class="ng-label">Estimated cost</span><span class="ng-display ng-num">$1.60 – $4.20</span><span class="ng-small ng-muted">Medium effort, Balanced models. An estimate, not a quote: run length is not known in advance.</span></div>
  <div class="ng-col" style="gap:2px"><div class="ng-row ng-mono"><span class="ng-muted ng-grow">Strong</span><span>$0.40 – $1.05</span></div><div class="ng-row ng-mono"><span class="ng-muted ng-grow">Standard</span><span>$0.72 – $1.89</span></div><div class="ng-row ng-mono"><span class="ng-muted ng-grow">Fast</span><span>$0.40 – $1.05</span></div><div class="ng-row ng-mono"><span class="ng-muted ng-grow">Verifier</span><span>$0.08 – $0.21</span></div></div>
  <hr class="ng-hr">
  <div class="ng-col"><span class="ng-label">What happens next</span><p class="ng-small">Netgrip drafts a plan: the root goal, the assumptions it found in your question, and a first split into lines of inquiry. No web research runs until you approve it.</p></div>
  <button class="ng-btn ng-btn--steer" style="justify-content:center">Draft the plan</button>
  <button class="ng-btn ng-btn--quiet" style="justify-content:center">Save as draft</button>
 </div></aside>
</div></main>
""", """
# ScreenNewInvestigation

The Draft state: the prompt, the settings for this run, and what it will roughly cost, before anything executes.

**Regions**

1. Left column, in this order: prompt (`ng-textarea` at 15/22), Effort (`ng-seg` with the resulting budget in `mono`), Models (preset `ng-seg` and a four-row tier table), source filters, page freshness, spending limit.
2. Right column, sticky: estimated cost as a range in `display`, per-tier split, "What happens next", and the steer button "Draft the plan".

**Rules**

- The prompt hint states the product's stance: the text is kept word for word and its assumptions are checked.
- Effort shows its consequences beside the control. The numbers come from Settings and are marked provisional there.
- The tier table says what each tier does and its rough share of cost. A model with no known price gets a `warn` hint, "No price on record. The spending limit will be approximate", with a link to Settings → Models.
- The Verifier row warns in `warn` when it shares a model family with Strong.
- The estimate is always a range and always says it is an estimate.
- The primary button is "Draft the plan", not "Start": research does not start here. It leads to ScreenPlanReview. If no model key is set, it is disabled and the hint reads "Add a model key in Settings → Keys".
- Every field here inherits its default from Settings and applies to this investigation only.
""", w=1280)

# ================= Plan review =================
screen("ScreenPlanReview", 860, top("Investigations") + f"""
<div class="ng-board">
 <div class="ng-board__head">
  <div class="ng-col ng-grow" style="gap:2px"><div class="ng-row ng-row--nowrap">{pill("steer","✎︎","Plan review")}<span class="ng-mono ng-muted">Medium · Balanced · no research has run</span></div><h1 class="ng-title ng-clip">Why is the Great Wall of China visible from space with the naked eye?</h1></div>
  {meter("Spend", "$0.06", "$5.00", 2)}{meter("Planned nodes", "8", "40", 20, w=170)}
  <div class="ng-row ng-row--nowrap"><button class="ng-btn ng-btn--quiet">Discard draft</button><button class="ng-btn ng-btn--steer">Approve plan and start</button></div>
 </div>
 <div class="ng-board__body" style="grid-template-columns:1fr 400px">
  <div class="ng-center" style="grid-template-rows:40px 1fr auto">
   <div class="ng-toolbar"><span class="ng-label">Proposed plan · version 3</span><span class="ng-mono ng-muted">changed by your last instruction: 1 removed, 1 added</span><button class="ng-btn ng-btn--sm ng-btn--quiet ng-right">Fit</button><button class="ng-btn ng-btn--sm ng-btn--quiet">Undo last instruction</button></div>
   <div id="g" class="ng-canvas"></div>
   <div class="ng-dock" style="padding:var(--space-3)">
    <div class="ng-composer"><div class="ng-composer__head">✎︎ Instruct the plan <span>· R · reshapes the whole investigation</span></div>
    <textarea id="plan-instr" aria-label="Instruction for the plan" placeholder="Leave out a line of inquiry, add one, narrow the scope…"></textarea>
    <div class="ng-composer__foot"><span class="ng-grow">The plan is redrawn each time. You can change what is investigated, not what is concluded.</span><span class="ng-kbd">⌘↵</span><button class="ng-btn ng-btn--sm">Re-plan</button></div></div>
   </div>
  </div>
  <aside class="ng-pane ng-pane--right"><div class="ng-pane__scroll ng-col ng-col--loose" style="padding:var(--space-4)">
   <div class="ng-col"><span class="ng-label">Root goal</span><p>Establish whether, and under what conditions, the Great Wall can be seen from space with the naked eye, and why the belief exists.</p><span class="ng-small ng-muted">Derived from your prompt. Fixed once you approve.</span></div>
   <div class="ng-col"><span class="ng-label">Assumptions in your question · checked first</span>
    <div class="ng-claim"><div class="ng-row"><span class="ng-tag">PRM</span><span class="ng-mono ng-faint">P1</span></div><span>The Wall is visible to the naked eye from low Earth orbit.</span></div>
    <div class="ng-claim"><div class="ng-row"><span class="ng-tag">PRM</span><span class="ng-mono ng-faint">P2</span></div><span>"From space" includes the Moon, as the popular version of the claim says.</span></div>
    <span class="ng-small ng-muted">Your question takes these as given. If they turn out false, the report says so first.</span></div>
   <div class="ng-col"><span class="ng-label">Your instructions so far</span>
    <div class="ng-instr"><div class="ng-instr__meta"><span>You · 13:48:40</span><span>plan v2 → v3</span></div><div class="ng-instr__text">Leave out tourism marketing. Include where the claim came from.</div>
    <div class="ng-diff" style="margin-top:var(--space-2)"><span class="ng-diff__k">= kept        P1, P2, D2, D3, V1</span><span class="ng-diff__s">− removed     D5 Use of the claim in tourism marketing</span><span class="ng-diff__n">+ added       D1 Where does the claim come from?</span></div></div>
    <div class="ng-instr"><div class="ng-instr__meta"><span>You · 13:47:02</span><span>plan v1 → v2</span></div><div class="ng-instr__text">Don't spend time on satellites and radar, only human eyes.</div></div></div>
   <div class="ng-col"><span class="ng-label">On approval</span><p class="ng-small ng-muted">P1 and P2 run first. Then D1, D2 and D3 run in parallel, 4 at a time. The orchestrator may add nodes as it learns; each one appears here with its reason.</p></div>
  </div></aside>
 </div>
</div>
<script>{GRAPH_JS}
ngGraph(document.getElementById('g'), [
 {{id:'R', k:'SYN', s:'proposed', st:'◌ Planned', q:'Why is the Great Wall visible from space with the naked eye?', x:40, y:230, sel:1}},
 {{id:'P1', k:'PRM', s:'proposed', st:'◌ Planned', q:'Visible to the naked eye from low Earth orbit', x:320, y:24, sub:'runs first'}},
 {{id:'P2', k:'PRM', s:'proposed', st:'◌ Planned', q:'Visible from the Moon', x:320, y:124, sub:'runs first'}},
 {{id:'D1', k:'DIV', s:'proposed', st:'◌ Planned', q:'Where does the claim come from?', x:320, y:224, sub:'added by your instruction', mark:'new'}},
 {{id:'D2', k:'DEEP', s:'proposed', st:'◌ Planned', q:'What astronauts report', x:320, y:324}},
 {{id:'D3', k:'DEEP', s:'proposed', st:'◌ Planned', q:'What limits visibility: width, contrast, acuity', x:320, y:406}},
 {{id:'D5', k:'DEEP', s:'excluded', st:'− Removed', q:'Use of the claim in tourism marketing', x:320, y:488}},
 {{id:'V1', k:'VER', s:'proposed', st:'◌ Planned', q:'Re-check naked-eye resolution at 400 km', x:600, y:406, sub:'after D3'}}
],[['R','P1'],['R','P2'],['R','D1'],['R','D2'],['R','D3'],['R','D5','off'],['D3','V1','dep']]);
</script>
""", """
# ScreenPlanReview

The Planning state. The user sees the first decomposition as a graph, reshapes it with instructions, and approves it. No web research runs on this screen.

**Regions**

1. Board header: the "Plan review" pill in `steer`, the prompt as `title`, Spend (planning already costs model calls) and Planned nodes, then "Discard draft" and the steer button "Approve plan and start".
2. Centre: toolbar with the plan version and what the last instruction changed; the GraphCanvas with every node dashed ("Planned"); the InstructionComposer docked underneath, aimed at the root.
3. Right pane: root goal; the assumptions extracted from the prompt, each a Premise check; the user's instructions so far, newest first, each with its diff; a short "On approval" note on execution order.

**Rules**

- Every node is `ng-node--proposed` with the state word "Planned". Nothing is live, so nothing is `live` coloured.
- Each instruction redraws the graph. Nodes it added carry a `steer` mark "new" until the next instruction; nodes it removed stay for that one version as `ng-node--excluded` with "− Removed", then leave the canvas. They remain in the instruction's diff.
- "Undo last instruction" returns to the previous plan version. Versions are numbered in the toolbar.
- The composer's own button is the neutral "Re-plan"; the single steer button on this screen is "Approve plan and start".
- The assumptions block uses the user's wording and explains the stance in one sentence. It is not optional and cannot be removed by instruction; an instruction that tries is answered in the diff: "P1 kept: premises are always checked".
- While a re-plan is being computed, the toolbar shows "Re-planning…" as an ActivityLine and Approve is disabled.
- Leaving the screen keeps the plan. The list shows the row as "Plan review" under Needs you.
""")

# ================= Control board =================
GRAPH_NODES = """[
 {id:'R', k:'SYN', s:'waiting', st:'◔ Waiting', q:'Why is the Great Wall visible from space with the naked eye?', x:12, y:242, sub:'3 of 6 children complete'},
 {id:'P1', k:'PRM', s:'done', st:'✓ Completed', q:'Visible to the naked eye from low Earth orbit', x:212, y:8, sub:'Premise refuted · high'},
 {id:'P2', k:'PRM', s:'done', st:'✓ Completed', q:'Visible from the Moon', x:212, y:100, sub:'Premise refuted · high'},
 {id:'D1', k:'DIV', s:'waiting', st:'◔ Waiting', q:'Where does the claim come from?', x:212, y:192},
 {id:'D2', k:'DEEP', s:'waiting', st:'◔ Waiting', q:'What astronauts report', x:212, y:268, sub:'1 of 3 children complete', mark:'✎︎ 1', fold:'−'},
 {id:'D3', k:'DEEP', s:'running', st:'● Running', q:'What limits visibility: width, contrast, acuity', x:212, y:362, sub:'SEARCHING "visual acuity" arcminute'},
 {id:'V1', k:'VER', s:'pending', st:'○ Pending', q:'Re-check naked-eye resolution at 400 km', x:212, y:466},
 {id:'D4', k:'DIV', s:'excluded', st:'⦸ Ignored', q:'Other structures visible from orbit', x:212, y:542},
 {id:'D1a', k:'DEEP', s:'done', st:'✓ Completed', q:'Pre-spaceflight origins, 1754–1932', x:412, y:40, sub:'4 claims · medium'},
 {id:'D1b', k:'DEEP', s:'running', st:'● Running', q:'Textbook and media repetition', x:412, y:134, sub:'READING britannica.com/topic/…'},
 {id:'D2a', k:'DEEP', s:'done', st:'✓ Completed', q:'Yang Liwei, 2003', x:412, y:228, sub:'3 claims · high'},
 {id:'D2b', k:'DEEP', s:'running', st:'● Running', q:'Leroy Chiao photograph, 2004', x:412, y:322, sub:'EXTRACTING 4 claims · nasa.gov', sel:1},
 {id:'D2c', k:'DEEP', s:'running', st:'● Retrying', q:'ESA Proba image, 2004: who identified it', x:412, y:416, sub:'RETRYING 2 OF 3 · esa.int'},
 {id:'D2x', k:'DEEP', s:'excluded', st:'↺ Superseded', q:'Space-agency press releases', x:412, y:510},
 {id:'N1', k:'DEEP', s:'proposed', st:'◌ Proposed', q:'School textbooks, 1950–2000', x:612, y:100},
 {id:'N2', k:'DEEP', s:'rejected', st:'⊘ Rejected', q:"History of the Wall's construction", x:612, y:184}
]"""
GRAPH_EDGES = "[['R','P1'],['R','P2'],['R','D1','live'],['R','D2','live'],['R','D3','live'],['R','V1'],['R','D4','off'],['D1','D1a'],['D1','D1b','live'],['D2','D2a'],['D2','D2b','live'],['D2','D2c','live'],['D2','D2x','off'],['D1b','N1'],['D1b','N2','off'],['D3','V1','dep']]"
BOARD_HEAD = f"""
 <div class="ng-board__head">
  <button class="ng-btn ng-btn--sm ng-btn--quiet" aria-label="Back to investigations">←</button>
  <div class="ng-col ng-grow" style="gap:2px"><div class="ng-row ng-row--nowrap">{pill("live",'<span class="ng-pulse">●</span>',"Running")}<span class="ng-mono ng-muted">Medium · Balanced · 0:22:10 · 4 running</span>{pill("danger","✕","2 premises refuted")}</div><h1 class="ng-title ng-clip">Why is the Great Wall of China visible from space with the naked eye?</h1></div>
  {meter("Spend", "$1.84", "$5.00", 37)}{meter("Nodes", "16", "40", 40, w=100)}{meter("Depth", "3", "4", 75, w=84)}
  <div class="ng-row ng-row--nowrap"><button class="ng-btn">‖ Pause</button><button class="ng-btn">Finish now</button><button class="ng-btn ng-btn--quiet">Stop</button><button class="ng-btn ng-btn--quiet" aria-label="More">⋯</button></div>
 </div>"""
CENTER = f"""
  <div class="ng-center">
   <div class="ng-toolbar"><span class="ng-label">Graph</span><span class="ng-mono ng-muted">16 nodes · 4 running · 3 excluded</span><button class="ng-btn ng-btn--sm ng-btn--quiet ng-right">Fit</button><button class="ng-btn ng-btn--sm ng-btn--quiet">Collapse completed</button><label class="ng-toggle is-on"><span class="ng-toggle__track"></span>Show excluded</label><label class="ng-toggle is-on"><span class="ng-toggle__track"></span>Follow active</label></div>
   <div id="g" class="ng-canvas"></div>
   <div class="ng-dock"><div class="ng-panel__head" style="min-height:34px;padding-block:4px"><span class="ng-label">Event log</span><div class="ng-row ng-row--tight"><span class="ng-tag ng-tag--solid">All</span><span class="ng-tag ng-tag--steer">You 7</span><span class="ng-tag">Orchestrator</span><span class="ng-tag">Selected node</span><span class="ng-tag">Claims</span><span class="ng-tag">Problems 2</span></div><span class="ng-right ng-mono ng-faint">current to #0419</span><button class="ng-btn ng-btn--sm ng-btn--quiet">Follow ●</button><button class="ng-btn ng-btn--sm ng-btn--quiet" aria-label="Collapse log">▾</button></div>
   <div class="ng-log" style="height:166px;overflow:hidden;padding:var(--space-1) 0">{LOG}</div></div>
  </div>"""
def inspector(tab, content):
    tabs = "".join(f'<button class="ng-tab{" is-on" if t == tab else ""}">{t}{c}</button>' for t, c in [("Overview", ""), ("Claims", '<span class="ng-mono-sm">3</span>'), ("Brief", ""), ("Trail", ""), ("Instructions", '<span class="ng-mono-sm">2</span>')])
    return f"""
  <aside class="ng-pane ng-pane--right">
   <div class="ng-col" style="padding:var(--space-3) var(--space-3) var(--space-2);gap:var(--space-2)">
    <div class="ng-row ng-row--nowrap"><span class="ng-tag">DEEP</span><span class="ng-mono ng-faint">D2b · depth 2</span>{pill("live",'<span class="ng-pulse">●</span>',"Running")}<button class="ng-btn ng-btn--sm ng-btn--quiet ng-right" aria-label="Node actions">⋯</button></div>
    <h2 class="ng-heading">Leroy Chiao photograph, 2004</h2>
    <p class="ng-small ng-muted"><span class="ng-label">Why </span>If the photo needed a long lens, it does not support naked-eye visibility.</p>
    <div class="ng-row ng-row--tight"><button class="ng-btn ng-btn--sm">Go deeper</button><button class="ng-btn ng-btn--sm">Run only this</button><button class="ng-btn ng-btn--sm">Pause</button><button class="ng-btn ng-btn--sm">Ignore</button></div>
   </div>
   <div class="ng-tabs">{tabs}</div>
   <div class="ng-pane__scroll ng-col" style="padding:var(--space-3);gap:var(--space-3)">{content}</div>
   <div style="padding:var(--space-3);border-top:1px solid var(--line)">
    <div class="ng-composer"><div class="ng-composer__head">✎︎ Instruct D2b <span>· reaches 1 node</span></div>
    <textarea id="instr" aria-label="Instruction for D2b" placeholder="Narrow, redirect or add a constraint…" style="min-height:44px"></textarea>
    <div class="ng-composer__foot"><span class="ng-grow">Takes effect at this node's next step.</span><span class="ng-kbd">⌘↵</span><button class="ng-btn ng-btn--sm ng-btn--steer">Send instruction</button></div></div>
   </div>
  </aside>"""
OVERVIEW = f"""
 <div class="ng-col"><span class="ng-label">Now</span><div class="ng-well"><div class="ng-activity"><span class="ng-activity__verb">Extracting</span><span class="ng-activity__what">4 claims · nasa.gov/vision/space/workinginspace/great_wall.html</span></div><div class="ng-faint" style="margin-top:4px">step 5 · 1:12 in this run · 3 of 8 sources read</div></div></div>
 <div class="ng-col"><div class="ng-row"><span class="ng-label">Verdict</span><span class="ng-small ng-faint ng-right">not yet · appears here the moment it exists</span></div></div>
 <div class="ng-col"><span class="ng-label">Claims so far</span>
  <div class="ng-claim" style="padding:var(--space-2) var(--space-3)"><div class="ng-row">{pill("ok ng-pill--hollow","✓","Supported")}<span class="ng-mono ng-faint ng-right">C-040</span></div><span class="ng-small">Chiao photographed a section of the Wall from the ISS in November 2004.</span></div>
  <div class="ng-claim" style="padding:var(--space-2) var(--space-3)"><div class="ng-row">{pill("","?","Unverified")}<span class="ng-mono ng-faint ng-right">C-041</span></div><span class="ng-small">The photo was taken with a 180 mm lens.</span></div></div>
 <div class="ng-row" style="gap:var(--space-4)">{meter("Spend", "$0.14", "$0.30", 47, w=120)}{meter("Sources", "3", "8", 38, w=100)}</div>
 <div class="ng-col"><span class="ng-label">Inherited instruction</span>
  <div class="ng-instr ng-instr--inherited"><div class="ng-instr__meta"><span>From D2</span><span>You · 14:02:11</span></div><div class="ng-instr__text">Only first-hand statements from people who were in orbit. Skip agency press releases.</div></div></div>
"""
BOARD_README = """
# ScreenControlBoard

The investigation detail screen while research runs: one header and three panes that show the same nodes by time, by structure and one at a time. This is where the user watches and steers.

**Regions**

1. **Header** (60px). Back; StatusPill with effort, preset, run time and running count; a `danger` pill when a premise has been refuted; the prompt as `title`; three BudgetMeters (Spend, Nodes, Depth); RunControls; an overflow with Export events, Open report and Delete investigation.
2. **Left pane, 284px: ExecutionOrder.** Now, Next, Done, Not running. Answers "what is happening, what comes after, what already happened".
3. **Centre: GraphCanvas** under a 40px toolbar (node counts; Fit, Collapse completed, Show excluded, Follow active), with the **EventLog** docked below. The log collapses to its head row.
4. **Right pane, 364px: the inspector** for the selected node. Top: kind, id, depth, StatusPill, question, the node's "Why", and the four most used NodeActions. Tabs: Overview, Claims, Brief, Trail, Instructions. The InstructionComposer is pinned to the bottom and always aims at the selected node.

**Rules**

- One selection, three panes. Clicking a node, a queue row or a log row selects the same node everywhere. With nothing selected, the inspector shows the root.
- Pink means the user, cyan means agents. On this screen `steer` appears only on the composer, the user's instructions, the user's log rows and node marks. `live` appears only on running or waiting work.
- The screen never guesses state. Controls show `is-sent` wording until the confirming event arrives over the stream; the toolbar's "current to #0419" is the proof of freshness.
- A SystemPause banner, when present, sits between the header and the panes and pushes them down.
- "Run only this branch" replaces the header's mono line with "Running only D2" and a "Run everything" button; nodes outside the branch dim to `ink-faint` text but keep their state.
- When the stream disconnects, the header pill gains "· reconnecting" in `warn`, live glyphs stop pulsing, and controls stay usable (commands queue with their ids).
- Paused: no node pulses, Now is empty, the pill is `warn` with its origin, and the header's Pause becomes the steer button Resume.
- Synthesising: the graph is read-only, the left pane shows "Writing the report from 61 claims", and the composer is locked.
- Completed or Stopped: the same board opens read-only as history, with "Open report" as the header's main button.

**Keyboard.** `↑ ↓` move through the queue; `← →` parent and first child in the graph; `I` instruct; `D` go deeper; `F` run only this branch; `Space` pause or resume branch; `X` ignore or restore; `R` re-run; `L` toggle the log; `.` node menu; `Esc` clear selection.

**Narrow widths.** Below 1180px the inspector becomes an overlay sheet over the graph; below 900px the left pane becomes a tab beside "Graph" and "Log". The composer stays reachable in every layout.
"""
screen("ScreenControlBoard", 970, top("Investigations") + f"""
<div class="ng-board">{BOARD_HEAD}
 <div class="ng-board__body">
  <aside class="ng-pane ng-pane--left"><div class="ng-pane__scroll">{QUEUE}</div></aside>
  {CENTER}
  {inspector("Overview", OVERVIEW)}
 </div>
</div>
<script>{GRAPH_JS}
ngGraph(document.getElementById('g'), {GRAPH_NODES}, {GRAPH_EDGES});
</script>
""", BOARD_README)

# ================= Node detail (inspector tabs) =================
def insp_card(title, content, w=364):
    return f'<div class="ng-col" style="width:{w}px"><span class="ng-label">{title}</span><div class="ng-panel ng-col" style="padding:var(--space-3);gap:var(--space-3)">{content}</div></div>'
CLAIMS_TAB = f"""
 <div class="ng-row ng-row--tight"><span class="ng-tag ng-tag--solid">All 3</span><span class="ng-tag">Confirmed 1</span><span class="ng-tag">Contested 1</span><span class="ng-tag">Unverified 1</span></div>
 <div class="ng-claim"><div class="ng-row">{pill("ok","✓✓","Confirmed")}<span class="ng-mono ng-faint ng-right">C-040</span></div><div class="ng-claim__text">Leroy Chiao photographed a section of the Wall from the ISS on 24 November 2004.</div>
  <div class="ng-col" style="gap:2px"><span class="ng-label">Supports · 2 independent</span><div class="ng-src"><span class="ng-tag ng-tag--solid">PRIMARY</span><span class="ng-src__url">nasa.gov/vision/space/workinginspace/great_wall.html</span><span>2005-05-09</span></div><div class="ng-src"><span class="ng-tag">REPUTABLE</span><span class="ng-src__url">space.com/…/great-wall-china-photo</span><span>2005-04-19</span></div></div></div>
 <div class="ng-claim"><div class="ng-row">{pill("warn","⇄","Contested")}<span class="ng-mono ng-faint ng-right">C-042</span></div><div class="ng-claim__text">Chiao could see the Wall with his own eyes while taking the photo.</div>
  <div class="ng-col" style="gap:2px"><span class="ng-label">Supports · 1</span><div class="ng-src"><span class="ng-tag ng-tag--dashed">WEAK</span><span class="ng-src__url">travelblog.example/great-wall-from-space</span><span>2011-03-02</span></div><span class="ng-label">Contradicts · 1</span><div class="ng-src ng-src--against"><span class="ng-tag ng-tag--solid">PRIMARY</span><span class="ng-src__url">nasa.gov/vision/space/workinginspace/great_wall.html</span><span>2005-05-09</span></div></div><button class="ng-btn ng-btn--sm" style="align-self:flex-start">Verify this claim</button></div>
"""
TRAIL_TAB = """
 <div class="ng-col" style="gap:2px">
  <div class="ng-well"><span class="ng-faint">step 1 · 14:01:16 · </span><span class="ng-live">PLANNING</span> find the photo's own caption, then one independent report</div>
  <div class="ng-well"><span class="ng-faint">step 2 · 14:01:21 · </span><span class="ng-live">SEARCHING</span> "Leroy Chiao" "Great Wall" photograph 180mm · 8 results</div>
  <div class="ng-well"><span class="ng-faint">step 3 · 14:01:30 · </span><span class="ng-live">READING</span> nasa.gov/vision/space/… · simple fetch · 4.1 KB of text <a href="#">stored page</a></div>
  <div class="ng-well"><span class="ng-faint">step 4 · 14:01:52 · </span><span class="ng-warn">RETRYING 2 OF 3</span> space.com timed out · full browser · ok</div>
  <div class="ng-well" style="border-color:var(--steer)"><span class="ng-steer">— instruction from D2 applied here, between step 4 and step 5 —</span></div>
  <div class="ng-well" style="border-color:var(--live)"><span class="ng-faint">step 5 · 14:02:20 · </span><span class="ng-live">EXTRACTING</span> 4 claims<div class="ng-faint" style="font-style:italic;margin-top:4px">…the caption says the photo was taken with a 180 mm lens, so it is not a naked-eye observation. Chiao himself was not sure▍</div><div class="ng-faint" style="margin-top:4px">live text · shown while this node is open · not stored</div></div>
 </div>
"""
INSTR_TAB = """
 <span class="ng-label">In the order the agent reads them</span>
 <div class="ng-instr ng-instr--inherited"><div class="ng-instr__meta"><span>Inherited from R · plan review</span><span>You · 13:48:40</span></div><div class="ng-instr__text">Leave out tourism marketing. Include where the claim came from.</div></div>
 <div class="ng-instr ng-instr--inherited"><div class="ng-instr__meta"><span>Inherited from D2</span><span>You · 14:02:11 · #0412</span></div><div class="ng-instr__text">Only first-hand statements from people who were in orbit. Skip agency press releases.</div></div>
 <span class="ng-small ng-muted">No instruction has been given to D2b itself. Write one below.</span>
"""
BRIEF_TAB = """
<dl class="ng-brief" style="margin:0">
 <dt>Root goal</dt><dd>Why is the Great Wall of China visible from space with the naked eye?</dd>
 <dt>Path</dt><dd class="ng-col" style="gap:2px"><span class="ng-muted">R → answer the question as asked</span><span class="ng-muted">D2 → first-hand reports decide whether the premise holds</span><span>D2b → the one photograph often cited as proof</span></dd>
 <dt>Task</dt><dd>Establish who took the photo, with what lens, and what it shows.</dd>
 <dt>Out of scope</dt><dd class="ng-muted">Satellite and radar imagery. Other structures.</dd>
 <dt>Done when</dt><dd class="ng-muted">Lens and date are confirmed by a primary source.</dd>
 <dt>Known</dt><dd><span class="ng-mono ng-muted">C-031, C-027 · result of D2a</span></dd>
 <dt>Budget</dt><dd><span class="ng-mono">$0.14 / $0.30 · 3 / 8 sources</span></dd>
</dl>"""
DONE_TAB = f"""
 <div class="ng-row"><span class="ng-label">Verdict</span><span class="ng-conf ng-right"><span class="ng-conf__bars"><b class="is-on"></b><b class="is-on"></b><b class="is-on"></b></span>High confidence</span></div>
 <p>Yang Liwei said after his October 2003 flight that he looked for the Wall and could not see it.</p>
 <div class="ng-row ng-mono ng-muted"><span>3 claims · 2 independent sources · $0.21 · 1 page unobtainable</span></div>
 <div class="ng-col"><span class="ng-label">Open questions</span><span class="ng-small ng-muted">Whether later Chinese astronauts reported differently.</span></div>
 <div class="ng-col"><span class="ng-label">Follow-ups it proposed</span><div class="ng-row"><span class="ng-small ng-grow">Statements by Shenzhou 6 and 7 crews</span>{pill("ghost","◌","Proposed")}</div></div>
 <div class="ng-row"><button class="ng-btn ng-btn--sm">Re-run node</button><button class="ng-btn ng-btn--sm ng-btn--quiet">Ignore branch</button></div>
"""
EXCL_TAB = f"""
 <div class="ng-row">{pill("steer ng-pill--hollow","⦸","Ignored by you")}<span class="ng-mono ng-faint">14:00:02 · #0398</span></div>
 <p class="ng-small ng-muted">This branch is stopped. Its 1 claim is kept out of the report, and the report will list the branch as excluded.</p>
 <div class="ng-well">1 node · $0.04 spent · 1 claim kept in storage</div>
 <button class="ng-btn ng-btn--sm ng-btn--steer" style="align-self:flex-start">Restore branch</button>
"""
write(R, "ScreenNodeDetail", 'group="Screens" page width=1240 height=980', f"""
<div style="display:flex;flex-wrap:wrap;gap:var(--space-5);align-items:flex-start">
 {insp_card("Claims tab", CLAIMS_TAB)}
 {insp_card("Trail tab · the node's steps, with live text on the open step", TRAIL_TAB)}
 {insp_card("Instructions tab", INSTR_TAB)}
 {insp_card("Brief tab", BRIEF_TAB)}
 {insp_card("Overview · completed node (D2a)", DONE_TAB)}
 {insp_card("Overview · ignored node (D4)", EXCL_TAB)}
</div>
""", """
# ScreenNodeDetail

The inspector's tabs and node states that the board screenshot does not show. Each panel here is the scrolling middle of the right pane; the node header above it and the composer below it stay as on ScreenControlBoard.

| Tab | Shows | Source |
|---|---|---|
| Overview | Now (ActivityLine, step number, time, sources read) while running; Verdict once it exists; claims so far; the branch's BudgetMeters; inherited instructions; open questions and proposed follow-ups | node state |
| Claims | filter tags by status; one ClaimCard per claim | evidence store |
| Brief | the Brief as the agent received it | stored brief |
| Trail | one `ng-well` per step: step number, time, activity verb, detail, link to the stored page | activity events; raw material on demand |
| Instructions | inherited instructions from the root down, then the node's own, oldest first | intervention events |

**Rules**

- The Trail's open step has a `live` border and shows streamed model text in italic `ink-faint` with a caret. A line under it says the text is live and not stored. Closed steps show only what was persisted.
- A `steer` rule in the Trail marks the step boundary at which an instruction was applied, so the user can see it did not interrupt a step.
- Retries appear in the Trail as their own steps in `warn`, with the fetch route used: simple fetch, full browser, hardened browser.
- "stored page" opens the page version this investigation used, as clean text, in a full-height sheet over the inspector. Page text is shown as inert text: no links are followed, no scripts or images load.
- A completed node's Overview leads with the Verdict, then open questions and the follow-ups it proposed with their orchestrator decision.
- A rejected node's Overview shows only the proposal, who proposed it and the orchestrator's reason. Its only action is Add instruction on the parent.
- An ignored or superseded node's Overview says who excluded it and when, what is kept, and offers Restore branch as the steer button.
- A failed node's Overview uses the Verdict component's failed state.
""")

# ================= Report =================
screen("ScreenReport", 1110, top("Investigations") + f"""
<div class="ng-board" style="grid-template-rows:auto 1fr">
 <div class="ng-board__head">
  <button class="ng-btn ng-btn--sm ng-btn--quiet" aria-label="Back">←</button>
  <div class="ng-col ng-grow" style="gap:2px"><div class="ng-row ng-row--nowrap">{pill("ok","✓","Completed")}<span class="ng-mono ng-muted">Medium · Balanced · 0:41:32 · $3.07 · ended early by you</span></div><h1 class="ng-title ng-clip">Why is the Great Wall of China visible from space with the naked eye?</h1></div>
  <div class="ng-row ng-row--nowrap"><button class="ng-btn">Open the board</button><button class="ng-btn">Export Markdown</button><button class="ng-btn ng-btn--steer">Ask a follow-up</button></div>
 </div>
 <div style="display:grid;grid-template-columns:220px 1fr 380px;min-height:0">
  <nav class="ng-pane ng-pane--left ng-col" style="padding:var(--space-5) var(--space-4);gap:var(--space-2)"><span class="ng-label">Report</span><a class="ng-small" href="#a" style="font-weight:600">The answer</a><a class="ng-small ng-danger" href="#w">Where you were wrong · 2</a><a class="ng-small ng-muted" href="#k">Key findings · 6</a><a class="ng-small ng-muted" href="#u">What could not be verified · 3</a><a class="ng-small ng-muted" href="#l">Limits of this investigation</a>
   <hr class="ng-hr" style="margin:var(--space-3) 0"><span class="ng-label">Evidence bar</span><span class="ng-small ng-muted">Medium effort: a claim is Confirmed with 2 independent sources.</span><span class="ng-mono ng-muted" style="margin-top:var(--space-2)">61 claims · 34 confirmed<br>47 sources · 5 unobtainable</span></nav>
  <main class="ng-pane__scroll" style="padding:var(--space-6) var(--space-7);overflow:hidden"><div class="ng-report">
   <section id="a"><div class="ng-row"><span class="ng-label">The answer</span><span class="ng-conf"><span class="ng-conf__bars"><b class="is-on"></b><b class="is-on"></b><b class="is-on"></b></span>High confidence</span></div>
    <h2 class="ng-display">It is not. The Wall cannot be seen with the naked eye from orbit, and the belief is older than spaceflight.</h2>
    <p>No astronaut has reported seeing the Great Wall unaided from low Earth orbit<a class="ng-cite is-open" href="#">C-031</a><a class="ng-cite" href="#">C-027</a>. At 400 km the Wall, mostly under 10 m wide, is far below what the eye can resolve<a class="ng-cite" href="#">C-052</a>. The claim appeared in print by 1932, decades before anyone could test it<a class="ng-cite" href="#">C-009</a>.</p>
    <div class="ng-well"><span style="color:var(--ink)">C-031</span> · Confirmed · 2 independent sources · from D2a Yang Liwei, 2003 · nasa.gov, chinadaily.com.cn · <a href="#">show on the board</a></div></section>
   <section id="w"><div class="ng-banner ng-banner--danger"><span class="ng-banner__g">✕</span><div class="ng-col ng-grow"><span class="ng-banner__t">Where you were wrong</span>
    <span>Your question assumed <b>the Wall is visible from space with the naked eye</b>. It is not, from low Earth orbit<a class="ng-cite" href="#">P1</a> or from the Moon<a class="ng-cite" href="#">P2</a>.</span></div></div></section>
   <section id="k"><h3 class="ng-title">Key findings</h3>
    <p>{pill("ok","✓✓","Confirmed")} Yang Liwei said in 2003 that he looked for the Wall and did not see it<a class="ng-cite" href="#">C-031</a>.</p>
    <p>{pill("ok","✓✓","Confirmed")} Leroy Chiao's November 2004 photograph of a Wall section was taken through a 180 mm lens<a class="ng-cite" href="#">C-040</a><a class="ng-cite" href="#">C-041</a>.</p>
    <p>{pill("ok ng-pill--hollow","✓","Supported")} <span class="ng-hedge">The claim may go back to a 1754 letter by William Stukeley</span><a class="ng-cite" href="#">C-006</a>; one reputable source reports it.</p></section>
   <section id="u"><h3 class="ng-title">What could not be verified</h3>
    <p>{pill("warn","⇄","Contested")} Whether a 2004 ESA satellite image shows the Wall. ESA's first statement and its later correction disagree<a class="ng-cite" href="#">C-044</a>.</p></section>
   <section id="l"><h3 class="ng-title">Limits of this investigation</h3>
    <p class="ng-muted">Medium effort. Ended early by you at 14:21 with 2 nodes unfinished. 5 pages could not be obtained.</p>
    <div class="ng-instr"><div class="ng-instr__meta"><span>You excluded · D4</span><span>Ignored branch</span></div><div class="ng-instr__text">Other structures visible from orbit</div></div>
    <div class="ng-instr"><div class="ng-instr__meta"><span>You narrowed · D2</span><span>Instruction</span></div><div class="ng-instr__text">Only first-hand statements from people who were in orbit. Skip agency press releases.</div></div></section>
  </div></main>
  <aside class="ng-pane ng-pane--right"><div class="ng-panel__head"><span class="ng-label">Evidence for C-031</span><button class="ng-btn ng-btn--sm ng-btn--quiet ng-right" aria-label="Close">✕</button></div><div class="ng-pane__scroll ng-col" style="padding:var(--space-3);gap:var(--space-3)">
   <div class="ng-claim"><div class="ng-row">{pill("ok","✓✓","Confirmed")}<span class="ng-mono ng-faint ng-right">C-031 · from D2a</span></div><div class="ng-claim__text">Yang Liwei said he did not see the Great Wall from orbit during Shenzhou 5.</div>
    <div class="ng-col" style="gap:2px"><span class="ng-label">Supports · 2 independent</span><div class="ng-src"><span class="ng-tag ng-tag--solid">PRIMARY</span><span class="ng-src__url">nasa.gov/vision/space/…/great_wall.html</span><span>2005-05-09</span></div><div class="ng-src"><span class="ng-tag">REPUTABLE</span><span class="ng-src__url">chinadaily.com.cn/en/doc/2003-10/17/…</span><span>2003-10-17</span></div><div class="ng-src ng-src--lost"><span class="ng-tag ng-tag--dashed">LOST</span><span class="ng-src__url">xinhuanet.com/english/2003-10/…</span><span>unobtainable</span></div></div></div>
   <div class="ng-col"><span class="ng-label">How it got here</span><div class="ng-well">R Why is the Great Wall visible…<br>└ D2 What astronauts report<br>&nbsp;&nbsp;└ D2a Yang Liwei, 2003 · ✓ high</div></div>
   <div class="ng-col"><span class="ng-label">Used in</span><span class="ng-small ng-muted">The answer, sentence 1 · Key findings, item 1</span></div>
  </div></aside>
 </div>
</div>
""", """
# ScreenReport

The Completed state: the written report, read inside the app, with every statement traceable to claims, nodes and sources.

**Regions**

1. Header: Completed pill with effort, preset, run time, total spend and "ended early by you" when that applies; then Open the board, Export Markdown, and the steer button "Ask a follow-up".
2. Left, 220px: section links with counts ("Where you were wrong · 2" in `danger`), then the evidence bar in words and the totals.
3. Centre: the report in a 680px column (`ng-report`).
4. Right, 380px: the evidence pane for the citation that is open. It shows the ClaimCard, the path of nodes that produced it, and where else the report uses it. Closed by default; the report column then centres.

**Rules**

- Section order is fixed: The answer, Where you were wrong, Key findings, What could not be verified, Limits of this investigation. "Where you were wrong" is omitted only when no premise was refuted.
- The answer opens with one `display` sentence that answers the prompt directly, with an `ng-conf` readout above it. If the user's premise was wrong, that sentence says so.
- Every factual sentence ends in `ng-cite` chips. The open one is filled. Citing a premise uses its node id (P1).
- Findings below Confirmed carry their pill and an `ng-hedge` underline, and are worded as uncertain.
- Limits always states: effort and evidence bar, whether the run was cut short and by what (budget, spending limit, Finish now), pages that could not be obtained, and each exclusion or narrowing the user made, shown as Instruction blocks.
- "Open the board" opens ScreenControlBoard read-only with the same selection. "show on the board" in the evidence pane does the same for one node.
- Export Markdown produces the same sections with citations as footnotes. It contains no settings and no keys.
- "Ask a follow-up" opens the prompt box with this investigation attached; the new question extends the existing graph rather than starting again.
- While Synthesising, this screen shows the section headings with "Writing from 61 claims…" as an ActivityLine and no partial prose.
""")

# ================= Settings =================
def frow(label, hint, control):
    return f'<div class="ng-form-row"><div class="ng-col" style="gap:2px"><span class="ng-field__label">{label}</span><span class="ng-field__hint">{hint}</span></div><div class="ng-col">{control}</div></div>'
def key(name, state, note, btn="Replace"):
    return f'<div class="ng-keyfield">{state}<span class="ng-mono ng-faint ng-grow">{note}</span><button class="ng-btn ng-btn--sm">{btn}</button></div>'
def eff(name, vals, on=""):
    cells = "".join(f'<td><input class="ng-input ng-input--mono" value="{v}" aria-label="{name} {i}" style="width:64px"></td>' for i, v in enumerate(vals))
    return f'<tr><td><span class="ng-heading">{name}</span>{on}</td>{cells}</tr>'
def price(model, tier, i, o, flag=""):
    return f'<tr><td class="ng-mono">{model}</td><td>{tier}</td><td class="is-num">{i}</td><td class="is-num">{o}</td><td>{flag}</td></tr>'
screen("ScreenSettings", 1960, top("Settings") + f"""
<main class="ng-page"><div class="ng-page__in"><h1 class="ng-display">Settings</h1>
<div class="ng-settings">
 <nav><a href="#keys" class="is-on">Keys</a><a href="#models">Models</a><a href="#effort">Effort</a><a href="#spend">Spending</a><a href="#sources">Sources</a><a href="#capacity">Capacity</a><a href="#storage">Storage</a></nav>
 <div class="ng-col" style="gap:var(--space-6)">
  <section class="ng-col" id="keys"><h2 class="ng-title">Keys</h2><p class="ng-small ng-muted">Keys are stored in Netgrip's database on this machine. They can be replaced but never shown again. Treat the database file as a secret.</p>
   <div class="ng-panel" style="padding:0 var(--space-4)">
   {frow("Model provider", "OpenRouter, or any OpenAI-compatible endpoint.", '<input class="ng-input ng-input--mono" value="https://openrouter.ai/api/v1" aria-label="Endpoint">' + key("k", pill("ok","✓","Key set"), "checked 12:04 · credit $41.20"))}
   {frow("Web search", "Tavily.", key("k", pill("danger","✕","Key rejected"), "Tavily answered \"invalid key\" at 02:14", "Replace key"))}
   </div></section>
  <section class="ng-col" id="models"><h2 class="ng-title">Models</h2>
   <div class="ng-row"><span class="ng-field__label">Default preset</span><div class="ng-seg"><button class="ng-seg__opt">Economy</button><button class="ng-seg__opt is-on">Balanced</button><button class="ng-seg__opt">Maximum quality</button></div><span class="ng-small ng-muted">Each investigation can override any tier.</span></div>
   <div class="ng-panel"><table class="ng-table"><thead><tr><th>Model</th><th>Tier in Balanced</th><th style="text-align:right">$ / M input</th><th style="text-align:right">$ / M output</th><th>Price source</th></tr></thead><tbody>
    {price("anthropic/claude-opus-5.5", "Strong", "15.00", "75.00", '<span class="ng-small ng-muted">provider</span>')}
    {price("anthropic/claude-sonnet-5.5", "Standard", "3.00", "15.00", '<span class="ng-small ng-muted">provider</span>')}
    {price("anthropic/claude-haiku-5.5", "Fast", "1.00", "5.00", '<span class="ng-small ng-muted">provider</span>')}
    {price("openai/gpt-5.2", "Verifier", '<input class="ng-input ng-input--mono is-error" aria-label="input price" style="width:72px" placeholder="–">', '<input class="ng-input ng-input--mono is-error" aria-label="output price" style="width:72px" placeholder="–">', '<span class="ng-small ng-warn">No price on record. Enter one, or spend will be approximate.</span>')}
   </tbody></table></div></section>
  <section class="ng-col" id="effort"><h2 class="ng-title">Effort</h2><p class="ng-small ng-muted">What Low, Medium and High mean. These are starting values, to be tuned after real runs.</p>
   <div class="ng-panel"><table class="ng-table"><thead><tr><th>Level</th><th>Max depth</th><th>Max nodes</th><th>Sources / node</th><th>In parallel</th><th>Sources to confirm</th></tr></thead><tbody>
    {eff("Low", [2, 12, 4, 2, 1])}{eff("Medium", [4, 40, 8, 4, 2], ' <span class="ng-tag">DEFAULT</span>')}{eff("High", [6, 80, 12, 6, 3])}
   </tbody></table></div></section>
  <section class="ng-col" id="spend"><h2 class="ng-title">Spending</h2><div class="ng-panel" style="padding:0 var(--space-4)">
   {frow("Default spending limit", "Per investigation. Reaching it pauses and asks you.", '<input class="ng-input ng-input--mono" value="$5.00" style="width:120px" aria-label="Default limit">')}
   {frow("When a service stops responding", "How long Netgrip retries before it pauses the investigation.", '<select class="ng-select" style="width:200px" aria-label="Retry window"><option>Retry for 5 minutes</option></select>')}
   </div></section>
  <section class="ng-col" id="sources"><h2 class="ng-title">Sources</h2><div class="ng-panel" style="padding:0 var(--space-4)">
   {frow("Always exclude", "Applied to every new investigation and listed in its report.", '<input class="ng-input ng-input--mono" value="pinterest.com" aria-label="Excluded domains">')}
   {frow("Reuse fetched pages", "Pages are shared between investigations while fresh. Claims never are.", '<select class="ng-select" style="width:200px" aria-label="Freshness"><option>Up to 1 day old</option><option>Always fetch again</option></select>')}
   {frow("Per-site politeness", "Slows requests to one site so your address is not blocked.", '<select class="ng-select" style="width:200px" aria-label="Politeness"><option>1 request every 2 seconds</option></select>')}
   </div></section>
  <section class="ng-col" id="capacity"><h2 class="ng-title">Capacity</h2><p class="ng-small ng-muted">Shared by all running investigations on this machine.</p><div class="ng-panel" style="padding:0 var(--space-4)">
   {frow("Investigations in parallel", "", '<input class="ng-input ng-input--mono" value="5" style="width:72px" aria-label="Parallel investigations">')}
   {frow("Model calls at once", "", '<input class="ng-input ng-input--mono" value="8" style="width:72px" aria-label="Model calls">')}
   {frow("Browser pages at once", "Each uses memory. 6 suits a 16 GB machine.", '<div class="ng-row"><input class="ng-input ng-input--mono" value="6" style="width:72px" aria-label="Browser pages"><span class="ng-mono ng-muted">now: 4 open · 2 restarts today · 7 fetches timed out</span></div>')}
   </div></section>
  <section class="ng-col" id="storage"><h2 class="ng-title">Storage</h2><div class="ng-panel" style="padding:0 var(--space-4)">
   {frow("On disk", "Nothing is removed until you delete an investigation.", '<span class="ng-mono">387 MB · 6 investigations · 1,204 pages</span><span class="ng-mono ng-muted">~/netgrip/data</span>')}
   {frow("Repair", "Rebuilds the current state from the event history. Safe; nothing is deleted.", '<button class="ng-btn" style="align-self:flex-start">Rebuild state from history</button>')}
   </div></section>
 </div>
</div></div></main>
""", """
# ScreenSettings

Defaults for every new investigation and the machine-wide limits, on one scrolling page with a section list at the left. Changes save as they are made.

| Section | Holds |
|---|---|
| Keys | model endpoint and key; search key. Write-only `ng-keyfield` rows with a status pill and the last check |
| Models | default preset; per-model table with tier, input and output price, and where the price came from |
| Effort | the budget behind Low, Medium, High: depth, nodes, sources per node, parallelism, sources needed to confirm |
| Spending | default spending limit; how long to retry a failing service before pausing |
| Sources | domains always excluded; page reuse window, including "Always fetch again"; per-site politeness |
| Capacity | investigations in parallel; model calls at once; browser pages at once, with live pool health |
| Storage | total disk use and data location; Rebuild state from history |

**Rules**

- A key is never displayed, not even masked characters. The row shows "Key set", "No key" or "Key rejected" with the provider's own message, and one button: Replace.
- A rejected key is `danger` here and raises the SystemPause banner on every investigation it paused.
- A model without a price gets empty `is-error` price inputs and a `warn` note. Until filled, any investigation using it shows "≈" before its spend.
- Effort values are editable numbers, labelled as starting values.
- Capacity shows what is in use now beside each limit, in `mono`.
- There is no account, profile, theme or notification section. The theme follows the system.
- Settings never appear in an exported report.
""", w=1280)
print("screens ok")
