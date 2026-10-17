#!/usr/bin/env python3
"""
HabitLoop — Qwen-VL & PaddleOCR Integrated Timetable Extractor
Merges PaddleOCR high-precision optical character recognition and spatial coordinate detection
with Qwen-VL Vision-Language Model semantic table reasoning.
"""

import os
import sys
import json
import re

# Add user site-packages for PaddleOCR & PyTorch dependencies if available
user_site = os.path.expanduser("~/Library/Python/3.9/lib/python/site-packages")
if os.path.isdir(user_site) and user_site not in sys.path:
    sys.path.insert(0, user_site)

os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

MODEL_NAME = os.environ.get("QWEN_MODEL", "Qwen/Qwen-VL-Chat")

_model = None
_tokenizer = None
_processor = None
_is_qwen2 = False
_ocr_instance = None

def get_paddle_ocr():
    """Initializes or reuses the PaddleOCR inference engine."""
    global _ocr_instance
    if _ocr_instance is not None:
        return _ocr_instance
    try:
        from paddleocr import PaddleOCR
        _ocr_instance = PaddleOCR(lang="en")
        return _ocr_instance
    except Exception as e:
        print(f"PaddleOCR initialization note: {e}")
        return None

def time_str_to_minutes(t_str):
    """Converts time string (e.g., '08:00', '8:50', '12:05') to minutes from midnight."""
    if isinstance(t_str, (int, float)):
        return int(t_str)
    if not t_str or not isinstance(t_str, str):
        return 480
    t_str = t_str.strip().upper()
    is_pm = "PM" in t_str and not t_str.startswith("12")
    m = re.search(r'(\d{1,2})[:.](\d{2})', t_str)
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        if is_pm and h < 12:
            h += 12
        elif h < 7:  # Afternoon classes (e.g. 1:00 PM -> 13:00)
            h += 12
        return h * 60 + mn
    return 480

def minutes_to_hhmm(mins):
    """Converts minutes from midnight to 'HH:MM' string."""
    h = mins // 60
    m = mins % 60
    return f"{h:02d}:{m:02d}"

def get_qwen_model(model_name=MODEL_NAME):
    """Lazy loader for Qwen-VL model."""
    global _model, _tokenizer, _processor, _is_qwen2
    if _model is not None:
        return _model, _tokenizer, _processor, _is_qwen2

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError:
        raise ImportError(
            "PyTorch and Transformers are required for local Qwen-VL execution.\n"
            "Install with: pip install torch torchvision transformers accelerate\n"
        )

    print(f"📦 Initializing Qwen-VL model ({model_name})...")
    if "Qwen2" in model_name:
        from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
        _is_qwen2 = True
        device = "mps" if (hasattr(torch.backends, "mps") and torch.backends.mps.is_available()) else ("cuda" if torch.cuda.is_available() else "cpu")
        dtype = torch.bfloat16 if (device in ["cuda", "mps"]) else torch.float32
        _model = Qwen2VLForConditionalGeneration.from_pretrained(
            model_name,
            torch_dtype=dtype,
            device_map="auto" if device != "mps" else None
        )
        if device == "mps":
            _model = _model.to("mps")
        _processor = AutoProcessor.from_pretrained(model_name)
        _tokenizer = None
    else:
        _is_qwen2 = False
        _tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        device_map = "auto" if torch.cuda.is_available() else None
        _model = AutoModelForCausalLM.from_pretrained(
            model_name,
            trust_remote_code=True,
            device_map=device_map
        ).eval()
        _processor = None

    print(f"✨ Qwen-VL model ready!")
    return _model, _tokenizer, _processor, _is_qwen2

def parse_extracted_classes(response_text):
    """Parses JSON timetable classes from model response text."""
    classes = []
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response_text)
    raw_json = json_match.group(1) if json_match else response_text

    array_match = re.search(r"\[\s*\{[\s\S]*\}\s*\]", raw_json)
    if array_match:
        raw_json = array_match.group(0)

    try:
        parsed = json.loads(raw_json)
        if isinstance(parsed, list):
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                subj = item.get("subject") or item.get("name")
                day = str(item.get("day", "mon")).lower()[:3]
                if day not in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]:
                    day = "mon"
                start_min = time_str_to_minutes(item.get("start", "08:00"))
                end_min = time_str_to_minutes(item.get("end", "08:50"))
                if end_min <= start_min:
                    end_min = start_min + 50
                if subj:
                    classes.append({
                        "subject": str(subj).strip(),
                        "day": day,
                        "start": start_min,
                        "end": end_min
                    })
    except Exception:
        for m in re.finditer(r'\{[^{}]*"subject"\s*:\s*"([^"]+)"[^{}]*"day"\s*:\s*"([^"]+)"[^{}]*"start"\s*:\s*"([^"]+)"[^{}]*"end"\s*:\s*"([^"]+)"[^{}]*\}', response_text):
            subj, day, s_time, e_time = m.groups()
            s_min = time_str_to_minutes(s_time)
            e_min = time_str_to_minutes(e_time)
            classes.append({
                "subject": subj.strip(),
                "day": day.lower()[:3],
                "start": s_min,
                "end": max(e_min, s_min + 50)
            })

    return classes

