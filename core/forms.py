from django import forms
from captcha.fields import CaptchaField


class CaptchaOnlyForm(forms.Form):
    captcha = CaptchaField(
        label="Security Check",
        error_messages={
            "invalid": "Invalid CAPTCHA. Please try again."
        }
    )