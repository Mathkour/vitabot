export interface Country {
  name: string;
  iso2: string;
  dialCode: string;
}

export const COUNTRIES: Country[] = [
  { name: 'Jordan', iso2: 'jo', dialCode: '+962' },
  { name: 'Saudi Arabia', iso2: 'sa', dialCode: '+966' },
  { name: 'UAE', iso2: 'ae', dialCode: '+971' },
  { name: 'Kuwait', iso2: 'kw', dialCode: '+965' },
  { name: 'Qatar', iso2: 'qa', dialCode: '+974' },
  { name: 'Bahrain', iso2: 'bh', dialCode: '+973' },
  { name: 'Oman', iso2: 'om', dialCode: '+968' },
  { name: 'Lebanon', iso2: 'lb', dialCode: '+961' },
  { name: 'Egypt', iso2: 'eg', dialCode: '+20' },
  { name: 'Iraq', iso2: 'iq', dialCode: '+964' },
  { name: 'Syria', iso2: 'sy', dialCode: '+963' },
  { name: 'Palestine', iso2: 'ps', dialCode: '+970' },
  { name: 'UK', iso2: 'gb', dialCode: '+44' },
  { name: 'USA', iso2: 'us', dialCode: '+1' },
  { name: 'Germany', iso2: 'de', dialCode: '+49' },
  { name: 'France', iso2: 'fr', dialCode: '+33' },
];

export function flagUrl(iso2: string): string {
  return `https://flagcdn.com/24x18/${iso2}.png`;
}
