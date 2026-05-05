import json
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from .models import Users, Announcements


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

        announcement = Announcements.objects.create(
            title=data.get("title"),
            content=data.get("content"),
            send_sms=data.get("send_sms", 0),
            category_id=1,          # temporary default
            posted_by_id=1          # temporary default
        )

        return JsonResponse({
            "message": "Announcement created successfully",
            "announcement_id": announcement.announcement_id
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