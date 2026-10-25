"""
Central Language Registry and Configuration for VoxSync AI.
Defines canonical language metadata, translation provider codes, TTS locales and voices,
and support/verification flags for all supported languages.
"""

from typing import Dict, Any, List, Optional, Tuple

LANGUAGE_REGISTRY: Dict[str, Dict[str, Any]] = {
    "en": {
        "code": "en",
        "name": "English",
        "native": "English",
        "translation_codes": {
            "google": "en",
            "mymemory": "en-US",
            "whisper": "en",
            "openai": "English",
            "gemini": "English",
        },
        "tts_locale": "en-US",
        "tts_provider": "edge-tts",
        "default_voice": "en-US-JennyNeural",
        "voices": [
            {"id": "en-US-JennyNeural", "name": "Jenny (Female, Friendly)", "gender": "Female", "locale": "en-US"},
            {"id": "en-US-GuyNeural", "name": "Guy (Male, Professional)", "gender": "Male", "locale": "en-US"},
            {"id": "en-IN-NeerjaNeural", "name": "Neerja (Female, Indian English)", "gender": "Female", "locale": "en-IN"},
            {"id": "en-IN-PrabhatNeural", "name": "Prabhat (Male, Indian English)", "gender": "Male", "locale": "en-IN"},
        ],
        "translation_supported": True,
        "tts_supported": True,
        "dubbing_supported": True,
        "verified": True,
    },
    "te": {
        "code": "te",
        "name": "Telugu",
        "native": "తెలుగు",
        "translation_codes": {
            "google": "te",
            "mymemory": "te-IN",
            "whisper": "te",
            "openai": "Telugu",
            "gemini": "Telugu",
        },
        "tts_locale": "te-IN",
        "tts_provider": "edge-tts",
        "default_voice": "te-IN-ShrutiNeural",
        "voices": [
            {"id": "te-IN-ShrutiNeural", "name": "Shruti (Female, Warm)", "gender": "Female", "locale": "te-IN"},
            {"id": "te-IN-MohanNeural", "name": "Mohan (Male, Clear)", "gender": "Male", "locale": "te-IN"},
        ],
        "translation_supported": True,
        "tts_supported": True,
        "dubbing_supported": True,
        "verified": True,
    },
    "hi": {
        "code": "hi",
        "name": "Hindi",
        "native": "हिन्दी",
        "translation_codes": {
            "google": "hi",
            "mymemory": "hi-IN",
            "whisper": "hi",
            "openai": "Hindi",
            "gemini": "Hindi",
        },
        "tts_locale": "hi-IN",
        "tts_provider": "edge-tts",
        "default_voice": "hi-IN-SwaraNeural",
        "voices": [
            {"id": "hi-IN-SwaraNeural", "name": "Swara (Female, Expressive)", "gender": "Female", "locale": "hi-IN"},
            {"id": "hi-IN-MadhurNeural", "name": "Madhur (Male, Confident)", "gender": "Male", "locale": "hi-IN"},
        ],
        "translation_supported": True,
        "tts_supported": True,
        "dubbing_supported": True,
        "verified": True,
    },
    "ta": {
        "code": "ta",
        "name": "Tamil",
        "native": "தமிழ்",
        "translation_codes": {
            "google": "ta",
            "mymemory": "ta-IN",
            "whisper": "ta",
            "openai": "Tamil",
            "gemini": "Tamil",
        },
        "tts_locale": "ta-IN",
        "tts_provider": "edge-tts",
        "default_voice": "ta-IN-PallaviNeural",
        "voices": [
            {"id": "ta-IN-PallaviNeural", "name": "Pallavi (Female, Fluent)", "gender": "Female", "locale": "ta-IN"},
            {"id": "ta-IN-ValluvarNeural", "name": "Valluvar (Male, Deep)", "gender": "Male", "locale": "ta-IN"},
        ],
        "translation_supported": True,
        "tts_supported": True,
        "dubbing_supported": True,
        "verified": True,
    },
    "kn": {
        "code": "kn",
        "name": "Kannada",
        "native": "ಕನ್ನಡ",
        "translation_codes": {
            "google": "kn",
            "mymemory": "kn-IN",
            "whisper": "kn",
            "openai": "Kannada",
            "gemini": "Kannada",
        },
        "tts_locale": "kn-IN",
        "tts_provider": "edge-tts",
        "default_voice": "kn-IN-SapnaNeural",
        "voices": [
            {"id": "kn-IN-SapnaNeural", "name": "Sapna (Female, Natural)", "gender": "Female", "locale": "kn-IN"},
            {"id": "kn-IN-GaganNeural", "name": "Gagan (Male, Authoritative)", "gender": "Male", "locale": "kn-IN"},
        ],
        "translation_supported": True,
        "tts_supported": True,
        "dubbing_supported": True,
        "verified": True,
    },
    "ml": {
        "code": "ml",
        "name": "Malayalam",
        "native": "മലയാളം",
        "translation_codes": {
            "google": "ml",
            "mymemory": "ml-IN",
            "whisper": "ml",
            "openai": "Malayalam",
            "gemini": "Malayalam",
        },
        "tts_locale": "ml-IN",
        "tts_provider": "edge-tts",
        "default_voice": "ml-IN-SobhanaNeural",
        "voices": [
            {"id": "ml-IN-SobhanaNeural", "name": "Sobhana (Female, Gentle)", "gender": "Female", "locale": "ml-IN"},
            {"id": "ml-IN-MidhunNeural", "name": "Midhun (Male, Narrative)", "gender": "Male", "locale": "ml-IN"},
        ],
        "translation_supported": True,
        "tts_supported": True,
        "dubbing_supported": True,
        "verified": True,
    },
    "es": {
        "code": "es",
        "name": "Spanish",
        "native": "Español",
        "translation_codes": {
            "google": "es",
            "mymemory": "es-ES",
            "whisper": "es",
            "openai": "Spanish",
            "gemini": "Spanish",
        },
        "tts_locale": "es-ES",
        "tts_provider": "edge-tts",
        "default_voice": "es-ES-ElviraNeural",
        "voices": [
            {"id": "es-ES-ElviraNeural", "name": "Elvira (Female, European)", "gender": "Female", "locale": "es-ES"},
            {"id": "es-ES-AlvaroNeural", "name": "Alvaro (Male, European)", "gender": "Male", "locale": "es-ES"},
        ],
        "translation_supported": True,
        "tts_supported": True,
        "dubbing_supported": True,
        "verified": True,
    },
    "fr": {
        "code": "fr",
        "name": "French",
        "native": "Français",
        "translation_codes": {
            "google": "fr",
            "mymemory": "fr-FR",
            "whisper": "fr",
            "openai": "French",
            "gemini": "French",
        },
        "tts_locale": "fr-FR",
        "tts_provider": "edge-tts",
        "default_voice": "fr-FR-DeniseNeural",
        "voices": [
            {"id": "fr-FR-DeniseNeural", "name": "Denise (Female, Parisian)", "gender": "Female", "locale": "fr-FR"},
            {"id": "fr-FR-HenriNeural", "name": "Henri (Male, Parisian)", "gender": "Male", "locale": "fr-FR"},
        ],
        "translation_supported": True,
        "tts_supported": True,
        "dubbing_supported": True,
        "verified": True,
    },
    "de": {
        "code": "de",
        "name": "German",
        "native": "Deutsch",
        "translation_codes": {
            "google": "de",
            "mymemory": "de-DE",
            "whisper": "de",
            "openai": "German",
            "gemini": "German",
        },
        "tts_locale": "de-DE",
        "tts_provider": "edge-tts",
        "default_voice": "de-DE-KatjaNeural",
        "voices": [
            {"id": "de-DE-KatjaNeural", "name": "Katja (Female, Standard)", "gender": "Female", "locale": "de-DE"},
            {"id": "de-DE-ConradNeural", "name": "Conrad (Male, Standard)", "gender": "Male", "locale": "de-DE"},
        ],
        "translation_supported": True,
        "tts_supported": True,
        "dubbing_supported": True,
        "verified": True,
    },
}


