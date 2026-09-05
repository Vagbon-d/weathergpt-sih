"""
Bhashini API client for Indian Language Intelligence.
National Language Translation Mission (NLTM / ULCA / Dhruva).

Provides integration with Bhashini ULCA pipelines for:
- Language identification & translation
- Text-to-Speech (TTS)
- Speech-to-Text (ASR)

If credentials (BHASHINI_API_KEY, BHASHINI_USER_ID) are not configured,
it transparently falls back to local deterministic language processing and browser speech.
"""

import os
import logging
import httpx
from typing import Any

logger = logging.getLogger(__name__)

BHASHINI_API_KEY = os.getenv("BHASHINI_API_KEY", "").strip()
BHASHINI_USER_ID = os.getenv("BHASHINI_USER_ID", "").strip()
BHASHINI_PIPELINE_ID = os.getenv("BHASHINI_PIPELINE_ID", "").strip()
BHASHINI_DISCOVERY_URL = os.getenv(
    "BHASHINI_DISCOVERY_URL",
    "https://meity-auth.ulca.gov.in/ulca/apis/v0/model/getModelsPipeline",
).strip()
BHASHINI_INFERENCE_URL = os.getenv(
    "BHASHINI_INFERENCE_URL",
    "https://dhruva-api.bhashini.gov.in/services/inference/pipeline",
).strip()


