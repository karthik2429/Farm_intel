const cropMap: Record<string, string> = {
  rice: "Paddy",
  maize: "Maize",
  wheat: "Wheat",
  cotton: "Cotton",
  onion: "Onion",
  tomato: "Tomato",
};

export const mapCropName = (name: string) => {
  // "Tur (Pigeon Pea)" -> "Tur", "Jowar (Sorghum)" -> "Jowar" so the
  // AGMARKNET commodity filter matches real mandi records.
  const base = (name || "").toLowerCase().split("(")[0].trim();
  if (cropMap[base]) return cropMap[base];
  if (!base) return name;
  return base.charAt(0).toUpperCase() + base.slice(1);
};
