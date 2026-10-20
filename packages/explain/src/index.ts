// Explainer registry built from docs/EXPLAINERS.md by scripts/build_explainers.ts (`make explainers`).
// Every on-screen explanation comes from here, word for word (CLAUDE.md rule 5).
import { explainers } from "./explainers.gen";
import type { Explainer } from "./parse";

export type { Explainer, ExplainerField } from "./parse";
export { explainerFields } from "./parse";

/** Every key in EXPLAINERS.md. A typo in a key is a type error. */
export type ExplainerKey = keyof typeof explainers;

export function explain(key: ExplainerKey): Explainer {
  return explainers[key];
}

/** For keys that arrive at runtime (server messages, plan reasons); undefined when unknown. */
export function explainMaybe(key: string): Explainer | undefined {
  return isExplainerKey(key) ? explainers[key] : undefined;
}

export function isExplainerKey(key: string): key is ExplainerKey {
  return Object.hasOwn(explainers, key);
}