class BhashiniService:
    """
    Client for Government of India's Bhashini AI language services.
    Implements ULCA pipeline discovery and Dhruva inference.
    """

    def __init__(self):
        self.api_key = BHASHINI_API_KEY
        self.user_id = BHASHINI_USER_ID
        self.pipeline_id = BHASHINI_PIPELINE_ID
        self.discovery_url = BHASHINI_DISCOVERY_URL
        self.inference_url = BHASHINI_INFERENCE_URL
        self._pipeline_cache: dict[str, dict[str, Any]] = {}
        self.configured = bool(self.api_key and self.user_id)
        if not self.configured:
            logger.info("Bhashini credentials (BHASHINI_API_KEY / BHASHINI_USER_ID) not set. Operating in local fallback mode.")

    def is_available(self) -> bool:
        """Check if Bhashini API credentials are configured."""
        return self.configured

    def _clean_lang_code(self, lang: str) -> str:
        """Normalize language codes (e.g. 'hi-Latn' -> 'hi', 'en-IN' -> 'en')."""
        if not lang:
            return "en"
        base = lang.split("-")[0].lower()
        # Supported Bhashini language codes: hi, mr, gu, bn, ta, te, kn, ml, pa, or, kok, en
        return base

    async def discover_pipeline_config(
        self,
        task_type: str,
        source_lang: str,
        target_lang: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Dynamically discover the appropriate Bhashini pipeline serviceId and callbackUrl.
        """
        if not self.is_available():
            return None

        cache_key = f"{task_type}:{source_lang}:{target_lang or ''}"
        if cache_key in self._pipeline_cache:
            return self._pipeline_cache[cache_key]

        task_config: dict[str, Any] = {
            "language": {
                "sourceLanguage": source_lang
            }
        }
        if target_lang:
            task_config["language"]["targetLanguage"] = target_lang

        payload: dict[str, Any] = {
            "pipelineTasks": [
                {
                    "taskType": task_type,
                    "config": task_config
                }
            ],
            "pipelineRequestConfig": {
                "pipelineId": self.pipeline_id or "64392f96daac500b55c543d7"
            }
        }

        headers = {
            "Content-Type": "application/json",
            "userID": self.user_id,
            "ulcaApiKey": self.api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.post(self.discovery_url, json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    task_res = data.get("pipelineResponseConfig", [])
                    service_id = None
                    for t in task_res:
                        if t.get("taskType") == task_type:
                            configs = t.get("config", [])
                            if configs and "serviceId" in configs[0]:
                                service_id = configs[0]["serviceId"]
                                break

                    endpoint_info = data.get("pipelineInferenceAPIEndPoint", {})
                    callback_url = endpoint_info.get("callbackUrl", self.inference_url)
                    inf_key_obj = endpoint_info.get("inferenceApiKey", {})

                    discovered = {
                        "serviceId": service_id,
                        "callbackUrl": callback_url,
                        "inferenceKeyName": inf_key_obj.get("name"),
                        "inferenceKeyValue": inf_key_obj.get("value"),
                    }
                    self._pipeline_cache[cache_key] = discovered
                    return discovered
                else:
                    logger.warning(f"Bhashini pipeline discovery returned HTTP {res.status_code}")
        except Exception as exc:
            logger.warning(f"Bhashini pipeline discovery failed: {exc}")

        return None

    async def translate_text(
        self,
        text: str,
        source_lang: str,
        target_lang: str = "en",
    ) -> str | None:
        """
        Translate text between Indian languages and English using Bhashini pipeline.
        Returns translated string or None if unconfigured/failed.
        """
        if not self.is_available() or not text or not text.strip():
            return None

        src = self._clean_lang_code(source_lang)
        tgt = self._clean_lang_code(target_lang)

        if src == tgt:
            return text

        disc = await self.discover_pipeline_config("translation", src, tgt)
        service_id = disc.get("serviceId") if disc else None
        target_url = (disc.get("callbackUrl") if disc else None) or self.inference_url

        config_obj: dict[str, Any] = {
            "language": {
                "sourceLanguage": src,
                "targetLanguage": tgt,
            }
        }
        if service_id:
            config_obj["serviceId"] = service_id

        payload = {
            "pipelineTasks": [
                {
                    "taskType": "translation",
                    "config": config_obj,
                }
            ],
            "inputData": {
                "input": [{"source": text}]
            }
        }

        headers = {
            "Content-Type": "application/json",
            "userID": self.user_id,
            "ulcaApiKey": self.api_key,
        }
        if disc and disc.get("inferenceKeyName") and disc.get("inferenceKeyValue"):
            headers[disc["inferenceKeyName"]] = disc["inferenceKeyValue"]

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.post(target_url, json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    tasks = data.get("pipelineResponse", [])
                    for t in tasks:
                        if t.get("taskType") == "translation":
                            output = t.get("output", [])
                            if output and "target" in output[0]:
                                return output[0]["target"]
                else:
                    logger.warning(f"Bhashini translation response: {res.status_code}")
        except Exception as exc:
            logger.warning(f"Bhashini translation failed: {exc}")

        return None

    async def generate_tts(
        self,
        text: str,
        language: str = "en",
        gender: str = "female",
    ) -> dict[str, Any] | None:
        """
        Generate Text-to-Speech audio using Bhashini ULCA TTS pipeline.
        Returns dict with base64 audio content or None if unconfigured/failed.
        """
        lang = self._clean_lang_code(language)

        logger.info("=" * 45)
        logger.info("TTS requested: language=%s, text_length=%d", lang, len(text))

        if not self.is_available():
            logger.info("Selected TTS provider: Local/Browser Fallback (Bhashini unconfigured)")
            logger.info("=" * 45)
            return None

        logger.info("Selected TTS provider: BHASHINI")
        logger.info("Selected language: %s", lang)

        # 1. Pipeline discovery for exact TTS serviceId
        disc = await self.discover_pipeline_config("tts", lang)
        service_id = disc.get("serviceId") if disc else None
        target_url = (disc.get("callbackUrl") if disc else None) or self.inference_url
        logger.info("Selected service/model: %s", service_id or "default-tts-pipeline")

        config_obj: dict[str, Any] = {
            "language": {"sourceLanguage": lang},
            "gender": gender,
            "samplingRate": 8000,
        }
        if service_id:
            config_obj["serviceId"] = service_id

        payload = {
            "pipelineTasks": [
                {
                    "taskType": "tts",
                    "config": config_obj,
                }
            ],
            "inputData": {
                "input": [{"source": text}]
            }
        }

        headers = {
            "Content-Type": "application/json",
            "userID": self.user_id,
            "ulcaApiKey": self.api_key,
        }
        if disc and disc.get("inferenceKeyName") and disc.get("inferenceKeyValue"):
            headers[disc["inferenceKeyName"]] = disc["inferenceKeyValue"]

        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                res = await client.post(target_url, json=payload, headers=headers)
                logger.info("Response status: %s", res.status_code)
                if res.status_code == 200:
                    data = res.json()
                    tasks = data.get("pipelineResponse", [])
                    for t in tasks:
                        if t.get("taskType") == "tts":
                            audios = t.get("audio", [])
                            if audios and "audioContent" in audios[0]:
                                logger.info("TTS Audio synthesized successfully via Bhashini (%d chars base64)", len(audios[0]["audioContent"]))
                                logger.info("=" * 45)
                                return {
                                    "audioContent": audios[0]["audioContent"],
                                    "audioFormat": "wav",
                                    "language": lang,
                                    "serviceId": service_id,
                                    "source": "bhashini",
                                }
                else:
                    logger.warning(f"Bhashini TTS failed with HTTP status: {res.status_code} - {res.text[:200]}")
        except Exception as exc:
            logger.warning(f"Bhashini TTS network error: {exc}")

        logger.info("=" * 45)
        return None

    async def recognize_speech(
        self,
        audio_base64: str,
        language: str = "hi",
    ) -> str | None:
        """
        Transcribe speech using Bhashini ASR pipeline.
        """
        if not self.is_available() or not audio_base64:
            return None

        lang = self._clean_lang_code(language)
        payload = {
            "pipelineTasks": [
                {
                    "taskType": "asr",
                    "config": {
                        "language": {"sourceLanguage": lang},
                    },
                }
            ],
            "inputData": {
                "audio": [{"audioContent": audio_base64}]
            }
        }

        headers = {
            "Content-Type": "application/json",
            "userID": self.user_id,
            "ulcaApiKey": self.api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                res = await client.post(
                    self.inference_url,
                    json=payload,
                    headers=headers,
                )
                if res.status_code == 200:
                    data = res.json()
                    tasks = data.get("pipelineResponse", [])
                    for t in tasks:
                        if t.get("taskType") == "asr":
                            output = t.get("output", [])
                            if output and "source" in output[0]:
                                return output[0]["source"]
        except Exception as exc:
            logger.warning(f"Bhashini ASR failed: {exc}")

        return None


# Global singleton instance
bhashini = BhashiniService()
