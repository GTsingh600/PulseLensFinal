// Parser for docs/EXPLAINERS.md: `### <key>` headings followed by `- field: text` lines.
// Pure (string in, object out) so the build script and the tests share it.

export const explainerFields = ["title", "what", "why", "real", "fake", "read", "text"] as const;
export type ExplainerField = (typeof explainerFields)[number];
export type Explainer = Partial<Record<ExplainerField, string>>;

const HEADING = /^###\s+(\S+)\s*$/;
const FIELD = /^-\s+(\w+):\s+(.+?)\s*$/;

export function parseExplainers(markdown: string): Record<string, Explainer> {
  const out: Record<string, Explainer> = {};
  let current: Explainer | null = null;
  let key = "";
  for (const line of markdown.split(/\r?\n/)) {
    const heading = HEADING.exec(line);
    if (heading) {
      key = heading[1]!;
      if (key in out) throw new Error(`EXPLAINERS.md: duplicate key ${key}`);
      current = out[key] = {};
      continue;
    }
    if (line.startsWith("#")) {
      current = null; // a ## section heading ends the entry
      continue;
    }
    const field = current && FIELD.exec(line);
    if (current && field) {
      const name = field[1] as ExplainerField;
      if (!explainerFields.includes(name)) throw new Error(`EXPLAINERS.md: unknown field "${name}" in ${key}`);
      current[name] = field[2]!;
    }
  }
  for (const [k, e] of Object.entries(out)) {
    if (Object.keys(e).length === 0) throw new Error(`EXPLAINERS.md: ${k} has no fields`);
  }
  return out;
}
