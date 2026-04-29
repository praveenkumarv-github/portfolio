from django.db import models


class FileUploadHistory(models.Model):
    """Store the last uploaded file path for convenience"""
    file_path = models.CharField(max_length=500)
    uploaded_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.file_path} - {self.uploaded_at}"