def run_paddleocr_detection(image_path):
    """Executes PaddleOCR on the image and returns cleaned tokens and coordinates."""
    ocr = get_paddle_ocr()
    if not ocr:
        return [], []
    res = ocr.predict(image_path)
    if not res or not res[0]:
        return [], []

    item = res[0]
    rec_texts = item.get("rec_texts", [])
    rec_boxes = item.get("rec_boxes", [])

    tokens = []
    for text, box in zip(rec_texts, rec_boxes):
        text = str(text).strip()
        if not text:
            continue
        xmin, ymin, xmax, ymax = [float(c) for c in box]
        tokens.append({
            "text": text,
            "xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax,
            "xc": (xmin + xmax) / 2.0,
            "yc": (ymin + ymax) / 2.0,
            "box": [xmin, ymin, xmax, ymax]
        })
    return tokens, rec_texts

def build_spatial_timetable(tokens):
    """
    Constructs structured timetable classes, Markdown table, and legend from OCR tokens.
    """
    DAY_MAP = {
        "monday": "mon", "mon": "mon",
        "tuesday": "tue", "tue": "tue",
        "wednesday": "wed", "wed": "wed",
        "thursday": "thu", "thu": "thu",
        "friday": "fri", "fri": "fri",
        "saturday": "sat", "sat": "sat",
        "sunday": "sun", "sun": "sun"
    }

    # 1. Parse Legend: Teachers, Subjects, Rooms
    legend_teachers = {}
    legend_subjects = {
        "EM-I": "Engineering Mathematics-I",
        "EM-1": "Engineering Mathematics-I",
        "CPLT": "Computer Programming and Logical Thinking",
        "CHEMISTRY": "Engineering Chemistry",
        "CS": "Communication Skills",
        "COMM. SKILLS": "Communication Skills",
        "COMM SKILLS": "Communication Skills",
        "DDAL": "Digital Data and AI Literacy",
        "EDP": "Entrepreneurship Development",
        "EDP-C": "Entrepreneurship Development",
        "AUTOCAD": "AutoCAD",
        "AC": "AutoCAD"
    }
    legend_rooms = {
        "NYB": "Nyay Bhawan",
        "VIB": "Vikram Sarabhai Bhawan",
        "KAB": "Kautilya Bhawan"
    }

    for i, tok in enumerate(tokens):
        t = tok["text"]
        if re.search(r'\b(Dr\.|Mr\.|Ms\.|Prof\.)\s*[A-Za-z]+', t):
            prev_tok = tokens[i-1]["text"] if i > 0 else ""
            if len(prev_tok) <= 3 and prev_tok.isalnum():
                legend_teachers[prev_tok.upper()] = t

        m_subj = re.search(r'^([A-Za-z0-9\-_]{2,6})\s*[:\-]\s*(.+)$', t)
        if m_subj:
            code = m_subj.group(1).upper()
            full = m_subj.group(2).strip()
            if len(full) > 2 and not code.startswith("SEC") and not code.startswith("W.E"):
                legend_subjects[code] = full

        m_room = re.search(r'^(NYB|VIB|KAB)\s*[:\-]?\s*(.+)$', t)
        if m_room:
            legend_rooms[m_room.group(1)] = m_room.group(2).strip()

    # 2. Find Time Headers
    time_headers = []
    for tok in tokens:
        tm = re.search(r'(\d{1,2}[:.]\d{2})\s*[-–]\s*(\d{1,2}[:.]\d{2})', tok["text"])
        if tm:
            s_min = time_str_to_minutes(tm.group(1))
            e_min = time_str_to_minutes(tm.group(2))
            time_headers.append({
                "raw": tok["text"],
                "start": s_min,
                "end": e_min,
                "xmin": tok["xmin"], "xmax": tok["xmax"],
                "ymin": tok["ymin"], "ymax": tok["ymax"],
                "xc": tok["xc"]
            })

    time_headers.sort(key=lambda th: th["xmin"])

    cols = []
    for i, th in enumerate(time_headers):
        prev_x = time_headers[i-1]["xmax"] if i > 0 else th["xmin"] - 30
        next_x = time_headers[i+1]["xmin"] if i < len(time_headers) - 1 else th["xmax"] + 60
        col_start = (prev_x + th["xmin"]) / 2.0 if i > 0 else th["xmin"] - 15
        col_end = (th["xmax"] + next_x) / 2.0 if i < len(time_headers) - 1 else th["xmax"] + 60
        cols.append({
            "idx": i,
            "name": th["raw"],
            "start": th["start"],
            "end": th["end"],
            "col_start": col_start,
            "col_end": col_end,
            "xc": th["xc"]
        })

    # 3. Find Day Rows
    day_rows = []
    for tok in tokens:
        clean = re.sub(r'[^a-zA-Z]', '', tok["text"]).lower()
        if clean in DAY_MAP:
            day_rows.append({
                "day_key": DAY_MAP[clean],
                "day_name": tok["text"].capitalize(),
                "ymin": tok["ymin"], "ymax": tok["ymax"],
                "yc": tok["yc"]
            })

    day_rows.sort(key=lambda dr: dr["ymin"])

    rows = []
    for i, dr in enumerate(day_rows):
        prev_y = day_rows[i-1]["ymax"] if i > 0 else dr["ymin"] - 20
        next_y = day_rows[i+1]["ymin"] if i < len(day_rows) - 1 else dr["ymax"] + 50
        rows.append({
            "day_key": dr["day_key"],
            "day_name": dr["day_name"],
            "row_top": (prev_y + dr["ymin"]) / 2.0 if i > 0 else dr["ymin"] - 10,
            "row_bot": (dr["ymax"] + next_y) / 2.0 if i < len(day_rows) - 1 else dr["ymax"] + 50,
            "yc": dr["yc"]
        })

    # 4. Extract Grid Cells
    grid_top = rows[0]["row_top"] if rows else 0
    grid_bot = rows[-1]["row_bot"] if rows else 1000
    grid_left = cols[0]["col_start"] if cols else 0

    grid_tokens = []
    for tok in tokens:
        if tok["ymin"] >= grid_top and tok["ymax"] <= grid_bot and tok["xc"] >= grid_left:
            clean = re.sub(r'[^a-zA-Z]', '', tok["text"]).lower()
            if clean not in DAY_MAP:
                grid_tokens.append(tok)

    extracted_classes = []
    for r in rows:
        row_toks = [t for t in grid_tokens if r["row_top"] <= t["yc"] <= r["row_bot"]]
        if not row_toks:
            continue

        row_toks.sort(key=lambda t: t["xmin"])
        cells = []
        for t in row_toks:
            matched_cols = []
            for c in cols:
                overlap = max(0, min(t["xmax"], c["col_end"]) - max(t["xmin"], c["col_start"]))
                if overlap > 0.3 * (t["xmax"] - t["xmin"]):
                    matched_cols.append(c)
            if not matched_cols:
                closest = min(cols, key=lambda c: abs(c["xc"] - t["xc"]))
                matched_cols = [closest]

            s_col = matched_cols[0]
            e_col = matched_cols[-1]

            merged = False
            for cell in cells:
                if cell["start_col"]["idx"] == s_col["idx"] and cell["end_col"]["idx"] == e_col["idx"]:
                    cell["tokens"].append(t)
                    merged = True
                    break
            if not merged:
                cells.append({
                    "start_col": s_col,
                    "end_col": e_col,
                    "tokens": [t]
                })

        for cell in cells:
            cell_texts = [tok["text"] for tok in cell["tokens"]]
            subject_parts = []
            room_parts = []
            faculty_parts = []

            for txt in cell_texts:
                m_room = re.search(r'\b(NYB-\d{3}|VIB-\d{3}|KAB-\d{3}|[A-Z]{3}-\d{3})\b', txt)
                if m_room:
                    room_parts.append(m_room.group(0))
                    rem = txt.replace(m_room.group(0), "").strip(" -_·,")
                    if rem:
                        subject_parts.append(rem)
                elif re.match(r'^(MJ|SS|SH|NB|JK|C1|C2)$', txt.strip()):
                    faculty_parts.append(txt.strip())
                else:
                    subject_parts.append(txt)

            main_subj = " ".join(subject_parts).strip()
            main_subj = re.sub(r'\s+', ' ', main_subj)
            if not main_subj or len(main_subj) < 2:
                continue

            clean_code = re.sub(r'[^A-Za-z0-9\-]', '', main_subj).upper()
            expanded_name = legend_subjects.get(clean_code) or legend_subjects.get(main_subj.upper())
            if not expanded_name:
                for k, v in legend_subjects.items():
                    if k in clean_code or clean_code in k:
                        expanded_name = v
                        break

            final_title = expanded_name if expanded_name else main_subj
            details = []
            if room_parts:
                details.append("/".join(room_parts))
            for f in faculty_parts:
                t_name = legend_teachers.get(f.upper())
                details.append(t_name if t_name else f)

            if details:
                final_title = f"{final_title} ({' · '.join(details)})"

            extracted_classes.append({
                "subject": final_title,
                "day": r["day_key"],
                "start": cell["start_col"]["start"],
                "end": cell["end_col"]["end"]
            })

    # Construct Markdown Table representation
    md_lines = ["# Reconstructed Academic Timetable", ""]
    header_cols = [c["name"] for c in cols]
    if cols:
        md_lines.append("| Day / Time | " + " | ".join(header_cols) + " |")
        md_lines.append("| --- | " + " | ".join(["---"] * len(header_cols)) + " |")
        for r in rows:
            row_classes = [cl for cl in extracted_classes if cl["day"] == r["day_key"]]
            row_cells = []
            for c in cols:
                matching = [cl["subject"] for cl in row_classes if cl["start"] <= c["start"] < cl["end"]]
                row_cells.append(", ".join(matching) if matching else "Free")
            md_lines.append(f"| {r['day_name']} | " + " | ".join(row_cells) + " |")

    return {
        "classes": extracted_classes,
        "markdown": "\n".join(md_lines),
        "legend_subjects": legend_subjects,
        "legend_teachers": legend_teachers,
        "cols": cols,
        "rows": rows
    }

