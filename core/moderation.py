import base64
import logging
import re

from openai import OpenAI
from django.conf import settings


# LOGGER

logger = logging.getLogger(__name__)


# OPENAI CLIENT

client = OpenAI(
    api_key=settings.OPENAI_API_KEY
)


# LOCAL FILIPINO PROFANITY FILTER

BAD_WORDS = [
    # Filipino
    "putangina", "putang ina", "puta",
    "gago", "bobo", "ulol", "tanga",
    "bwisit", "tangina", "pakyu",
    "tarantado", "hinayupak", "leche",
    "hayop", "buwisit", "lintik",

    # English
    "fuck", "shit", "bitch", "asshole",
    "bastard", "cunt", "damn", "ass",
    "dick", "piss", "crap",
]


def contains_bad_words(text: str) -> bool:

    text = text.lower()
    for word in BAD_WORDS:
        # Use word boundaries to avoid false positives
        pattern = r'\b' + re.escape(word) + r'\b'
        if re.search(pattern, text):
            return True
    return False
    

# ALLOWED IMAGE TYPES

ALLOWED_IMAGE_TYPES = [
    "image/jpeg",
    "image/png",
]


# TEXT MODERATION

def moderate_text(text: str) -> dict:
    """
    Moderate text content.

    Returns:
    {
        "flagged": bool,
        "reason": str | None
    }
    """

    if not text or not text.strip():
        return {
            "flagged": False,
            "reason": None
        }

    text = text.strip()

    try:

        #LOCAL PROFANITY CHECK

        if contains_bad_words(text):

            return {
                "flagged": True,
                "reason": "Filipino profanity detected"
            }

        # OPENAI MODERATION
        response = client.moderations.create(
            model="omni-moderation-latest",
            input=text
        )

        result = response.results[0]

        if result.flagged:

            categories = result.categories

            checks = {
                "harassment":
                    getattr(categories, "harassment", False),

                "harassment/threatening":
                    getattr(categories, "harassment_threatening", False),

                "hate":
                    getattr(categories, "hate", False),

                "hate/threatening":
                    getattr(categories, "hate_threatening", False),

                "self-harm":
                    getattr(categories, "self_harm", False),

                "self-harm/intent":
                    getattr(categories, "self_harm_intent", False),

                "sexual":
                    getattr(categories, "sexual", False),

                "violence":
                    getattr(categories, "violence", False),

                "violence/graphic":
                    getattr(categories, "violence_graphic", False),
            }

            triggered = [
                key for key, value in checks.items()
                if value
            ]

            return {
                "flagged": True,
                "reason":
                    ", ".join(triggered)
                    if triggered
                    else "policy violation"
            }

        return {
            "flagged": False,
            "reason": None
        }

    except Exception as e:

        logger.error(f"[TEXT MODERATION ERROR] {e}")

        # FAIL OPEN
        # Allow the user if moderation fails

        return {
            "flagged": False,
            "reason": None
        }


# IMAGE MODERATION
def moderate_image(image_file) -> dict:
    """
    Moderate uploaded image files.

    Returns:
    {
        "flagged": bool,
        "reason": str | None
    }
    """

    try:

        # VALIDATE IMAGE TYPE
        if image_file.content_type not in ALLOWED_IMAGE_TYPES:

            return {
                "flagged": True,
                "reason": "Unsupported image type"
            }

        # READ IMAGE
        image_data = image_file.read()

        # IMPORTANT:
        # Reset pointer so Django can still save it later

        image_file.seek(0)

        # CONVERT TO BASE64
        b64 = base64.b64encode(image_data).decode("utf-8")

        # OPENAI IMAGE MODERATION
        response = client.moderations.create(
            model="omni-moderation-latest",
            input=[
                {
                    "type": "image_url",
                    "image_url": {
                        "url":
                            f"data:{image_file.content_type};base64,{b64}"
                    }
                }
            ]
        )

        result = response.results[0]

        if result.flagged:

            categories = result.categories

            checks = {
                "sexual":
                    getattr(categories, "sexual", False),

                "violence":
                    getattr(categories, "violence", False),

                "violence/graphic":
                    getattr(categories, "violence_graphic", False),

                "hate":
                    getattr(categories, "hate", False),
            }

            triggered = [
                key for key, value in checks.items()
                if value
            ]

            return {
                "flagged": True,
                "reason":
                    ", ".join(triggered)
                    if triggered
                    else "inappropriate image detected"
            }

        return {
            "flagged": False,
            "reason": None
        }

    except Exception as e:

        logger.error(f"[IMAGE MODERATION ERROR] {e}")

        # FAIL OPEN
        # Allow upload if moderation API fails

        return {
            "flagged": False,
            "reason": None
        }