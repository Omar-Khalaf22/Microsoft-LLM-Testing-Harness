// Display-only Title Case for built-in criterion names ("JSON field type" -> "JSON Field Type").
// Existing capitals (acronyms such as JSON) are kept, and small words stay lowercase.
const SMALL = new Set(["a", "an", "the", "of", "to", "in", "on", "at", "by", "for", "or", "and", "as", "with", "from"]);

export function titleCase(text: string): string {
  return text
    .split(" ")
    .map((word, index) => {
      if (index > 0 && SMALL.has(word.toLowerCase())) return word.toLowerCase();
      return word.replace(/(^|[-(])([a-z])/g, (_, lead: string, letter: string) => lead + letter.toUpperCase());
    })
    .join(" ");
}

// Display-only: "completed" -> "Completed". Used for status and state words that come from the backend.
export const capitalize = (text: string): string => (text ? text[0].toUpperCase() + text.slice(1) : text);
