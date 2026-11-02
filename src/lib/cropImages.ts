/**
 * Crop imagery.
 *
 * A photo lives at /public/crops/<slug>.webp. When a photo is missing we show
 * a tinted leaf tile whose hue is derived from the crop name — never another
 * crop's photo. Adding the real WebP files is a drop-in: no code change.
 */

export const CROP_SLUGS = [
  'rice', 'wheat', 'maize', 'cotton', 'sugarcane', 'soybean', 'groundnut',
  'mustard', 'chickpea', 'pigeonpeas', 'mungbean', 'blackgram', 'lentil',
  'jute', 'coffee', 'tea', 'banana', 'mango', 'grapes', 'orange', 'apple',
  'pomegranate', 'watermelon', 'muskmelon', 'papaya', 'coconut', 'tomato',
  'onion', 'potato', 'brinjal', 'cabbage', 'cauliflower', 'okra', 'chilli',
  'turmeric', 'ginger', 'garlic', 'coriander', 'cumin', 'sesame', 'castor',
  'sunflower', 'barley', 'ragi', 'jowar', 'bajra', 'navybean', 'kidneybeans',
  'mothbeans', 'pigeonpea', 'cardamom', 'rubber', 'cocoa', 'pepper',
] as const;

/** Normalise "Pigeon Peas (Tur)" → "pigeonpeas". */
export function cropSlug(name: string): string {
  return (name || '')
    .toLowerCase()
    .replace(/\(.*?\)/g, ' ')
    .replace(/[^a-z]+/g, '')
    .trim();
}

export function cropImage(name: string): string | null {
  const slug = cropSlug(name);
  return (CROP_SLUGS as readonly string[]).includes(slug) ? `/crops/${slug}.webp` : null;
}

/** Stable hue per crop so the fallback tiles are visibly different. */
export function cropTint(name: string): { from: string; to: string } {
  let h = 0;
  const s = cropSlug(name) || 'crop';
  for (let i = 0; i < s.length; i += 1) h = (h * 31 + s.charCodeAt(i)) % 360;
  const hue = 90 + (h % 90); // stay inside the green→gold band
  return {
    from: `hsl(${hue} 46% 42%)`,
    to: `hsl(${(hue + 28) % 360} 58% 30%)`,
  };
}
