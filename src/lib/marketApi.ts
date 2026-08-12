const BASE_URL =
  "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070";

const API_KEY = "579b464db66ec23bdd0000010b138cdcddfa47526650163ba46d0b07"; // 🔴 replace

// 🔥 DISTRICT NORMALIZATION (VERY IMPORTANT)
const districtMap: Record<string, string> = {
  belagavi: "Belgaum",
  bengaluru: "Bangalore",
};

// 🔥 CLEAN DISTRICT NAME
const normalizeDistrict = (district: string) => {
  if (!district) return "";

  const clean = district.split(",")[0].trim().toLowerCase();

  return districtMap[clean] || district.split(",")[0].trim();
};

export const getMarketPrice = async (crop: string, district: string) => {
  try {
    const cleanDistrict = normalizeDistrict(district);

    console.log("🔍 API CALL:", crop, cleanDistrict);

    // 🔁 COMMON FETCH FUNCTION
    const fetchData = async (url: string) => {
      const res = await fetch(url);
      const data = await res.json();

      console.log("📦 API RESPONSE:", data);

      if (data.records && data.records.length > 0) {
        return data.records[0];
      }

      return null;
    };

    // ✅ 1. TRY DISTRICT
    let result = await fetchData(
      `${BASE_URL}?api-key=${API_KEY}&format=json&limit=1&filters[commodity]=${crop}&filters[district]=${cleanDistrict}`
    );

    // ✅ 2. FALLBACK → ANY DISTRICT (VERY IMPORTANT)
    if (!result) {
      console.log("⚠️ No district data, trying global fallback...");

      result = await fetchData(
        `${BASE_URL}?api-key=${API_KEY}&format=json&limit=1&filters[commodity]=${crop}`
      );
    }

    // ❌ STILL NOTHING
    if (!result) {
      console.log("❌ No data found for:", crop);
      return null;
    }

    // ✅ SAFE PARSE
    return {
      modal: result.modal_price ? Number(result.modal_price) : null,
      min: result.min_price ? Number(result.min_price) : null,
      max: result.max_price ? Number(result.max_price) : null,
      market: result.market || "",
    };

  } catch (e) {
    console.log("❌ Market API error:", e);
    return null;
  }
};