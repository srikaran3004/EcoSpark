from django.contrib import admin
from .models import RecyclingCenter, Device, UserCredit, Pickup, Challenge, ChallengeCompletion

@admin.register(RecyclingCenter)
class RecyclingCenterAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "latitude", "longitude")
    search_fields = ("name", "address")


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("model_name", "metal_value")
    search_fields = ("model_name",)


@admin.register(UserCredit)
class UserCreditAdmin(admin.ModelAdmin):
    list_display = ("user", "points")
    search_fields = ("user__username",)


@admin.register(Pickup)
class PickupAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "phone", "drive_type", "pickup_date", "pickup_time", "waste_type", "created_at")
    list_filter = ("drive_type", "pickup_date", "waste_type")
    search_fields = ("name", "email", "phone", "address")


@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    list_display = ("title", "co2_saved", "is_active", "order", "created_at")
    list_filter = ("is_active",)
    search_fields = ("title",)
    list_editable = ("is_active", "order")
    ordering = ("order", "-created_at")


@admin.register(ChallengeCompletion)
class ChallengeCompletionAdmin(admin.ModelAdmin):
    list_display = ("user", "challenge", "completed_at")
    search_fields = ("user__username", "challenge__title")
    list_filter = ("completed_at",)
