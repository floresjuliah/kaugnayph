import cv2
import pytesseract
import os
from difflib import SequenceMatcher

# Change this path if Tesseract is installed somewhere else
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

# IMAGE QUALITY CHECKS

def is_blurry(image):
    """
    Returns True if the image is too blurry.
    """

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    variance = cv2.Laplacian(gray, cv2.CV_64F).var()

    return variance < 100


def is_too_dark(image):
    """
    Returns True if the image is too dark.
    """

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    brightness = gray.mean()

    return brightness < 50


# OCR

def preprocess_image(image):
    """
    Cleans the image before OCR.
    """

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    _, thresh = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    return thresh


def extract_text(image_path):
    """
    Reads text from the uploaded ID.
    """

    if not os.path.exists(image_path):
        return ""

    image = cv2.imread(image_path)

    if image is None:
        return ""

    cleaned = preprocess_image(image)

    text = pytesseract.image_to_string(cleaned)

    return text.lower()


# TEXT CLEANING

def normalize(text):
    """
    Makes text easier to compare.
    """

    if not text:
        return ""

    text = text.lower()

    text = text.replace("\n", " ")

    text = text.replace(",", " ")

    text = text.replace(".", " ")

    text = text.replace("-", " ")

    text = text.replace("/", " ")

    text = " ".join(text.split())

    return text

def is_similar(expected, actual, threshold=0.80):
    """
    Returns True if two strings are similar enough.
    """

    expected = normalize(expected)
    actual = normalize(actual)

    score = SequenceMatcher(
        None,
        expected,
        actual
    ).ratio()

    return score >= threshold

# MAIN VALIDATION

def verify_registration(image_path, firstname, lastname, address, id_name):

    if not os.path.exists(image_path):
        return {
            "matched": False,
            "reason": "Uploaded ID could not be found."
        }

    image = cv2.imread(image_path)

    if image is None:
        return {
            "matched": False,
            "reason": "Unable to read uploaded ID."
        }

    if is_blurry(image):
        return {
            "matched": False,
            "reason": "The uploaded ID is too blurry."
        }

    if is_too_dark(image):
        return {
            "matched": False,
            "reason": "The uploaded ID is too dark."
        }

    ocr_text = normalize(extract_text(image_path))

    print("=" * 60)
    print("OCR TEXT:")
    print(ocr_text)
    print("=" * 60)

    if len(ocr_text) < 10:
        return {
            "matched": False,
            "reason": "No readable text was detected on the uploaded ID."
        }

    # Verify ID Type

    id_keywords = {
        "Philippine National ID": [
            "philsys",
            "republic",
            "philippines"
        ],

        "Passport": [
            "passport",
            "republic of the philippines"
        ],

        "Driver's License": [
            "driver",
            "license",
            "land transportation office"
        ],

        "UMID": [
            "umid",
            "sss",
            "gsis"
        ],

        "Voter ID": [
            "comelec",
            "voter"
        ],

        "Senior Citizen ID": [
            "senior citizen"
        ],

        "PWD ID": [
            "pwd"
        ],

        "Student ID": [
            "student"
        ]
    }

    keywords = id_keywords.get(id_name, [])

    if keywords:

        found = False

        for keyword in keywords:

            if keyword.lower() in ocr_text:
                found = True
                break

        if not found:
            return {
                "matched": False,
                "reason": f"The uploaded image does not appear to be a valid {id_name}."
            }

    # Verify First Name

    if normalize(firstname) not in ocr_text:

        return {
            "matched": False,
            "reason": "First name was not found on the uploaded ID."
        }

    # Verify Last Name

    if normalize(lastname) not in ocr_text:

        return {
            "matched": False,
            "reason": "Last name was not found on the uploaded ID."
        }

    return {
        "matched": True,
        "reason": "Verification successful.",
        "ocr_text": ocr_text
    }
