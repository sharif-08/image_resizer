from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from .models import ProcessedImage
from PIL import Image
import io
from rembg import remove
import numpy as np
import base64

def home(request):
    return render(request, 'image_app/home.html')

def process_image(request):
    if request.method == 'POST':
        if 'image' not in request.FILES:
            messages.error(request, 'Please select an image file')
            return redirect('image_app:home')
            
        image_file = request.FILES['image']
        
        # Validate file size (max 10MB)
        if image_file.size > 10 * 1024 * 1024:  # 10MB in bytes
            messages.error(request, 'Image size must be less than 10MB')
            return redirect('image_app:home')
            
        # Validate image format
        allowed_formats = ['image/jpeg', 'image/png', 'image/gif', 'image/bmp']
        if image_file.content_type not in allowed_formats:
            messages.error(request, 'Unsupported image format. Please use JPEG, PNG, GIF or BMP')
            return redirect('image_app:home')
            
        try:
            width = float(request.POST.get('width', 0))
            height = float(request.POST.get('height', 0))
            unit = request.POST.get('unit', 'px')
            dpi = int(request.POST.get('dpi', 300))
            target_size = int(request.POST.get('target_size', 0))
            remove_bg = request.POST.get('remove_background', False) == 'true'
            
            # Validate dimensions
            if width < 0 or height < 0:
                messages.error(request, 'Width and height must be positive values')
                return redirect('image_app:home')
                
            # Validate DPI
            if dpi < 72 or dpi > 1200:
                messages.error(request, 'DPI must be between 72 and 1200')
                return redirect('image_app:home')

            # Validate target size
            if target_size < 0 or target_size > 10000:
                messages.error(request, 'Target file size must be between 0 and 10000 KB')
                return redirect('image_app:home')

            # Convert dimensions to pixels based on unit and DPI
            if unit == 'mm':
                width = round((width / 25.4) * dpi)
                height = round((height / 25.4) * dpi)
            elif unit == 'cm':
                width = round((width / 2.54) * dpi)
                height = round((height / 2.54) * dpi)
            elif unit == 'in':
                width = round(width * dpi)
                height = round(height * dpi)
            elif unit == 'px':
                width = round(width)
                height = round(height)
            
            # Validate final pixel dimensions
            if width < 1 or height < 1:
                messages.error(request, 'Dimensions too small after conversion. Please increase size or DPI.')
                return redirect('image_app:home')
            if width > 10000 or height > 10000:
                messages.error(request, 'Dimensions too large after conversion. Please decrease size or DPI.')
                return redirect('image_app:home')

        except (ValueError, TypeError) as e:
            messages.error(request, 'Invalid dimensions or DPI value')
            return redirect('image_app:home')

        # Create ProcessedImage instance
        processed = ProcessedImage.objects.create(
            original_image=image_file,
            width=width,
            height=height,
            unit=unit,
            dpi=dpi,
            remove_background=remove_bg
        )

        try:
            # Open and process image
            img = Image.open(processed.original_image)
        except Exception as e:
            messages.error(request, 'Failed to process image. Please try again with a different image')
            return redirect('image_app:home')

        # Remove background if requested
        if remove_bg:
            try:
                # Convert PIL Image to bytes
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format=img.format)
                img_byte_arr = img_byte_arr.getvalue()

                # Remove background
                output = remove(img_byte_arr)
                img = Image.open(io.BytesIO(output))

                # Create white background
                white_bg = Image.new('RGBA', img.size, (255, 255, 255, 255))
                white_bg.paste(img, (0, 0), img)
                img = white_bg.convert('RGB')
            except Exception as e:
                messages.error(request, 'Failed to remove background. Please try with a different image')
                processed.delete()  # Cleanup the database entry
                return redirect('image_app:home')

        # Resize image
        if width and height:
            img = img.resize((int(width), int(height)), Image.Resampling.LANCZOS)

        # Save processed image with binary search for optimal quality and size
        output = io.BytesIO()
        quality = 95
        original_width = img.width
        original_height = img.height
        scale_factor = 1.0

        # Adjust quality and dimensions to meet target file size if specified
        if target_size > 0:
            # First try adjusting quality
            low_quality = 5
            high_quality = 95
            best_quality = 95
            min_diff = float('inf')

            while low_quality <= high_quality:
                current_quality = (low_quality + high_quality) // 2
                output = io.BytesIO()
                img.save(output, format='JPEG', quality=current_quality, dpi=(dpi, dpi))
                file_size = len(output.getvalue()) / 1024  # Convert to KB
                
                diff = abs(file_size - target_size)
                if diff < min_diff:
                    min_diff = diff
                    best_quality = current_quality

                if file_size > target_size:
                    high_quality = current_quality - 1
                else:
                    low_quality = current_quality + 1

            # If we still can't achieve target size, try adjusting dimensions
            output = io.BytesIO()
            img = img.resize((original_width, original_height), Image.Resampling.LANCZOS)
            img.save(output, format='JPEG', quality=best_quality, dpi=(dpi, dpi))
            file_size = len(output.getvalue()) / 1024

            if file_size > target_size:
                # Reduce dimensions gradually until target size is met
                while file_size > target_size and scale_factor > 0.1:
                    scale_factor *= 0.9
                    new_width = int(original_width * scale_factor)
                    new_height = int(original_height * scale_factor)
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    
                    output = io.BytesIO()
                    img.save(output, format='JPEG', quality=best_quality, dpi=(dpi, dpi))
                    file_size = len(output.getvalue()) / 1024
            elif file_size < target_size * 0.8:  # If file is much smaller, try increasing size
                while file_size < target_size and scale_factor < 2.0:
                    scale_factor *= 1.1
                    new_width = int(original_width * scale_factor)
                    new_height = int(original_height * scale_factor)
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    
                    output = io.BytesIO()
                    img.save(output, format='JPEG', quality=best_quality, dpi=(dpi, dpi))
                    file_size = len(output.getvalue()) / 1024

            if abs(file_size - target_size) / target_size > 0.2:  # If still off by more than 20%
                messages.warning(request, f'Achieved file size of {file_size:.1f}KB (target: {target_size}KB) while maintaining best possible quality')
        else:
            img.save(output, format='JPEG', quality=quality, dpi=(dpi, dpi))
            
        output.seek(0)

        # Save to model
        processed.processed_image.save(
            f'processed_{image_file.name}',
            io.BytesIO(output.getvalue()),
            save=True
        )

        return redirect('image_app:preview_image', image_id=processed.id)

    return redirect('image_app:home')

