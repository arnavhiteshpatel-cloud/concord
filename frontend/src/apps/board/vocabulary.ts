// Communication board — word lists. Plain data; no device or decoder knowledge.

/** Phrase tiles, most useful first (a smaller tile grid shows fewer of them). */
export const PHRASES: readonly string[] = [
  "Yes",
  "No",
  "Hello",
  "Thank you",
  "Please",
  "Help",
  "Water",
  "Wait",
  "I'm tired",
  "Pain",
  "Too hot",
  "Too cold",
  "Bathroom",
  "Change position",
  "I don't know",
  "Call the nurse",
  "Turn on the TV",
  "Goodbye",
  "I love you",
  "Later",
];

export const LETTERS: readonly string[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");

/**
 * Core vocabulary for the task-grid layout and for word prediction: common English words,
 * roughly by frequency of use in conversation. 200 entries (a 14 × 14 grid uses 196).
 */
export const CORE_WORDS: readonly string[] = (
  "I you yes no it the a to and is not what that want go like do more help stop " +
  "here there this get make need good bad can will have he she we they me my your " +
  "on off in out up down all some one two now later today tomorrow again different same " +
  "open close turn put look see hear feel think know say tell ask give take come " +
  "eat drink water food hot cold pain tired sleep sit stand walk move bed chair " +
  "bathroom wash clean dry wear shirt light music book phone TV call family friend " +
  "nurse doctor mom dad home outside room door window fast slow big little many " +
  "happy sad angry scared sick okay fine better worse please thanks sorry hello " +
  "goodbye wait finished start play work read write watch listen talk sing laugh " +
  "who where when why how which because but or if with without for from about " +
  "very too much enough almost never always sometimes maybe sure right wrong " +
  "left front back top bottom inside under over next last first new old other " +
  "time day night morning afternoon evening week minute hour year name word " +
  "question answer love miss money car dog"
).split(" ");

/** Up to `n` completions of the word being typed (case-insensitive prefix match). */
export function predictions(message: string, n = 3, words: readonly string[] = CORE_WORDS): string[] {
  const partial = /([A-Za-z']+)$/.exec(message)?.[1] ?? "";
  if (!partial) return [];
  const p = partial.toLowerCase();
  const out: string[] = [];
  for (const w of words) {
    if (w.length > p.length && w.toLowerCase().startsWith(p) && !out.includes(w)) out.push(w);
    if (out.length >= n) break;
  }
  return out;
}

/** Parse a word-list file: one word or phrase per line; blank lines and `#` comments ignored. */
export function parseWordList(text: string, max = 400): string[] {
  return text
    .split(/\r?\n/)
    .map((l) => l.replace(/#.*$/, "").trim())
    .filter((l) => l.length > 0)
    .map((l) => l.slice(0, 40))
    .slice(0, max);
}
