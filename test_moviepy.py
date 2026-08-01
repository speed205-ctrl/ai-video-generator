import os
import sys

try:
    from moviepy import ImageClip, AudioFileClip, concatenate_videoclips
    from PIL import Image

    print("Moviepy imported successfully.")

    # Create dummy files
    img_path = "test_img.png"
    audio_path = "test_audio.mp3"

    Image.new('RGB', (100, 100)).save(img_path)
    
    # We can't easily create a real valid MP3 in a few lines without a lib, but we can try to use a wav or just import errors
    print("Testing ImageClip")
    clip = ImageClip(img_path)
    print("ImageClip created:", clip)
except Exception as e:
    print("Error:", e)
