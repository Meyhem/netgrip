/** Fuzzy matching for pickers. The query splits into words; every word must match the text,
 * in any order. A word matches as a substring (best) or as letters in order with gaps.
 * Separators are ignored, so "sonnet45" finds "claude-sonnet-4.5". Higher scores are better;
 * null means no match. `marks` lists the matched character positions, for highlighting. */
export interface FuzzyHit { score: number; marks: number[] }

const SEP = /[\s\-_/.:]/;
const isBoundary = (text: string, i: number) => i === 0 || SEP.test(text[i - 1]);

function matchWord(text: string, lower: string, word: string): FuzzyHit | null {
  const at = lower.indexOf(word);
  if (at >= 0) {
    let start = at;
    // Prefer an occurrence that starts a word ("opus" in "claude-opus", not "octopus").
    for (let i = at; i >= 0; i = lower.indexOf(word, i + 1)) {
      if (isBoundary(text, i)) { start = i; break; }
    }
    const marks = Array.from({ length: word.length }, (_, k) => start + k);
    return { score: 100 + word.length * 4 + (isBoundary(text, start) ? 30 : 0) - start * 0.05, marks };
  }
  // Letters in order, skipping separators in the text. Greedy, preferring word starts.
  const marks: number[] = [];
  let score = 0;
  let pos = 0;
  let prev = -2;
  for (const ch of word) {
    if (SEP.test(ch)) continue;
    let found = -1;
    for (let i = pos; i < lower.length; i++) {
      if (lower[i] !== ch) continue;
      if (found < 0) found = i;
      if (i === prev + 1 || isBoundary(text, i)) { found = i; break; }
    }
    if (found < 0) return null;
    score += found === prev + 1 ? 6 : isBoundary(text, found) ? 4 : 1;
    marks.push(found);
    prev = found;
    pos = found + 1;
  }
  return { score: score - (marks[marks.length - 1] - marks[0]) * 0.1, marks };
}

export function fuzzy(text: string, query: string): FuzzyHit | null {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return { score: 0, marks: [] };
  const lower = text.toLowerCase();
  let score = 0;
  const marks = new Set<number>();
  for (const w of words) {
    const hit = matchWord(text, lower, w);
    if (!hit) return null;
    score += hit.score;
    hit.marks.forEach((m) => marks.add(m));
  }
  return { score: score - text.length * 0.01, marks: [...marks].sort((a, b) => a - b) };
}

/** Rank `items` by the best match of the query over the fields `keys` gives (id first). */
export function rank<T>(items: T[], query: string, keys: (item: T) => string[], limit = 60) {
  const out: { item: T; score: number; marks: number[][] }[] = [];
  for (const item of items) {
    const fields = keys(item);
    let best: { score: number; marks: number[][] } | null = null;
    // A word may match in any field: score the query against the fields joined, and keep the
    // marks per field for highlighting.
    const joined = fields.join(" \u0000 ");
    const hit = fuzzy(joined, query);
    if (hit) {
      const per: number[][] = fields.map(() => []);
      let offset = 0;
      fields.forEach((f, i) => {
        per[i] = hit.marks.filter((m) => m >= offset && m < offset + f.length).map((m) => m - offset);
        offset += f.length + 3;
      });
      best = { score: hit.score + (per[0].length ? 5 : 0), marks: per };
    }
    if (best) out.push({ item, ...best });
  }
  out.sort((a, b) => b.score - a.score);
  return out.slice(0, limit);
}
