# HabitLoop 🚀
### Intelligent Habit Tracker & Adaptive Schedule Manager with Sarvam AI Vision

HabitLoop (HabitFlow × Ramp) is a modern productivity and schedule management workspace designed for students and professionals. It combines cognitive load-balanced habit tracking (Ramp vs. Boulder tasks) with an interactive weekly schedule and an AI-powered timetable digitizer powered by **Sarvam AI Document Intelligence**.

---

## ✨ Features

- 📅 **Interactive Weekly Timetable**:
  - Full weekly agenda (Mon–Sat) with period time slots and multi-slot lab blocks.
  - Visual energy curve mapping throughout the day.
  - Dynamic free block detection between lectures and scheduled tasks.

- 📷 **Sarvam AI Document Intelligence Timetable OCR**:
  - Native integration with Sarvam AI's Document Intelligence API (`doc-ai/v1/job/digitise`).
  - Converts timetable photos or digital charts into structured weekly class agendas.
  - Handles complex university layouts: period headers, multi-period lab blocks (e.g., C1/C2 batch splits), teacher initials, and lecture hall codes.
  - Built-in review and verification table to adjust classes before committing to your schedule.

- 🏛️ **Trainable In-Browser OCR Engine (Offline)**:
  - 100% client-side fallback with coordinate gradient alignment and spatial clustering.
  - Trainable parameters: start times, slot durations, total periods, margins, and subject acronym dictionary.
  - Interactive training loop with real-time loss and accuracy metrics.

- 🔄 **Habit Tracking & Cognitive Load (Ramp vs. Boulder)**:
  - Track daily and weekly habits with streak counters.
  - Categorize tasks into **Ramp** (warm-up, low mental resistance) and **Boulder** (high-focus deep work).
  - One-click scheduling of habits directly into your daily timeline.

- 🍅 **Built-in Focus Tools**:
  - Fullscreen Pomodoro timer with custom focus/break intervals and cycle tracking.
  - Smart hydration reminder alerts.
  - Daily target checklist and evening debriefs.

---

## 🚀 Quick Start

### Prerequisites
- Python 3.7+ (uses only Python standard library — zero `pip install` required!)
- Any modern web browser (Chrome, Safari, Edge, Firefox)

### 1. Clone the Repository
```bash
git clone https://github.com/amit047-byte/HabitLoop.git
cd HabitLoop
```

### 2. Launch Local Server
Run the lightweight server (serves the application and provides the Sarvam AI API proxy):
```bash
python3 server.py
```

### 3. Open in Browser
Visit **[http://localhost:8080](http://localhost:8080)** in your browser.

*(Note: You can also open `index.html` directly in a browser. When running directly via `file://`, the client gracefully falls back to the calibrated local engine).*

---

## 🔑 Sarvam AI API Key Configuration

To scan custom timetable images using Sarvam AI Vision:
1. Open the application at `http://localhost:8080`.
2. In the **Schedule & Ramp** view, click **"API Key Settings"** in the OCR bar.
3. Enter your Sarvam AI subscription key (obtained from [sarvam.ai](https://www.sarvam.ai/)).
4. Keys are stored safely in browser `localStorage`.

---

## 📁 Project Structure

```text
HabitLoop/
├── index.html                  # Single-file React 18 application with Lucide icons
├── server.py                   # Local development server and Sarvam AI proxy
├── jecrc_section_c_clean.jpg   # Sample calibrated clean digital timetable
├── jecrc_section_c_timetable.jpg # Sample classroom poster timetable
├── sarvam_clean_table.html     # Digitized layout table extracted by Sarvam AI
├── sarvam_clean_result.json    # Complete Document Intelligence API response
├── README.md                   # Project documentation
└── .gitignore                  # Git ignore rules
```

---

## 🛠️ Tech Stack

- **Frontend**: React 18 (Standalone ESM), Lucide React Icons, Space Grotesk & IBM Plex Sans fonts
- **Backend / Proxy**: Python 3 `http.server`, `urllib.request` (Zero third-party dependencies)
- **AI / Vision**: Sarvam AI Document Intelligence (`en-IN` printed table OCR)
- **Storage**: Browser `localStorage` (Offline-first architecture)

---

## 📄 License

MIT License. Feel free to use, modify, and distribute.
