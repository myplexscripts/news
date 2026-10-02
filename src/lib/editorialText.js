// Remove only known publisher suffixes, never rewrite reporting.
export function cleanTitle(value = '') {
  return String(value).replace(/\s+[-|–—]\s*(?:CBC(?:\.CA| News)?|CTV News(?: London)?|Global News(?: London)?)(?:\s*[-|–—]\s*.*)?$/i, '').trim();
}
export function cleanSummary(value = '', title = '') {
  const text = cleanTitle(value);
  const key = (input) => String(input).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  const summaryKey = key(text.replace(/\s+(?:CBC|CTV|Global News)$/i, ''));
  return summaryKey === key(cleanTitle(title)) ? '' : text;
}