def preview_image(request, image_id):
    processed = get_object_or_404(ProcessedImage, id=image_id)
    context = {
        'processed': processed,
        'original_size': processed.original_image.size,
        'processed_size': processed.processed_image.size if processed.processed_image else None,
    }
    return render(request, 'image_app/preview.html', context)

def download_image(request, image_id):
    processed = get_object_or_404(ProcessedImage, id=image_id)
    response = HttpResponse(processed.processed_image, content_type='image/jpeg')
    response['Content-Disposition'] = f'attachment; filename="{processed.processed_image.name}"'
    return response

def signature(request):
    return render(request, 'image_app/signature.html')

def process_signature(request):
    if request.method == 'POST':
        if 'signature' not in request.FILES:
            messages.error(request, 'Please select a signature image file')
            return redirect('image_app:signature')
            
        signature_file = request.FILES['signature']
        
        # Validate file size (max 5MB for signatures)
        if signature_file.size > 5 * 1024 * 1024:  # 5MB in bytes
            messages.error(request, 'Signature image size must be less than 5MB')
            return redirect('image_app:signature')
            
        # Validate image format
        allowed_formats = ['image/jpeg', 'image/png', 'image/gif', 'image/bmp']
        if signature_file.content_type not in allowed_formats:
            messages.error(request, 'Unsupported image format. Please use JPEG, PNG, GIF or BMP')
            return redirect('image_app:signature')
            
        try:
            width = float(request.POST.get('width', 0))
            height = float(request.POST.get('height', 0))
            unit = request.POST.get('unit', 'px')
            dpi = int(request.POST.get('dpi', 300))
            target_size = int(request.POST.get('target_size', 0))
            
            # Validate dimensions
            if width < 0 or height < 0:
                messages.error(request, 'Width and height must be positive values')
                return redirect('image_app:signature')
                
            # Validate DPI
            if dpi < 72 or dpi > 1200:
                messages.error(request, 'DPI must be between 72 and 1200')
                return redirect('image_app:signature')

            # Convert dimensions to pixels based on unit and DPI
            if unit == 'mm':
                width = round((width / 25.4) * dpi)
                height = round((height / 25.4) * dpi)
            elif unit == 'cm':
                width = round((width / 2.54) * dpi)
                height = round((height / 2.54) * dpi)
            elif unit == 'in':
                width = round(width * dpi)
                height = round(height * dpi)
            elif unit == 'px':
                width = round(width)
                height = round(height)
            
            # Validate final pixel dimensions
            if width < 1 or height < 1:
                messages.error(request, 'Dimensions too small after conversion. Please increase size or DPI.')
                return redirect('image_app:signature')
            if width > 10000 or height > 10000:
                messages.error(request, 'Dimensions too large after conversion. Please decrease size or DPI.')
                return redirect('image_app:signature')

        except (ValueError, TypeError) as e:
            messages.error(request, 'Invalid dimensions or DPI value')
            return redirect('image_app:signature')

        # Create ProcessedImage instance for signature
        processed = ProcessedImage.objects.create(
            original_image=signature_file,
            width=width,
            height=height,
            unit=unit,
            dpi=dpi,
            remove_background=True  # Always remove background for signatures
        )

        try:
            # Open and process signature
            img = Image.open(processed.original_image)
        except Exception as e:
            messages.error(request, 'Failed to process signature. Please try again with a different image')
            return redirect('image_app:signature')

        try:
            # Convert PIL Image to bytes
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format=img.format)
            img_byte_arr = img_byte_arr.getvalue()

            # Remove background
            output = remove(img_byte_arr)
            img = Image.open(io.BytesIO(output))

            # Create transparent background
            img = img.convert('RGBA')
        except Exception as e:
            messages.error(request, 'Failed to process signature. Please try with a different image')
            processed.delete()  # Cleanup the database entry
            return redirect('image_app:signature')

        # Resize signature
        if width and height:
            img = img.resize((int(width), int(height)), Image.Resampling.LANCZOS)

        # Process signature with target size adjustment
        output = io.BytesIO()
        quality = 95  # Initial quality setting
        min_quality = 30  # Minimum acceptable quality
        max_quality = 100
        target_size_bytes = target_size * 1024 if target_size else 0  # Convert KB to bytes
        original_width = img.width
        original_height = img.height
        scale_factor = 1.0

        if target_size_bytes > 0:
            # First try adjusting quality
            best_quality = quality
            min_diff = float('inf')
            best_output = None

            while min_quality <= max_quality:
                quality = (min_quality + max_quality) // 2
                output = io.BytesIO()
                img.save(output, format='PNG', dpi=(dpi, dpi), quality=quality)
                current_size = output.tell()
                
                diff = abs(current_size - target_size_bytes)
                if diff < min_diff:
                    min_diff = diff
                    best_quality = quality
                    best_output = output.getvalue()

                if current_size > target_size_bytes:
                    max_quality = quality - 1
                else:
                    min_quality = quality + 1

            # If we still can't achieve target size, try adjusting dimensions
            if min_diff / target_size_bytes > 0.2:  # If off by more than 20%
                img = img.resize((original_width, original_height), Image.Resampling.LANCZOS)
                while scale_factor > 0.1:
                    new_width = int(original_width * scale_factor)
                    new_height = int(original_height * scale_factor)
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    
                    output = io.BytesIO()
                    img.save(output, format='PNG', dpi=(dpi, dpi), quality=best_quality)
                    current_size = output.tell()
                    
                    if current_size <= target_size_bytes:
                        break
                    scale_factor *= 0.9

                if current_size > target_size_bytes:
                    # If we couldn't achieve target size, use the best result from quality adjustment
                    output = io.BytesIO(best_output)
                    messages.warning(request, f'Could not achieve target size while maintaining image quality. Current size: {current_size/1024:.1f}KB')
            else:
                output = io.BytesIO(best_output)
        else:
            # If no target size specified, use default quality
            img.save(output, format='PNG', dpi=(dpi, dpi), quality=quality)
            
        output.seek(0)

        # Save to model
        processed.processed_image.save(
            f'signatures/processed_{signature_file.name}',
            io.BytesIO(output.getvalue()),
            save=True
        )

        return redirect('image_app:preview_signature', image_id=processed.id)

    return redirect('image_app:signature')

def preview_signature(request, image_id):
    processed = get_object_or_404(ProcessedImage, id=image_id)
    context = {
        'processed': processed,
        'original_size': processed.original_image.size,
        'processed_size': processed.processed_image.size if processed.processed_image else None,
    }
    return render(request, 'image_app/preview_signature.html', context)

def download_signature(request, image_id):
    processed = get_object_or_404(ProcessedImage, id=image_id)
    response = HttpResponse(processed.processed_image, content_type='image/png')
    response['Content-Disposition'] = f'attachment; filename="{processed.processed_image.name}"'
    return response