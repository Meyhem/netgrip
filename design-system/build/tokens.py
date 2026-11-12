import json, sys, os
out = sys.argv[1]
def c(name, dark, light, usage): return {"name": name, "value": {"dark": dark, "light": light}, "usage": usage}
colors = [
 c("bg", "#0f1318", "#f4f6f8", "App ground behind every screen and the graph canvas."),
 c("surface", "#161b22", "#ffffff", "Panels, the top bar, table rows, graph nodes at rest."),
 c("raised", "#1d232c", "#ffffff", "Popovers, menus, the selected node, hovered rows."),
 c("sunken", "#0b0e12", "#e9edf1", "Wells: inputs, the event log, meter tracks, code and trail blocks."),
 c("line", "#2a323d", "#d5dbe2", "Hairline dividers and panel borders. Decorative only, never the sole carrier of meaning."),
 c("line-strong", "#5f6b7c", "#7b8694", "Control borders, graph edges, node outlines. 3:1 on bg, surface and raised in both themes."),
 c("ink", "#e8edf3", "#141a22", "Primary text on bg, surface, raised and sunken."),
 c("ink-muted", "#a3aebc", "#4a5564", "Secondary text on bg, surface, raised and sunken: justifications, meta, table secondary columns."),
 c("ink-faint", "#8793a2", "#5c6877", "Tertiary text on bg, surface, raised and sunken: timestamps, sequence numbers, uppercase labels. Never for body copy."),
 c("steer", "#ff7ac0", "#b0186c", "The user's hand. Text, icons and borders for anything the user did or is asked to do: instructions, interventions, approval. Reads on bg, surface, raised, sunken and steer-wash. Also the fill of the one primary action per view."),
 c("on-steer", "#2a0a1b", "#ffffff", "Text and glyphs on a steer fill."),
 c("steer-wash", "#3a1a2c", "#fbe4f0", "Ground for instruction blocks, user rows in the event log, the composer header."),
 c("live", "#5cc8f0", "#0a6a94", "Agents at work. Running and waiting-on-children status, activity verbs, live edges. Reads on bg, surface, raised, sunken and live-wash."),
 c("live-wash", "#12303d", "#dff1f9", "Ground of a running node and of live pills."),
 c("ok", "#3ecfb2", "#0b7663", "Settled and holding: Completed nodes, Confirmed and Supported claims, Primary sources. A blue-leaning teal so it never relies on red-green contrast with danger. Reads on bg, surface, raised, sunken and ok-wash."),
 c("ok-wash", "#10332c", "#dcf3ee", "Ground of ok pills and confirmed-claim markers."),
 c("warn", "#f2b84b", "#8a5a00", "Needs attention but nothing is lost: Paused, Retrying, Contested claims, budget above 80%. Reads on bg, surface, raised, sunken and warn-wash."),
 c("warn-wash", "#3a2c10", "#faecc8", "Ground of warn pills and system-pause banners."),
 c("danger", "#ff8566", "#b3360f", "Broken or false: Failed nodes, Refuted claims and premises, Rejected proposals, destructive actions. Reads on bg, surface, raised, sunken and danger-wash."),
 c("danger-wash", "#3d1c14", "#fbe3da", "Ground of danger pills, the Where-you-were-wrong block, delete confirmation."),
 c("focus", "#5cc8f0", "#0a6a94", "Keyboard focus ring: solid 2px, 2px offset. 3:1 or better on every surface."),
 c("scrim", "rgba(5,8,12,0.6)", "rgba(20,26,34,0.35)", "Overlay behind the delete confirmation, the only modal in the app."),
]
tokens = {
 "name": "Netgrip", "version": 1,
 "color": {"themes": [{"id": "dark", "name": "Dark"}, {"id": "light", "name": "Light"}], "tokens": colors},
 "type": {
  "fonts": [],
  "families": {"sans": "\"Instrument Sans\", \"Segoe UI\", system-ui, sans-serif", "mono": "\"JetBrains Mono\", ui-monospace, \"SF Mono\", Menlo, Consolas, monospace"},
  "groups": [
   {"name": "Interface", "family": "sans", "styles": [
    {"name": "display", "fontSize": "28px", "lineHeight": "34px", "fontWeight": 600, "letterSpacing": "-0.01em", "usage": "Screen titles on Investigations, Settings, and the report's answer.", "sample": "Why is the Great Wall visible from space?"},
    {"name": "title", "fontSize": "20px", "lineHeight": "26px", "fontWeight": 600, "usage": "Investigation title in the board header; section titles in Settings and the report.", "sample": "Where you were wrong"},
    {"name": "heading", "fontSize": "15px", "lineHeight": "22px", "fontWeight": 600, "usage": "Panel heads, node question in the inspector, table primary column.", "sample": "What astronauts report"},
    {"name": "body", "fontSize": "14px", "lineHeight": "20px", "fontWeight": 400, "usage": "Default text: verdicts, claims, instructions, form copy.", "sample": "No astronaut has reported seeing the Wall unaided from low Earth orbit."},
    {"name": "small", "fontSize": "13px", "lineHeight": "18px", "fontWeight": 400, "usage": "Graph node titles, queue rows, hints under fields.", "sample": "Takes effect at each node's next step."},
    {"name": "label", "fontSize": "11px", "lineHeight": "16px", "fontWeight": 600, "letterSpacing": "0.06em", "usage": "Uppercase section labels and column heads. Always ink-faint.", "sample": "EXECUTION ORDER"}]},
   {"name": "Data", "family": "mono", "styles": [
    {"name": "mono", "fontSize": "12px", "lineHeight": "18px", "fontWeight": 400, "usage": "Activity lines, event log, URLs, queries, money, counts, node ids.", "sample": "READING  nasa.gov/vision/space/workinginspace/great_wall.html"},
    {"name": "mono-sm", "fontSize": "11px", "lineHeight": "16px", "fontWeight": 500, "usage": "Node kind codes, sequence numbers, keyboard hints, pill glyphs.", "sample": "DEEP  #0412  $0.31"}]}]},
 "spacing": {"tokens": [
  {"name": "space-1", "value": "4px", "usage": "Gap between a glyph and its word; pill padding block."},
  {"name": "space-2", "value": "8px", "usage": "Gap inside rows and between sibling controls; node padding."},
  {"name": "space-3", "value": "12px", "usage": "Panel head padding; gap between stacked blocks in the inspector."},
  {"name": "space-4", "value": "16px", "usage": "Panel padding; page gutter at narrow widths."},
  {"name": "space-5", "value": "24px", "usage": "Gap between sections; page gutter on list and settings screens."},
  {"name": "space-6", "value": "32px", "usage": "Gap between settings groups and report sections."},
  {"name": "space-7", "value": "48px", "usage": "Top padding of list and settings screens; empty-state breathing room."}]},
 "radius": {"tokens": [
  {"name": "radius-sm", "value": "3px", "usage": "Pills' inner tags, kind codes, keyboard hints, meter bars."},
  {"name": "radius-md", "value": "6px", "usage": "Buttons, inputs, graph nodes, panels, menus."},
  {"name": "radius-lg", "value": "10px", "usage": "The instruction composer and banners: the two things that ask for the user."},
  {"name": "radius-pill", "value": "999px", "usage": "Status pills and segmented controls only."}]},
 "shadow": {"tokens": [
  {"name": "shadow-pop", "value": {"dark": "0 8px 24px rgba(0,0,0,0.5)", "light": "0 8px 24px rgba(20,26,34,0.14)"}, "usage": "Menus and popovers only. Panels and nodes are flat and separated by line."}]},
}
json.dump(tokens, open(os.path.join(out, "tokens.json"), "w"), indent=1)
# first tokens.css, laid out as the page compiles it
L = ["/* Netgrip — generated from tokens.json */"]
def block(theme):
    r = [f"  --{t['name']}: {t['value'][theme]};" for t in colors]
    r += [f"  --{t['name']}: {t['value'][theme]};" for t in tokens['shadow']['tokens']]
    return "\n".join(r)
L.append(':root, [data-theme="dark"] {\n' + block("dark") + "\n}")
L.append('[data-theme="light"] {\n' + block("light") + "\n}")
r = [f"  --{t['name']}: {t['value']};" for t in tokens['spacing']['tokens'] + tokens['radius']['tokens']]
r += [f"  --font-{k}: {v};" for k, v in tokens['type']['families'].items()]
L.append(":root {\n" + "\n".join(r) + "\n}")
for g in tokens['type']['groups']:
    for s in g['styles']:
        d = [f"font-family: var(--font-{g['family']})", f"font-size: {s['fontSize']}", f"line-height: {s['lineHeight']}", f"font-weight: {s['fontWeight']}"]
        if 'letterSpacing' in s: d.append(f"letter-spacing: {s['letterSpacing']}")
        L.append(f".{s['name']} {{ " + "; ".join(d) + "; }")
open(os.path.join(out, "tokens.css"), "w").write("\n".join(L) + "\n")
