export const getCropRecommendations = async (payload: any) => {
  try {
    const res = await fetch("http://127.0.0.1:8000/predict", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    return await res.json();
  } catch (err) {
    console.error("API Error:", err);
    return null;
  }
};

export const getRotationSuggestions = async (payload: {
  prev_crop: string;
  N: number;
  P: number;
  K: number;
  top_n?: number;
}) => {
  try {
    const res = await fetch("http://127.0.0.1:8000/rotation/suggestions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    return await res.json();
  } catch (err) {
    console.error("Rotation API Error:", err);
    return null;
  }
};

export const getRotationPlan = async (payload: {
  season1_crop: string;
  N?: number;
  P?: number;
  K?: number;
  ph?: number;
  lat?: number;
  lon?: number;
  district?: string;
  mode?: "auto" | "coords";
  top_n?: number;
}) => {
  try {
    const res = await fetch("http://127.0.0.1:8000/rotation/plan", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    return await res.json();
  } catch (err) {
    console.error("Rotation Plan API Error:", err);
    return null;
  }
};

export const getFertilizerRecommendation = async (payload: {
  crop: string;
  soil: string;
  N?: number;
  P?: number;
  K?: number;
  PH?: number;
  lat?: number;
  lon?: number;
  district?: string;
  mode?: "auto" | "coords";
  top_k?: number;
}) => {
  try {
    const res = await fetch("http://127.0.0.1:8000/fertilizer/recommend", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    return await res.json();
  } catch (err) {
    console.error("Fertilizer API Error:", err);
    return null;
  }
};

export const getDefaultNPK = async (payload: {
  district?: string;
  lat?: number;
  lon?: number;
  mode?: "auto" | "coords";
}) => {
  try {
    const res = await fetch("http://127.0.0.1:8000/location/default-npk", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    return await res.json();
  } catch (err) {
    console.error("Default NPK API Error:", err);
    return null;
  }
};