const cropMap: Record<string, string> = {
  rice: "Paddy",
  maize: "Maize",
  wheat: "Wheat",
  cotton: "Cotton",
  onion: "Onion",
  tomato: "Tomato",
};

export const mapCropName = (name: string) => {
  return cropMap[name?.toLowerCase()] || name;
};