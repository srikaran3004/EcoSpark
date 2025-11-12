from django.db import models
from django.contrib.auth.models import User


class RecyclingCenter(models.Model):
    name = models.CharField(max_length=100)
    address = models.TextField()
    latitude = models.FloatField()
    longitude = models.FloatField()

    def __str__(self):
        return self.name


class Device(models.Model):
    model_name = models.CharField(max_length=100)
    metal_value = models.FloatField(help_text="Approx. grams of recoverable metal")

    def __str__(self):
        return self.model_name


class UserCredit(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    points = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.user.username} - {self.points} pts"


class Pickup(models.Model):
    DRIVE_TYPE_CHOICES = [
        ("single_pickup", "Single Pickup"),
        ("community_drive", "Community Drive"),
    ]
    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address = models.TextField()
    waste_type = models.CharField(max_length=50)
    drive_type = models.CharField(max_length=20, choices=DRIVE_TYPE_CHOICES)
    pickup_date = models.DateField()
    pickup_time = models.TimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.get_drive_type_display()} on {self.pickup_date}"


class Challenge(models.Model):
    title = models.CharField(max_length=200, help_text="Challenge title (e.g., 'Recycle 1 old phone')")
    co2_saved = models.FloatField(help_text="CO2 saved in kg (e.g., 1.0)")
    is_active = models.BooleanField(default=True, help_text="Show this challenge to users?")
    order = models.IntegerField(default=0, help_text="Display order (lower numbers first)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', '-created_at']

    def __str__(self):
        return f"{self.title} ({self.co2_saved} kg CO2)"


class ChallengeCompletion(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="challenge_completions")
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name="completions")
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "challenge")
        ordering = ["-completed_at"]

    def __str__(self):
        return f"{self.user.username} → {self.challenge.title}"