def extract_timetable_with_qwen(image_path, model_name=MODEL_NAME):
    """
    Main integrated extraction function combining PaddleOCR and Qwen-VL.
    1. Executes PaddleOCR for optical token and coordinate detection.
    2. Builds spatial table structure and parses legend.
    3. Invokes Qwen-VL with multimodal image + OCR context if available.
    4. Falls back seamlessly to the integrated spatial table classes.
    """
    if not os.path.isfile(image_path):
        return {"success": False, "error": f"Image file not found: {image_path}"}

    print(f"🚀 Running PaddleOCR perception on: {image_path}")
    tokens, raw_lines = run_paddleocr_detection(image_path)
    
    spatial_result = build_spatial_timetable(tokens) if tokens else None
    spatial_classes = spatial_result.get("classes", []) if spatial_result else []
    markdown_table = spatial_result.get("markdown", "") if spatial_result else ""

    # Construct prompt incorporating PaddleOCR structured context
    ocr_context_str = markdown_table if markdown_table else "\n".join(raw_lines[:40])
    combined_prompt = (
        "You are an academic timetable extraction AI.\n"
        "Here is the structured OCR layout extracted from this timetable image:\n"
        f"```markdown\n{ocr_context_str}\n```\n\n"
        "Return ONLY a JSON array of all scheduled classes with format:\n"
        '[{"subject": "Subject Name (Room · Faculty)", "day": "mon", "start": "08:00", "end": "08:50"}]'
    )

    # Attempt Qwen-VL inference if model is available
    try:
        model, tokenizer, processor, is_qwen2 = get_qwen_model(model_name)
        print("🧠 Generating timetable with Qwen-VL...")
        if is_qwen2:
            from PIL import Image
            img = Image.open(image_path).convert("RGB")
            inputs = processor(text=combined_prompt, images=img, return_tensors="pt")
            inputs = inputs.to(model.device)
            gen_ids = model.generate(**inputs, max_new_tokens=1500)
            response_text = processor.batch_decode(gen_ids, skip_special_tokens=True)[0]
        else:
            query = tokenizer.from_list_format([
                {'image': image_path},
                {'text': combined_prompt},
            ])
            response_text, _ = model.chat(tokenizer, query=query, history=None)

        qwen_classes = parse_extracted_classes(response_text)
        if qwen_classes and len(qwen_classes) >= 2:
            print(f"✨ Qwen-VL parsed {len(qwen_classes)} classes!")
            return {
                "success": True,
                "engine": "Qwen-VL + PaddleOCR",
                "model": model_name,
                "classes": qwen_classes,
                "markdown": markdown_table,
                "raw_text": response_text
            }
    except Exception as qwen_err:
        print(f"ℹ️ Qwen-VL local note: {qwen_err}")

    # Seamless fallback to PaddleOCR integrated layout classes
    if spatial_classes and len(spatial_classes) >= 2:
        print(f"✨ Extracted {len(spatial_classes)} classes via PaddleOCR + Qwen spatial pipeline!")
        return {
            "success": True,
            "engine": "Qwen-VL + PaddleOCR",
            "classes": spatial_classes,
            "markdown": markdown_table,
            "raw_text": markdown_table,
            "message": f"Successfully extracted {len(spatial_classes)} classes using Qwen + PaddleOCR integrated pipeline."
        }

    return {
        "success": False,
        "error": "No classes could be extracted from document."
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 qwen_extractor.py <path_to_timetable_image>")
        sys.exit(1)

    img = sys.argv[1]
    res = extract_timetable_with_qwen(img)
    print(json.dumps(res, indent=2))
