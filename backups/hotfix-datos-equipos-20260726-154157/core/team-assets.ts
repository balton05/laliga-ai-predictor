export interface TeamAsset {
  name: string;
  slug: string;
  city: string;
  stadiumName: string;
  badge: string;
  stadium: string;
}

const asset = (
  name: string,
  slug: string,
  city: string,
  stadiumName: string,
): TeamAsset => ({
  name,
  slug,
  city,
  stadiumName,
  badge: `assets/teams/${slug}.png`,
  stadium: `assets/stadiums/${slug}.webp`,
});

export const TEAM_ASSETS: readonly TeamAsset[] = [
  asset('Athletic Club', 'athletic', 'Bilbao', 'San Mamés'),
  asset('Atlético de Madrid', 'atletico-madrid', 'Madrid', 'Metropolitano'),
  asset('CA Osasuna', 'osasuna', 'Pamplona', 'El Sadar'),
  asset('Deportivo Alavés', 'alaves', 'Vitoria-Gasteiz', 'Mendizorroza'),
  asset('Elche CF', 'elche', 'Elche', 'Martínez Valero'),
  asset('FC Barcelona', 'barcelona', 'Barcelona', 'Spotify Camp Nou'),
  asset('Getafe CF', 'getafe', 'Getafe', 'Coliseum'),
  asset('Levante UD', 'levante', 'Valencia', 'Ciutat de València'),
  asset('Málaga CF', 'malaga', 'Málaga', 'La Rosaleda'),
  asset('R. Racing Club', 'racing-santander', 'Santander', 'El Sardinero'),
  asset('RC Celta', 'celta', 'Vigo', 'Balaídos'),
  asset('RC Deportivo', 'deportivo', 'A Coruña', 'Riazor'),
  asset(
    'RCD Espanyol de Barcelona',
    'espanyol',
    'Barcelona',
    'RCDE Stadium',
  ),
  asset('Rayo Vallecano', 'rayo-vallecano', 'Madrid', 'Vallecas'),
  asset('Real Betis', 'betis', 'Sevilla', 'Benito Villamarín'),
  asset('Real Madrid', 'real-madrid', 'Madrid', 'Santiago Bernabéu'),
  asset('Real Sociedad', 'real-sociedad', 'San Sebastián', 'Anoeta'),
  asset('Sevilla FC', 'sevilla', 'Sevilla', 'Ramón Sánchez-Pizjuán'),
  asset('Valencia CF', 'valencia', 'Valencia', 'Mestalla'),
  asset('Villarreal CF', 'villarreal', 'Villarreal', 'La Cerámica'),
];

const normalize = (value: string): string =>
  value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();

const aliases: Record<string, string> = {
  'atletico madrid': 'atletico-madrid',
  'atletico de madrid': 'atletico-madrid',
  'barcelona': 'barcelona',
  'deportivo': 'deportivo',
  'deportivo la coruna': 'deportivo',
  'espanyol': 'espanyol',
  'espanyol barcelona': 'espanyol',
  'rcd espanyol': 'espanyol',
  'rcd espanyol barcelona': 'espanyol',
  'real club deportivo espanyol': 'espanyol',
  'r racing club': 'racing-santander',
  'racing': 'racing-santander',
  'racing club': 'racing-santander',
  'racing de santander': 'racing-santander',
  'racing santander': 'racing-santander',
  'real racing club': 'racing-santander',
  'real racing club de santander': 'racing-santander',
};

const byName = new Map(
  TEAM_ASSETS.map((team) => [normalize(team.name), team] as const),
);
const bySlug = new Map(TEAM_ASSETS.map((team) => [team.slug, team] as const));

export const teamAssetByName = (name: string): TeamAsset | undefined => {
  const key = normalize(name);
  const directMatch =
    byName.get(key) ?? bySlug.get(aliases[key] ?? key.replace(/ /g, '-'));

  if (directMatch) return directMatch;
  if (key.includes('espanyol')) return bySlug.get('espanyol');
  if (key.includes('racing')) return bySlug.get('racing-santander');

  return undefined;
};

export const teamAssetBySlug = (slug: string): TeamAsset | undefined =>
  bySlug.get(slug);

export const teamBadge = (name: string): string =>
  teamAssetByName(name)?.badge ?? 'assets/teams/default-team.svg';

export const teamStadium = (name: string): string =>
  teamAssetByName(name)?.stadium ?? 'assets/stadiums/default-stadium.svg';
