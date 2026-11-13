"""Service tests: image validation and Cloudinary wrapper (task T09).

Cloudinary itself is never called: ``uploader.upload`` / ``uploader.destroy`` are patched.
"""

import asyncio
import io

import pytest
from starlette.datastructures import Headers
from starlette.datastructures import UploadFile

from app.config import settings
from app.services import cloudinary as cloud
from tests.support import JPEG_BYTES, PNG_BYTES, WEBP_BYTES


def _upload_file(content: bytes, content_type: str = "image/png", filename: str = "photo.png") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def _run(coro):
    return asyncio.run(coro)


class TestMagicByteValidation:
    @pytest.mark.parametrize(
        "content",
        [JPEG_BYTES, PNG_BYTES, WEBP_BYTES],
        ids=["jpeg", "png", "webp"],
    )
    def test_supported_formats_pass(self, content):
        """TC-SVC-IMG-001 | AC-16.1 | T09 | positive | JPEG, PNG and WebP signatures are accepted"""
        cloud._validate_image_magic_bytes(content)

    def test_unsupported_signature_is_rejected(self):
        """TC-SVC-IMG-002 | AC-16.1 | T09 | negative | a GIF signature is rejected"""
        with pytest.raises(ValueError, match="does not match"):
            cloud._validate_image_magic_bytes(b"GIF89a" + b"\x00" * 20)

    def test_plain_text_is_rejected(self):
        """TC-SVC-IMG-003 | AC-16.1 | T09 | negative | arbitrary text renamed to .png is rejected"""
        with pytest.raises(ValueError):
            cloud._validate_image_magic_bytes(b"this is definitely not an image at all")

    def test_eleven_bytes_is_too_small(self):
        """TC-SVC-IMG-004 | AC-16.1 | T09 | boundary | 11 bytes is below the 12-byte minimum"""
        with pytest.raises(ValueError, match="too small"):
            cloud._validate_image_magic_bytes(b"\xff\xd8\xff" + b"\x00" * 8)

    def test_twelve_bytes_is_the_minimum(self):
        """TC-SVC-IMG-005 | AC-16.1 | T09 | boundary | exactly 12 bytes with a valid signature passes"""
        cloud._validate_image_magic_bytes(b"\xff\xd8\xff" + b"\x00" * 9)

    def test_riff_without_webp_marker_is_rejected(self):
        """TC-SVC-IMG-006 | AC-16.1 | T09 | negative | a RIFF container that is not WebP (e.g. WAV) is rejected"""
        with pytest.raises(ValueError):
            cloud._validate_image_magic_bytes(b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 8)


class TestUploadImage:
    @pytest.fixture()
    def uploads(self, monkeypatch):
        """Replace uploader.upload; returns the list of recorded calls."""
        calls = []

        def fake_upload(stream, **kwargs):
            calls.append({"stream": stream, **kwargs})
            return {
                "public_id": "infyexchange/listings/5/abc",
                "secure_url": "https://res.cloudinary.com/test/abc.png",
            }

        monkeypatch.setattr(cloud.uploader, "upload", fake_upload)
        return calls

    def test_valid_image_is_uploaded_to_listing_folder(self, uploads):
        """TC-SVC-IMG-010 | AC-16.2 | T09 | positive | valid PNG uploads into infyexchange/listings/<id> and returns id + url"""
        result = _run(cloud.upload_image(_upload_file(PNG_BYTES), listing_id=5))
        assert result == {
            "public_id": "infyexchange/listings/5/abc",
            "url": "https://res.cloudinary.com/test/abc.png",
        }
        assert uploads[0]["folder"] == "infyexchange/listings/5"
        assert uploads[0]["resource_type"] == "image"

    @pytest.mark.parametrize(
        "content_type, content",
        [("image/jpeg", JPEG_BYTES), ("image/webp", WEBP_BYTES)],
        ids=["jpeg", "webp"],
    )
    def test_other_allowed_types_upload(self, uploads, content_type, content):
        """TC-SVC-IMG-011 | AC-16.1 | T09 | positive | JPEG and WebP uploads are accepted"""
        _run(cloud.upload_image(_upload_file(content, content_type), listing_id=1))
        assert len(uploads) == 1

    def test_disallowed_content_type_is_rejected_before_upload(self, uploads):
        """TC-SVC-IMG-012 | AC-16.1 | T09 | negative | image/gif is refused and nothing is sent to Cloudinary"""
        with pytest.raises(ValueError, match="Only JPEG, PNG and WebP"):
            _run(cloud.upload_image(_upload_file(PNG_BYTES, "image/gif"), listing_id=1))
        assert uploads == []

    def test_content_type_and_content_must_agree(self, uploads):
        """TC-SVC-IMG-013 | AC-16.1 | T09 | negative | image/png header with non-image bytes is rejected"""
        with pytest.raises(ValueError):
            _run(cloud.upload_image(_upload_file(b"<html>not an image</html>" * 4, "image/png"), listing_id=1))
        assert uploads == []

    def test_image_at_exact_size_limit_is_accepted(self, uploads, monkeypatch):
        """TC-SVC-IMG-014 | AC-16.1 | T09 | boundary | a file of exactly MAX_IMAGE_SIZE_MB passes"""
        monkeypatch.setattr(settings, "max_image_size_mb", 1)
        content = PNG_BYTES + b"\x00" * (1024 * 1024 - len(PNG_BYTES))
        assert len(content) == 1024 * 1024
        _run(cloud.upload_image(_upload_file(content), listing_id=1))
        assert len(uploads) == 1

    def test_image_one_byte_over_limit_is_rejected(self, uploads, monkeypatch):
        """TC-SVC-IMG-015 | AC-16.1 | T09 | boundary | one byte over MAX_IMAGE_SIZE_MB is rejected"""
        monkeypatch.setattr(settings, "max_image_size_mb", 1)
        content = PNG_BYTES + b"\x00" * (1024 * 1024 - len(PNG_BYTES) + 1)
        with pytest.raises(ValueError, match="maximum allowed size"):
            _run(cloud.upload_image(_upload_file(content), listing_id=1))
        assert uploads == []


class TestDeleteImage:
    def test_delete_calls_destroy_with_invalidate(self, monkeypatch):
        """TC-SVC-IMG-020 | AC-07.4 | T09 | positive | delete_image destroys the asset by public id and invalidates the CDN"""
        calls = []
        monkeypatch.setattr(cloud.uploader, "destroy", lambda public_id, **kw: calls.append((public_id, kw)))
        cloud.delete_image("infyexchange/listings/5/abc")
        assert calls == [("infyexchange/listings/5/abc", {"resource_type": "image", "invalidate": True})]
