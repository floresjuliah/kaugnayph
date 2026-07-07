from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
import requests
import time

from core.models import SMSOutbox


class Command(BaseCommand):
    help = "Process pending SMS messages from SMSOutbox."

    def handle(self, *args, **options):
        self.stdout.write("SMS queue worker started.")

        while True:
            stuck_cutoff = timezone.now() - timezone.timedelta(minutes=5)

            recovered_count = SMSOutbox.objects.filter(
                status="processing",
                sent_at__isnull=True,
                created_at__lt=stuck_cutoff
            ).update(status="pending")

            if recovered_count:
                self.stdout.write(f"Recovered {recovered_count} stuck processing SMS messages.")

            pending_sms = SMSOutbox.objects.filter(status="pending").order_by("created_at")[:20]

            if not pending_sms:
                time.sleep(2)
                continue

            for sms in pending_sms:
                sms.status = "processing"
                sms.save(update_fields=["status"])

                success = False
                retry_later = False
                gateway_response = ""
                error_message = ""

                try:
                    r = requests.get(settings.SMS_URL, params={
                        "USERNAME": settings.SMS_USERNAME,
                        "PASSWORD": settings.SMS_PASSWORD,
                        "smsnum": sms.recipient_number,
                        "Memo": sms.message,
                        "method": "2",
                        "smsprovider": settings.SMS_PROVIDER,
                    }, timeout=30)

                    gateway_response = r.text
                    success = r.status_code == 200 and "Failure:1" not in gateway_response

                    if not success:
                        error_message = f"HTTP {r.status_code}: {gateway_response[:200]}"

                        if r.status_code != 200:
                            retry_later = True

                except requests.Timeout:
                    error_message = "Request timed out"
                    retry_later = True

                except requests.RequestException as e:
                    error_message = str(e)
                    retry_later = True

                if success:
                    sms.status = "sent"
                    sms.sent_at = timezone.now()
                elif retry_later:
                    sms.status = "pending"
                    sms.sent_at = None
                else:
                    sms.status = "failed"
                    sms.sent_at = timezone.now()

                sms.gateway_response = gateway_response
                sms.error_message = error_message
                sms.save(update_fields=[
                    "status",
                    "sent_at",
                    "gateway_response",
                    "error_message",
                ])

                self.stdout.write(f"SMS {sms.outboxid} -> {sms.status}")

                if success:
                    delay = 10 if len(sms.message) <= 160 else 17
                    time.sleep(delay)
