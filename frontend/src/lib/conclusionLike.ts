/** "Reads like a conclusion" (U2, P2): a local text heuristic, not a model call. It only turns
 * the composer's foot to warn; the instruction is still sent and treated as a hypothesis. */
const PATTERNS: RegExp[] = [
  /\bconclude[sd]? that\b/,
  /\bthe (?:answer|conclusion|truth|verdict) is\b/,
  /\bprove[sd]? that\b/,
  /\bshow that (?:it|they|this|there) (?:is|are|was|were)\b/,
  /\bmake sure (?:the )?(?:report|verdict|answer|result)s? (?:says?|states?|concludes?|confirms?|shows?)\b/,
  /\bit(?: is|'s) (?:obvious|clear|certain|a fact|true|false) that\b/,
  /\b(?:obviously|clearly|undeniably|definitely) (?:true|false|visible|invisible|wrong|right|correct)\b/,
  /\bjust (?:confirm|prove|verify) (?:it|that|this)\b/,
  /\b(?:confirm|prove) (?:it|that) (?:is|was|isn't|wasn't)\b/,
];

export function conclusionLike(text: string): boolean {
  const t = text.toLowerCase().replace(/[’‘]/g, "'").replace(/\s+/g, " ");
  return PATTERNS.some((re) => re.test(t));
}
