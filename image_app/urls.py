from django.urls import path
from . import views

app_name = 'image_app'

urlpatterns = [
    path('', views.home, name='home'),
    path('process/', views.process_image, name='process_image'),
    path('preview/<int:image_id>/', views.preview_image, name='preview_image'),
    path('download/<int:image_id>/', views.download_image, name='download_image'),
    path('signature/', views.signature, name='signature'),
    path('process-signature/', views.process_signature, name='process_signature'),
    path('preview-signature/<int:image_id>/', views.preview_signature, name='preview_signature'),
    path('download-signature/<int:image_id>/', views.download_signature, name='download_signature'),
]