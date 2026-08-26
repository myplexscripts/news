const SOURCE_LOGO_FILES: Record<string, string> = {
  'global news london': 'global.png',
  'global news': 'global.png',
  'cbc news london': 'cbc.png',
  'cbc news': 'cbc.png',
  'london free press': 'lfp.png',
  'ctv news': 'ctv.png',
  '106.9 the x': '1069thex.png',
  'city of london newsroom': 'CoL.png',
  'city of london': 'CoL.png',
  'london police service': 'lps.png',
  'london fire department': 'lfd.png',
  '104.7 heart fm': 'heartfm.png',
  'heart fm': 'heartfm.png',
  'google news london discovery': 'google.png',
  'google news': 'google.png'
};

export function sourceLogoFile(name = ''): string {
  const normalized = name.trim().toLowerCase();
  if (SOURCE_LOGO_FILES[normalized]) return SOURCE_LOGO_FILES[normalized];
  if (normalized.includes('global news')) return 'global.png';
  if (normalized.includes('cbc')) return 'cbc.png';
  if (normalized.includes('london free press') || normalized.includes('lfpress')) return 'lfp.png';
  if (normalized.includes('ctv')) return 'ctv.png';
  if (normalized.includes('106.9') || normalized.includes('the x')) return '1069thex.png';
  if (normalized.includes('heart fm')) return 'heartfm.png';
  if (normalized.includes('city of london')) return 'CoL.png';
  if (normalized.includes('london police')) return 'lps.png';
  if (normalized.includes('london fire')) return 'lfd.png';
  if (normalized.includes('google news')) return 'google.png';
  return '';
}

export function sourceLogoPath(name: string, base = '/'): string {
  const file = sourceLogoFile(name);
  if (!file) return '';
  const cleanBase = base.endsWith('/') ? base : `${base}/`;
  return `${cleanBase}images/logos/${file}`;
}
