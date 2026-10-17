// Vercel Serverless Function: POST /api/paddleocr/scan
// Dynamic Timetable Extraction Endpoint for HabitLoop

export default async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") {
    return res.status(200).end();
  }

  if (req.method !== "POST") {
    return res.status(405).json({ success: false, error: "Method not allowed" });
  }

  try {
    const { isSample } = req.body || {};
    if (isSample) {
      return res.status(200).json({
        success: true,
        engine: "Sample",
        classes: [
          { subject: "Sample Class 1", day: "mon", start: 480, end: 530 },
          { subject: "Sample Class 2", day: "mon", start: 580, end: 630 }
        ]
      });
    }

    // Route to client-side high-precision document OCR engine
    return res.status(200).json({
      success: false,
      fallback_client_ocr: true,
      message: "Routing to client high-precision document OCR engine."
    });
  } catch (err) {
    return res.status(500).json({ success: false, error: err.message || "OCR execution error" });
  }
}
