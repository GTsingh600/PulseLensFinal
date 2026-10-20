/**
 * The one clock (CLAUDE.md rule 1). Every client timestamp is performance.now() in ms, or a frame time
 * mapped into that domain. Never use Date.now() in echo maths.
 */
export const now = (): number => performance.now();
