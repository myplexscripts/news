// Screen state belongs to a destination, independently of its history entry.
// Keep content in memory so returning never swaps the list under the reader.
const screens = new Map();
const positions = new Map();
const LIMIT = 40;
export function readScreen(key) { return screens.get(key); }
export function rememberScreen(key, state) {
  screens.delete(key);
  screens.set(key, state);
  if (screens.size > LIMIT) screens.delete(screens.keys().next().value);
}
export function rememberPosition(url, position) {
  positions.delete(url);
  positions.set(url, position);
  if (positions.size > LIMIT) positions.delete(positions.keys().next().value);
}
export function readPosition(url) { return positions.get(url); }
