// Vercel Serverless Function: GET/POST /api/sync
// Relays timetable photo upload from mobile phone to desktop session

global._hlSessions = global._hlSessions || new Map();

export default async function handler(req, res) {
  // Set CORS headers
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") {
    return res.status(200).end();
  }

  const { searchParams } = new URL(req.url, `http://${req.headers.host || "localhost"}`);
  const session = searchParams.get("session") || (req.body && req.body.session);

  if (!session) {
    return res.status(400).json({ success: false, error: "Missing session parameter" });
  }

  // Handle mobile upload POST
  if (req.method === "POST") {
    const { image, name } = req.body || {};
    if (!image) {
      return res.status(400).json({ success: false, error: "Missing image payload" });
    }

    global._hlSessions.set(session, {
      image,
      name: name || "mobile_timetable.jpg",
      timestamp: Date.now(),
    });

    return res.status(200).json({
      success: true,
      message: "Mobile timetable received and queued for desktop session.",
    });
  }

  // Handle desktop polling GET
  if (req.method === "GET") {
    if (global._hlSessions.has(session)) {
      const data = global._hlSessions.get(session);
      global._hlSessions.delete(session);
      return res.status(200).json({
        success: true,
        ready: true,
        data,
      });
    }

    return res.status(200).json({
      success: true,
      ready: false,
    });
  }

  return res.status(405).json({ success: false, error: "Method not allowed" });
}
