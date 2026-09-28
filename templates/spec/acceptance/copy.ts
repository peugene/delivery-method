// Interface labels: key -> visible text, read from spec/ui/copy.<LOCALE>.json.
// Tests find elements by these texts, never by the structure of the page.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const locale = process.env.LOCALE ?? 'fr';
const file = join(__dirname, '..', 'ui', `copy.${locale}.json`);
const catalogue: Record<string, string> = JSON.parse(readFileSync(file, 'utf8'));

// copy('lists.count', { count: 3 }) fills the {count} placeholder of the label.
export function copy(key: string, values: Record<string, string | number> = {}): string {
  const text = catalogue[key];
  if (text === undefined) {
    throw new Error(`label key '${key}' is missing from ${file}`);
  }
  return text.replace(/\{(\w+)\}/g, (whole, name) => (name in values ? String(values[name]) : whole));
}
