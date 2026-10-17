#!/usr/bin/env python3
"""
Qwen-VL Timetable Extraction Pipeline
Uses Alibaba's Qwen-VL Vision-Language Model for zero-shot timetable understanding and JSON extraction.
"""

import os
import sys
import json
import re

# Model configuration
# Defaults to Qwen/Qwen-VL-Chat or Qwen/Qwen2-VL-2B-Instruct (which runs natively on Apple Silicon MPS)
MODEL_NAME = os.environ.get("QWEN_MODEL", "Qwen/Qwen-VL-Chat")

_model = None
_tokenizer = None
_processor = None
_is_qwen2 = False

TIMETABLE_PROMPT = (
    "You are an expert academic document understanding AI.\n"
    "Carefully inspect this timetable image and extract all scheduled classes, lectures, labs, and tutorials.\n"
    "For each class, identify:\n"
    "- subject: Complete subject name, venue/room, and faculty name if visible (e.g. 'Engineering Mathematics-I (NYB-301 · Dr. Monika Jain)')\n"
    "- day: 3-letter lowercase day: 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'\n"
    "- start: Start time in 24-hour format 'HH:MM' (e.g. '08:00', '09:40', '10:30')\n"
    "- end: End time in 24-hour format 'HH:MM' (e.g. '08:50', '10:30', '12:05')\n\n"
    "Note on labs: If a lab spans 2 or 3 consecutive periods, combine it into one block with the full start and end time.\n"
    "Ignore lunch breaks, recess, and free periods.\n\n"
    "Return ONLY a valid JSON array like this:\n"
    "[\n"
    '  {"subject": "Engineering Chemistry (NYB-102 · Dr. Vishnu)", "day": "mon", "start": "08:00", "end": "08:50"},\n'
    '  {"subject": "Engineering Mathematics-I (NYB-101)", "day": "mon", "start": "09:40", "end": "10:30"}\n'
    "]"
)

def hhmm_to_minutes(time_str):
    """Converts '08:50' or '8:50 AM' to minutes from midnight."""
    if isinstance(time_str, (int, float)):
        return int(time_str)
    if not time_str or not isinstance(time_str, str):
        return 480
    time_str = time_str.strip().upper()
    is_pm = "PM" in time_str and not time_str.startswith("12")
    cleaned = re.sub(r"[^\d:]", "", time_str)
    parts = cleaned.split(":")
    if len(parts) >= 2:
        try:
            h = int(parts[0])
            m = int(parts[1])
            if is_pm and h < 12:
                h += 12
            elif h < 7:  # Assume classes before 7 are afternoon PM (e.g. 1:00 PM -> 13:00)
                h += 12
            return h * 60 + m
        except ValueError:
            pass
    return 480

def get_qwen_model(model_name=MODEL_NAME):
    global _model, _tokenizer, _processor, _is_qwen2
    if _model is not None:
        return _model, _tokenizer, _processor, _is_qwen2

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError:
        raise ImportError(
            "PyTorch and Transformers are required for Qwen-VL.\n"
            "Install them with:\n"
            "  pip install torch torchvision transformers accelerate\n"
        )

    print(f"📦 Loading Qwen-VL model ({model_name})...")
    
    # Check if using Qwen2-VL or original Qwen-VL
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
        # User specified: AutoModelForCausalLM.from_pretrained("Qwen/Qwen-VL", trust_remote_code=True, device_map="auto")
        _is_qwen2 = False
        _tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        device_map = "auto" if torch.cuda.is_available() else None
        
        _model = AutoModelForCausalLM.from_pretrained(
            model_name,
            trust_remote_code=True,
            device_map=device_map
        ).eval()
        _processor = None

    print(f"✨ Qwen-VL model loaded successfully!")
    return _model, _tokenizer, _processor, _is_qwen2

def parse_extracted_classes(response_text):
    """Parses JSON timetable classes from model output string."""
    classes = []
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response_text)
    raw_json = json_match.group(1) if json_match else response_text

    # Extract JSON array
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
                start_min = hhmm_to_minutes(item.get("start", "08:00"))
                end_min = hhmm_to_minutes(item.get("end", "08:50"))
                if end_min <= start_min:
                    end_min = start_min + 50
                if subj:
                    classes.append({
                        "subject": str(subj).strip(),
                        "day": day,
                        "start": start_min,
                        "end": end_min
                    })
    except Exception as e:
        print(f"Warning: JSON parsing failed on model response: {e}")
        # Regex line-by-line fallback
        for m in re.finditer(r'\{[^{}]*"subject"\s*:\s*"([^"]+)"[^{}]*"day"\s*:\s*"([^"]+)"[^{}]*"start"\s*:\s*"([^"]+)"[^{}]*"end"\s*:\s*"([^"]+)"[^{}]*\}', response_text):
            subj, day, s_time, e_time = m.groups()
            s_min = hhmm_to_minutes(s_time)
            e_min = hhmm_to_minutes(e_time)
            classes.append({
                "subject": subj.strip(),
                "day": day.lower()[:3],
                "start": s_min,
                "end": max(e_min, s_min + 50)
            })

    return classes

def extract_timetable_with_qwen(image_path, model_name=MODEL_NAME):
    """
    Extracts timetable classes from an image using Qwen-VL.
    Returns dict with success status, extracted classes, and raw response.
    """
    if not os.path.isfile(image_path):
        return {"success": False, "error": f"Image file not found: {image_path}"}

    try:
        model, tokenizer, processor, is_qwen2 = get_qwen_model(model_name)
    except Exception as e:
        return {"success": False, "error": f"Failed to initialize Qwen-VL: {e}"}

    print(f"🔍 Analyzing timetable with Qwen-VL: {image_path}")

    try:
        if is_qwen2:
            from qwen_vl_utils import process_vision_info
            import torch
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image_path},
                        {"type": "text", "text": TIMETABLE_PROMPT}
                    ]
                }
            ]
            text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            image_inputs, video_inputs = process_vision_info(messages)
            inputs = processor(
                text=[text],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt"
            )
            inputs = inputs.to(model.device)
            generated_ids = model.generate(**inputs, max_new_tokens=1500)
            generated_ids_trimmed = [
                out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]
            response_text = processor.batch_decode(
                generated_ids_trimmed,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False
            )[0]
        else:
            # Qwen-VL / Qwen-VL-Chat format
            query = tokenizer.from_list_format([
                {'image': image_path},
                {'text': TIMETABLE_PROMPT},
            ])
            response_text, _ = model.chat(tokenizer, query=query, history=None)

        classes = parse_extracted_classes(response_text)
        return {
            "success": True,
            "engine": "Qwen-VL",
            "model": model_name,
            "classes": classes,
            "raw_text": response_text
        }
    except Exception as e:
        return {"success": False, "error": f"Qwen-VL inference failed: {e}"}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 qwen_extractor.py <path_to_timetable_image>")
        sys.exit(1)

    img = sys.argv[1]
    res = extract_timetable_with_qwen(img)
    print(json.dumps(res, indent=2))
