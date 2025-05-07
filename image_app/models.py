from django.db import models

class ProcessedImage(models.Model):
    original_image = models.ImageField(upload_to='original/')
    processed_image = models.ImageField(upload_to='processed/', null=True, blank=True)
    width = models.FloatField(null=True)
    height = models.FloatField(null=True)
    unit = models.CharField(max_length=10, choices=[
        ('mm', 'Millimeters'),
        ('cm', 'Centimeters'),
        ('in', 'Inches')
    ], default='px')
    dpi = models.IntegerField(default=300)
    remove_background = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f'ProcessedImage {self.id} - {self.created_at}'