// Vercel Serverless Function: POST /api/sarvam/scan
// Proxies Sarvam AI Document Intelligence API with zero client-side CORS issues

export default async function handler(req, res) {
  // Set CORS headers
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, api-subscription-key");

  if (req.method === "OPTIONS") {
    return res.status(200).end();
  }

  if (req.method !== "POST") {
    return res.status(405).json({ success: false, error: "Method not allowed" });
  }

  try {
    const { image, apiKey } = req.body || {};
    const key = apiKey || "sk_y6l3slkk_G9xv4vDO8QRMsghTbAe6e4HN";

    if (!image) {
      return res.status(400).json({ success: false, error: "No image provided" });
    }

    let buffer;
    if (typeof image === "string" && image.startsWith("data:")) {
      const base64Data = image.split(",")[1];
      buffer = Buffer.from(base64Data, "base64");
    } else if (typeof image === "string" && (image.startsWith("http://") || image.startsWith("https://"))) {
      const fetched = await fetch(image);
      const arrayBuf = await fetched.arrayBuffer();
      buffer = Buffer.from(arrayBuf);
    } else if (typeof image === "string") {
      buffer = Buffer.from(image, "base64");
    } else {
      return res.status(400).json({ success: false, error: "Invalid image format" });
    }

    const blob = new Blob([buffer], { type: "image/jpeg" });
    const formData = new FormData();
    formData.append("file", blob, "timetable.jpg");
    formData.append("language", "en-IN");
    formData.append("content_type", "printed");

    const startResp = await fetch("https://api.sarvam.ai/doc-ai/v1/job/digitise", {
      method: "POST",
      headers: {
        "api-subscription-key": key,
      },
      body: formData,
    });

    if (!startResp.ok) {
      const errText = await startResp.text();
      return res.status(startResp.status).json({ success: false, error: `Sarvam AI API error: ${errText}` });
    }

    const startData = await startResp.json();
    const jobId = startData.job_id;

    // Poll status until completion
    let completed = false;
    for (let i = 0; i < 40; i++) {
      await new Promise((r) => setTimeout(r, 1000));
      const statusResp = await fetch(`https://api.sarvam.ai/doc-ai/v1/job/${jobId}/status`, {
        headers: { "api-subscription-key": key },
      });
      if (statusResp.ok) {
        const sData = await statusResp.json();
        if (sData.status === "completed") {
          completed = true;
          break;
        } else if (sData.status === "failed" || sData.status === "rejected") {
          return res.status(500).json({ success: false, error: "Sarvam digitise job failed" });
        }
      }
    }

    if (!completed) {
      return res.status(504).json({ success: false, error: "Sarvam digitise job timed out" });
    }

    // Fetch digitized layout results
    const resultsResp = await fetch(`https://api.sarvam.ai/doc-ai/v1/job/${jobId}/results`, {
      headers: { "api-subscription-key": key },
    });

    if (!resultsResp.ok) {
      return res.status(500).json({ success: false, error: "Failed to fetch Sarvam results" });
    }

    const resData = await resultsResp.json();
    let tableHtml = null;
    try {
      const pages = resData.documents?.[0]?.pages || [];
      for (const p of pages) {
        for (const b of p.blocks || []) {
          if (b.layout_tag === "table" && !tableHtml) {
            tableHtml = b.text;
          }
        }
      }
    } catch {}

    return res.status(200).json({
      success: true,
      job_id: jobId,
      table_html: tableHtml,
      raw: resData,
    });
  } catch (err) {
    return res.status(500).json({ success: false, error: err.message || "Internal server error" });
  }
}
