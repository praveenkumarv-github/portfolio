from django.db import models


class FileUploadHistory(models.Model):
    """Store the last uploaded file path for convenience"""
    file_path = models.CharField(max_length=500)
    uploaded_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.file_path} - {self.uploaded_at}"


class NetWorthSnapshot(models.Model):
    """
    Monthly snapshot of net worth components.
    Captured on each file upload, keyed by YYYY-MM so only one row per month.
    """
    month         = models.CharField(max_length=7, unique=True)   # e.g. "2026-04"
    total_net_worth     = models.FloatField(default=0)
    mutual_funds        = models.FloatField(default=0)
    retirement          = models.FloatField(default=0)
    liquid              = models.FloatField(default=0)
    emergency_fund      = models.FloatField(default=0)
    metals              = models.FloatField(default=0)
    captured_at         = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['month']

    def __str__(self):
        return f"{self.month}  ₹{self.total_net_worth:,.0f}"

