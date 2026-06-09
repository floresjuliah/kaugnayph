# core/moderation.py
import base64
import openai
from django.conf import settings

openai.api_key = settings.OPENAI_API_KEY


def moderate_text(text: str) -> dict:
    """
    Moderate a text string.
    Returns: { "flagged": bool, "reason": str | None }
    """
    if not text or not text.strip():
        return {"flagged": False, "reason": None}

    try:
        response = openai.moderations.create(
            model="omni-moderation-latest",
            input=text.strip()
        )
        result = response.results[0]

        if result.flagged:
            cats = result.categories
            triggered = []
            checks = {
                "harassment":           getattr(cats, "harassment",           False),
                "harassment/threatening": getattr(cats, "harassment_threatening", False),
                "hate":                 getattr(cats, "hate",                 False),
                "hate/threatening":     getattr(cats, "hate_threatening",     False),
                "self-harm":            getattr(cats, "self_harm",            False),
                "self-harm/intent":     getattr(cats, "self_harm_intent",     False),
                "sexual":               getattr(cats, "sexual",               False),
                "violence":             getattr(cats, "violence",             False),
                "violence/graphic":     getattr(cats, "violence_graphic",     False),
            }
            triggered = [k for k, v in checks.items() if v]
            return {
                "flagged": True,
                "reason": ", ".join(triggered) if triggered else "policy violation"
            }

        return {"flagged": False, "reason": None}

    except Exception as e:
        # If OpenAI is down, fail OPEN (don't block the user)
        print(f"[MODERATION ERROR - text] {e}")
        return {"flagged": False, "reason": None}


def moderate_image(image_file) -> dict:
    """
    Moderate an uploaded image file (Django InMemoryUploadedFile).
    Returns: { "flagged": bool, "reason": str | None }
    """
    try:
        image_data = image_file.read()
        image_file.seek(0)  # Reset so it can still be saved afterward
        b64 = base64.standard_b64encode(image_data).decode("utf-8")
        mime = image_file.content_type  # e.g. "image/jpeg"

        response = openai.moderations.create(
            model="omni-moderation-latest",
            input=[{
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime};base64,{b64}"
                }
            }]
        )
        result = response.results[0]

        if result.flagged:
            cats = result.categories
            checks = {
                "harassment":           getattr(cats, "harassment",           False),
                "harassment/threatening": getattr(cats, "harassment_threatening", False),
                "hate":                 getattr(cats, "hate",                 False),
                "hate/threatening":     getattr(cats, "hate_threatening",     False),
                "self-harm":            getattr(cats, "self_harm",            False),
                "sexual":               getattr(cats, "sexual",               False),
                "violence":             getattr(cats, "violence",             False),
                "violence/graphic":     getattr(cats, "violence_graphic",     False),
            }
            triggered = [k for k, v in checks.items() if v]
            return {
                "flagged": True,
                "reason": ", ".join(triggered) if triggered else "policy violation"
            }

        return {"flagged": False, "reason": None}

    except Exception as e:
        print(f"[MODERATION ERROR - image] {e}")
        return {"flagged": False, "reason": None}