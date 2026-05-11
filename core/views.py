import json
import requests
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from .models import Users, Announcements, SmsOutbox
from django.shortcuts import render
from django.utils import timezone
from django.conf import settings

def landing_page(request):
    return render(request, 'landing.html')

def login_page(request):
    return render(request, 'login.html')

def register_page(request):
    return render(request, 'register.html')


def get_users(request):
    data = list(Users.objects.all().values())
    return JsonResponse(data, safe=False)


def get_announcements(request):
    data = list(Announcements.objects.all().values())
    return JsonResponse(data, safe=False)


def get_announcement_detail(request, announcement_id):
    try:
        announcement = Announcements.objects.values().get(announcement_id=announcement_id)
        return JsonResponse(announcement, safe=False)
    except Announcements.DoesNotExist:
        return JsonResponse({"error": "Announcement not found"}, status=404)

@csrf_exempt
def create_announcement(request):
    if request.method == "POST":
        data = json.loads(request.body)

        send_sms_value = int(data.get("send_sms", 0))
        gateway_response = None

        announcement = Announcements.objects.create(
            title=data.get("title"),
            content=data.get("content"),
            send_sms=send_sms_value,
            category_id=1,
            posted_by_id=1
        )

        if send_sms_value == 1:
            gateway_response = send_sms(
                recipient_number="09175585424",
                message=f"New announcement: {announcement.title}",
                sent_by=1
            )

        return JsonResponse({
            "message": "Announcement created successfully",
            "announcement_id": announcement.announcement_id,
            "send_sms_value": send_sms_value,
            "gateway_response": gateway_response
        })

    return JsonResponse({"error": "POST request required"}, status=400)

@csrf_exempt
def update_announcement(request, announcement_id):
    if request.method == "PUT":
        data = json.loads(request.body)

        try:
            announcement = Announcements.objects.get(announcement_id=announcement_id)
            announcement.title = data.get("title", announcement.title)
            announcement.content = data.get("content", announcement.content)
            announcement.send_sms = data.get("send_sms", announcement.send_sms)
            announcement.save()

            return JsonResponse({"message": "Announcement updated successfully"})
        except Announcements.DoesNotExist:
            return JsonResponse({"error": "Announcement not found"}, status=404)

    return JsonResponse({"error": "PUT request required"}, status=400)

@csrf_exempt
def delete_announcement(request, announcement_id):
    if request.method == "DELETE":
        try:
            announcement = Announcements.objects.get(announcement_id=announcement_id)
            announcement.delete()
            return JsonResponse({"message": "Announcement deleted successfully"})
        except Announcements.DoesNotExist:
            return JsonResponse({"error": "Announcement not found"}, status=404)

    return JsonResponse({"error": "DELETE request required"}, status=400)


def send_sms(recipient_number, message, sent_by):

    url = settings.SMS_URL

    params = {
        "USERNAME": settings.SMS_USERNAME,
        "PASSWORD": settings.SMS_PASSWORD,
        "smsnum": recipient_number,
        "Memo": message,
        "method": "2",
        "smsprovider": settings.SMS_PROVIDER
    }

    response = requests.get(url, params=params)

    sms = SmsOutbox.objects.create(
        recipient_number=recipient_number,
        message=message,
        sent_by_id=sent_by,
        sent_at=timezone.now()
    )

    return response.text

@csrf_exempt
def create_sms_log(request):
    if request.method == "POST":
        data = json.loads(request.body)

        sms = send_sms(
            data.get("recipient_number"),
            data.get("message"),
            data.get("sent_by")
        )

        return JsonResponse({
            "message": "SMS log created successfully",
            "outbox_id": sms.outboxid,
        })

    return JsonResponse({"error": "POST request required"}, status=400)

@csrf_exempt
def get_sms_logs(request):
    data = list(SmsOutbox.objects.all().values())
    return JsonResponse(data, safe=False)

def admin_dashboard(request):
    return render(request, 'admin_dashboard.html')