def normalize_language_code(code: Optional[str]) -> str:
    """Normalize input language code (e.g. 'te-IN' -> 'te', 'en-US' -> 'en')."""
    if not code:
        return "en"
    clean = code.strip().lower()
    if "-" in clean:
        clean = clean.split("-")[0]
    return clean if clean in LANGUAGE_REGISTRY else "en"


def get_language(code: Optional[str]) -> Optional[Dict[str, Any]]:
    """Get full language configuration by canonical code or locale."""
    norm = normalize_language_code(code)
    return LANGUAGE_REGISTRY.get(norm)


def get_supported_languages() -> Dict[str, Dict[str, Any]]:
    """
    Get all languages where both translation and TTS are supported and configured.
    Ensures backwards compatibility with frontend by providing name, native, tts_voices.
    """
    supported = {}
    for code, info in LANGUAGE_REGISTRY.items():
        if info.get("dubbing_supported", False):
            supported[code] = {
                "code": code,
                "name": info["name"],
                "native": info["native"],
                "tts_voices": [v["id"] for v in info["voices"]],
                "voices": info["voices"],
                "default_voice": info["default_voice"],
                "tts_locale": info["tts_locale"],
                "tts_provider": info["tts_provider"],
                "translation_codes": info["translation_codes"],
                "translation_supported": info["translation_supported"],
                "tts_supported": info["tts_supported"],
                "dubbing_supported": info["dubbing_supported"],
                "verified": info.get("verified", True)
            }
    return supported


