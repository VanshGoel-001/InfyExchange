import asyncio
import io

import cloudinary
from cloudinary import uploader

from fastapi import UploadFile

from app.config import settings


cloudinary.config(
    cloud_name=settings.cloudinary_cloud_name,
    api_key=settings.cloudinary_api_key,
    api_secret=settings.cloudinary_api_secret,
    secure=True,
)


ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}


def _validate_image_magic_bytes(content: bytes) -> None:
    """Verify file content starts with a valid image signature."""
    if len(content) < 12:
        raise ValueError(
            "File is too small to be a valid image"
        )
    if content[:3] == b"\xff\xd8\xff":
        return  # JPEG
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return  # PNG
    if (
        content[:4] == b"RIFF"
        and content[8:12] == b"WEBP"
    ):
        return  # WebP
    raise ValueError(
        "File content does not match a supported image format"
    )


async def upload_image(
    file: UploadFile,
    listing_id: int,
) -> dict:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError(
            "Only JPEG, PNG and WebP images are allowed"
        )

    max_size = (
        settings.max_image_size_mb
        * 1024
        * 1024
    )

    # Stream chunks up to max_size + 1 to prevent unbounded RAM allocation (OOM guard)
    chunk_size = 64 * 1024
    byte_array = bytearray()
    
    while chunk := await file.read(chunk_size):
        byte_array.extend(chunk)
        if len(byte_array) > max_size:
            raise ValueError(
                f"Image exceeds the maximum allowed size of {settings.max_image_size_mb} MB."
            )

    content = bytes(byte_array)
    _validate_image_magic_bytes(content)

    file_stream = io.BytesIO(content)
    # Never the user's filename: Cloudinary then names the stored file with a random id.
    file_stream.name = "image"

    # Execute synchronous Cloudinary network call in a worker thread so event loop is not blocked
    result = await asyncio.to_thread(
        uploader.upload,
        file_stream,
        folder=f"infyexchange/listings/{listing_id}",
        resource_type="image",
        use_filename=False,
        unique_filename=True,
        # Applied before the file is stored, so the saved original is already small, WebP and
        # free of EXIF/location metadata (strip_profile). "limit" never enlarges a small image.
        format="webp",
        transformation=[
            {
                "width": settings.max_image_width,
                "crop": "limit",
                "flags": "strip_profile",
            }
        ],
    )

    # Cloudinary reports the stored size, so a too-small image is caught here and removed again.
    if result.get("width", 0) < settings.min_image_width:
        await asyncio.to_thread(delete_image, result["public_id"])
        raise ValueError(
            f"Image is too small. Use a photo at least {settings.min_image_width} pixels wide."
        )

    return {
        "public_id": result["public_id"],
        "url": result["secure_url"],
    }


def delete_image(public_id: str):
    uploader.destroy(
        public_id,
        resource_type="image",
        invalidate=True,
    )