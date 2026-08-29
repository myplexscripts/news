const SOURCE_LOGO_FILES: Record<string, string> = {
  'global news london': 'Global_News.svg',
  'global news': 'Global_News.svg',
  'cbc news london': 'CBC_News_Logo.svg',
  'cbc news': 'CBC_News_Logo.svg',
  'london free press': 'The_London_Free_Press_Logo.svg',
  'ctv news': 'CTVNews_horizontal_logo.svg',
  '106.9 the x': '1069thex.png',
  'city of london newsroom': 'CoL.png',
  'city of london': 'CoL.png',
  'london police service': 'lps.svg',
  'london fire department': 'lfd.png',
  '104.7 heart fm': 'heartfm.png',
  'heart fm': 'heartfm.png',
  'google news london discovery': 'google.png',
  'google news': 'google.png',
  'cnn': 'cnn.png',
  'cnn news': 'cnn.png',
  'the new york times': 'nyt.png',
  'new york times': 'nyt.png',
  'nyt': 'nyt.png',
  'vox': 'vox.png'
};

export function sourceLogoFile(name = ''): string {
  const normalized = name.trim().toLowerCase();
  if (SOURCE_LOGO_FILES[normalized]) return SOURCE_LOGO_FILES[normalized];
  if (normalized.includes('global news')) return 'Global_News.svg';
  if (normalized.includes('cbc')) return 'CBC_News_Logo.svg';
  if (normalized.includes('london free press') || normalized.includes('lfpress')) return 'The_London_Free_Press_Logo.svg';
  if (normalized.includes('ctv')) return 'CTVNews_horizontal_logo.svg';
  if (normalized.includes('106.9') || normalized.includes('the x')) return '1069thex.png';
  if (normalized.includes('heart fm')) return 'heartfm.png';
  if (normalized.includes('city of london')) return 'CoL.png';
  if (normalized.includes('london police')) return 'lps.svg';
  if (normalized.includes('london fire')) return 'lfd.png';
  if (normalized.includes('google news')) return 'google.png';
  if (normalized === 'cnn' || normalized.includes('cnn.com')) return 'cnn.png';
  if (normalized.includes('new york times') || normalized === 'nyt') return 'nyt.png';
  if (normalized === 'vox' || normalized.includes('vox.com')) return 'vox.png';
  return '';
}

export function sourceLogoPath(name: string, base = '/'): string {
  const file = sourceLogoFile(name);
  if (!file) return '';
  const cleanBase = base.endsWith('/') ? base : `${base}/`;
  return `${cleanBase}images/logos/${file}`;
}