def get_translation_code(lang_code: str, provider: str = "google") -> str:
    """Get provider-specific language code for a canonical language."""
    info = get_language(lang_code)
    if not info:
        return lang_code
    t_codes = info.get("translation_codes", {})
    return t_codes.get(provider, info.get("code", lang_code))


def get_tts_locale(lang_code: str) -> str:
    """Get TTS locale code (e.g. 'te-IN', 'hi-IN', 'en-US')."""
    info = get_language(lang_code)
    if not info:
        return "en-US"
    return info.get("tts_locale", "en-US")


def get_available_voices(lang_code: Optional[str] = None) -> List[Dict[str, str]]:
    """Return available TTS voices for a language or all languages."""
    if lang_code:
        info = get_language(lang_code)
        if info:
            return info.get("voices", [])
        return []
    
    all_voices = []
    for info in LANGUAGE_REGISTRY.values():
        if info.get("dubbing_supported", False):
            all_voices.extend(info.get("voices", []))
    return all_voices


def get_default_voice_for_language(lang_code: str) -> str:
    """Get default voice for a supported language. Never silently falls back to English for non-English languages."""
    norm = normalize_language_code(lang_code)
    info = LANGUAGE_REGISTRY.get(norm)
    if not info or not info.get("voices"):
        raise ValueError(
            f"Language '{lang_code}' is not supported by the configured TTS provider. "
            f"Supported languages: {', '.join(LANGUAGE_REGISTRY.keys())}"
        )
    return info.get("default_voice", info["voices"][0]["id"])


def validate_voice_for_language(lang_code: str, voice_name: Optional[str]) -> Tuple[bool, str, str]:
    """
    Validate that voice_name matches the requested target language.
    Returns (is_valid, resolved_voice_name, message).
    """
    norm = normalize_language_code(lang_code)
    info = LANGUAGE_REGISTRY.get(norm)
    if not info:
        raise ValueError(f"Language '{lang_code}' is not supported for dubbing.")
    
    valid_ids = [v["id"] for v in info.get("voices", [])]
    if not valid_ids:
        raise ValueError(f"No speech synthesis voices configured for language '{info['name']}' ({norm}).")

    if not voice_name or voice_name.strip() not in valid_ids:
        default_v = info["default_voice"]
        msg = f"Voice '{voice_name}' is not valid for {info['name']}. Resolved to default: '{default_v}'"
        return False, default_v, msg

    return True, voice_name.strip(), f"Voice '{voice_name}' is valid for {info['name']}."


def is_language_supported(lang_code: str) -> bool:
    """Check if both translation and TTS are supported and configured."""
    norm = normalize_language_code(lang_code)
    info = LANGUAGE_REGISTRY.get(norm)
    if not info:
        return False
    return bool(info.get("dubbing_supported") and info.get("translation_supported") and info.get("tts_supported"))
