// Explainer registry built from docs/EXPLAINERS.md by scripts/build_explainers.ts (task M1.3).
// Until M1.3 lands the registry is empty and every lookup returns undefined.

export type ExplainerField = "title" | "what" | "why" | "real" | "fake" | "read" | "text";
export type Explainer = Partial<Record<ExplainerField, string>>;

const registry: Record<string, Explainer> = {};

export function explain(key: string): Explainer | undefined {
  return registry[key];
}
