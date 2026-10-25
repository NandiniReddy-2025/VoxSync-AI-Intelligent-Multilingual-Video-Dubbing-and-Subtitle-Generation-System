import os
import re
import time
import requests
import urllib.parse
from typing import List, Dict, Any, Optional
from config import OPENAI_API_KEY, GEMINI_API_KEY
from languages import (
    get_translation_code,
    normalize_language_code,
    get_language,
    LANGUAGE_REGISTRY
)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

_gemini_disabled = False
_openai_disabled = False


def translate_with_google_api(text: str, source_lang: str, target_lang: str, timeout: int = 6) -> Optional[str]:
    """Translate single string using Google web translate endpoint with canonical provider codes."""
    if not text or not text.strip():
        return ""
    
    sl = get_translation_code(source_lang, "google")
    tl = get_translation_code(target_lang, "google")
    
    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        "client": "dict-chrome-ex",
        "sl": sl,
        "tl": tl,
        "dt": "t",
        "q": text
    }
    
    try:
        resp = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            if data and isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                translated = "".join([part[0] for part in data[0] if part and part[0]]).strip()
                if translated:
                    return translated
    except Exception:
        pass

    return None


def translate_batch_google_api(texts: List[str], source_lang: str, target_lang: str, timeout: int = 12) -> Optional[List[str]]:
    """Translate multiple strings together using delimiter chunking."""
    if not texts:
        return []
    
    delimiter = "\n<<<SEG_BREAK>>>\n"
    combined = delimiter.join(texts)
    sl = get_translation_code(source_lang, "google")
    tl = get_translation_code(target_lang, "google")
    
    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        "client": "dict-chrome-ex",
        "sl": sl,
        "tl": tl,
        "dt": "t",
        "q": combined
    }
    
    try:
        resp = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            if data and isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                raw_out = "".join([part[0] for part in data[0] if part and part[0]])
                parts = [p.strip() for p in raw_out.split("<<<SEG_BREAK>>>")]
                if len(parts) == len(texts):
                    return parts
    except Exception:
        pass

    return None


def translate_with_mymemory_direct(text: str, source_lang: str, target_lang: str, timeout: int = 6) -> Optional[str]:
    """Translate using direct MyMemory GET request with RFC/ISO locale codes."""
    if not text or not text.strip():
        return ""
        
    src_code = get_translation_code(source_lang, "mymemory")
    tgt_code = get_translation_code(target_lang, "mymemory")

    url = "https://api.mymemory.translated.net/get"
    params = {
        "q": text,
        "langpair": f"{src_code}|{tgt_code}",
        "de": "support@voxsync.ai"
    }
    
    try:
        resp = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            res_data = data.get("responseData", {})
            trans_text = res_data.get("translatedText", "")
            if trans_text and "MYMEMORY WARNING" not in trans_text.upper():
                return trans_text.strip()
    except Exception:
        pass

    return None


def translate_with_deep_translator(text: str, source_lang: str, target_lang: str) -> Optional[str]:
    """Fallback using deep-translator GoogleTranslator or MyMemoryTranslator with locale codes."""
    sl = get_translation_code(source_lang, "google")
    tl = get_translation_code(target_lang, "google")
    try:
        from deep_translator import GoogleTranslator
        gt = GoogleTranslator(source=sl, target=tl)
        res = gt.translate(text)
        if res and res.strip():
            return res.strip()
    except Exception:
        pass

    try:
        from deep_translator import MyMemoryTranslator
        src_code = get_translation_code(source_lang, "mymemory")
        tgt_code = get_translation_code(target_lang, "mymemory")
        mt = MyMemoryTranslator(source=src_code, target=tgt_code)
        res = mt.translate(text)
        if res and res.strip() and "MYMEMORY WARNING" not in res.upper():
            return res.strip()
    except Exception:
        pass

    return None


def translate_with_openai(text: str, source_lang: str, target_lang: str) -> Optional[str]:
    global _openai_disabled
    if _openai_disabled or not OPENAI_API_KEY or not OPENAI_API_KEY.strip().startswith("sk-"):
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY.strip())
        src_info = get_language(source_lang)
        tgt_info = get_language(target_lang)
        src_name = src_info["name"] if src_info else source_lang
        tgt_name = tgt_info["name"] if tgt_info else target_lang

        system_prompt = (
            f"You are a professional multilingual translator. Translate speech transcript text from {src_name} to {tgt_name}.\n"
            "Guidelines:\n"
            "1. Preserve original meaning, tone, sentence context, proper names, and technical terminology.\n"
            "2. Keep the translation natural and concise for speech dubbing.\n"
            "3. Output ONLY the direct translated text without quotes or explanations."
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0.2,
            max_tokens=500
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"OpenAI translation failed: {e}")
        _openai_disabled = True
        return None


