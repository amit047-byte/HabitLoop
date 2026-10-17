// Vercel Serverless Function: POST /api/sarvam/scan (Alias to PaddleOCR-VL v1.6)
import paddleHandler from "../paddleocr/scan.js";

export default async function handler(req, res) {
  return paddleHandler(req, res);
}