def translate_with_gemini(text: str, source_lang: str, target_lang: str) -> Optional[str]:
    global _gemini_disabled
    if _gemini_disabled or not GEMINI_API_KEY or not GEMINI_API_KEY.strip().startswith("AIza"):
        return None

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY.strip())
        model = genai.GenerativeModel("gemini-1.5-flash")

        src_info = get_language(source_lang)
        tgt_info = get_language(target_lang)
        src_name = src_info["name"] if src_info else source_lang
        tgt_name = tgt_info["name"] if tgt_info else target_lang

        prompt = (
            f"Translate the following speech transcript text from {src_name} to {tgt_name}.\n"
            "Maintain natural phrasing suitable for video voiceover and retain proper nouns.\n"
            "Return ONLY the direct translation:\n\n"
            f"Text: {text}"
        )
        response = model.generate_content(prompt)
        if response and response.text:
            return response.text.strip()
    except Exception as e:
        print(f"Gemini translation failed: {e}")
        _gemini_disabled = True
        return None


def translate_single_text(text: str, source_lang: str = "en", target_lang: str = "te", max_retries: int = 2) -> str:
    """
    Translate a single string using multi-tier fallback pipeline with bounded retries.
    Never returns original English text as a fake translation on failure.
    Raises ValueError if all providers fail.
    """
    if not text or not text.strip():
        return ""
    
    src_norm = normalize_language_code(source_lang)
    tgt_norm = normalize_language_code(target_lang)

    # If source and target languages are identical
    if src_norm == tgt_norm:
        return text

    for attempt in range(max_retries + 1):
        # Tier 1: Fast direct Google Translate API
        res = translate_with_google_api(text, src_norm, tgt_norm)
        if res and res.strip():
            return res.strip()

        # Tier 2: MyMemory direct API
        res = translate_with_mymemory_direct(text, src_norm, tgt_norm)
        if res and res.strip():
            return res.strip()

        # Tier 3: deep-translator (Google/MyMemory)
        res = translate_with_deep_translator(text, src_norm, tgt_norm)
        if res and res.strip():
            return res.strip()

        # Tier 4: OpenAI if configured and valid
        res = translate_with_openai(text, src_norm, tgt_norm)
        if res and res.strip():
            return res.strip()

        # Tier 5: Gemini if configured and valid
        res = translate_with_gemini(text, src_norm, tgt_norm)
        if res and res.strip():
            return res.strip()

        if attempt < max_retries:
            time.sleep(0.4 * (attempt + 1))

    # If all providers fail: do NOT return fake original English text
    lang_info = get_language(tgt_norm)
    lang_display = lang_info["name"] if lang_info else tgt_norm.upper()
    raise ValueError(
        f"Unable to translate text to {lang_display}. "
        "Translation service providers are currently unreachable or rate limited. "
        "Please check your internet connection or try again."
    )


def translate_batch_texts(
    texts: List[str],
    source_lang: str = "en",
    target_lang: str = "te",
    chunk_size: int = 15
) -> List[str]:
    """
    Translate a list of strings efficiently using batching with fallback to individual items.
    """
    if not texts:
        return []

    if source_lang == target_lang:
        return list(texts)

    results: List[str] = []

    for i in range(0, len(texts), chunk_size):
        chunk = texts[i:i + chunk_size]
        batch_res = translate_batch_google_api(chunk, source_lang, target_lang)
        if batch_res and len(batch_res) == len(chunk):
            results.extend(batch_res)
        else:
            # Fallback to translating individual items in the chunk
            for item in chunk:
                if not item or not item.strip():
                    results.append("")
                    continue
                try:
                    single_res = translate_single_text(item, source_lang, target_lang)
                    results.append(single_res)
                except Exception as e:
                    print(f"Failed to translate segment '{item[:30]}': {e}")
                    results.append("")

    return results


def translate_segments(segments: List[Dict[str, Any]], source_lang: str, target_lang: str) -> List[Dict[str, Any]]:
    """Translate each segment in the list and assign translated_text."""
    texts = [seg.get("original_text", "") for seg in segments]
    translations = translate_batch_texts(texts, source_lang, target_lang)
    for seg, trans in zip(segments, translations):
        seg["translated_text"] = trans
    return segments

