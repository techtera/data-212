"""Tests for src/services/gcs_service.py — V4-GCS-M0.

All tests mock the google.cloud.storage SDK; no real GCS calls are made.
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.services.gcs_service import (
    GCSServiceError,
    _clamp_ttl,
    _validate_object_path,
    delete_object,
    mint_signed_get_url,
    mint_signed_put_url,
    object_exists,
)

# ── Path validation ───────────────────────────────────────────────────────────


class TestValidateObjectPath:
    """Tests for _validate_object_path."""

    def test_valid_datasets_prefix(self):
        _validate_object_path("datasets/ds_abc/raw.zip")  # no error

    def test_valid_weights_prefix(self):
        _validate_object_path("weights/base.pt")  # no error

    def test_valid_results_prefix(self):
        _validate_object_path("results/job_123/best.pt")  # no error

    def test_rejects_empty_path(self):
        with pytest.raises(GCSServiceError, match="cannot be empty"):
            _validate_object_path("")

    def test_rejects_disallowed_prefix(self):
        with pytest.raises(GCSServiceError, match="must start with one of"):
            _validate_object_path("secret/keys/leak.json")

    def test_rejects_path_traversal_dotdot(self):
        with pytest.raises(GCSServiceError, match="path traversal"):
            _validate_object_path("datasets/../secret/key.json")

    def test_rejects_path_traversal_double_slash(self):
        with pytest.raises(GCSServiceError, match="path traversal"):
            _validate_object_path("datasets//evil.zip")

    def test_rejects_no_prefix(self):
        with pytest.raises(GCSServiceError, match="must start with one of"):
            _validate_object_path("raw.zip")


# ── TTL clamping ──────────────────────────────────────────────────────────────


class TestClampTtl:
    """Tests for _clamp_ttl — ensures TTL never exceeds 900s."""

    def test_default_uses_config(self):
        # Config default is 900
        assert _clamp_ttl(None) == 900

    def test_lower_value_passes_through(self):
        assert _clamp_ttl(300) == 300

    def test_exceeding_value_clamped_to_900(self):
        assert _clamp_ttl(1800) == 900

    def test_exact_900_passes(self):
        assert _clamp_ttl(900) == 900


# ── Signed PUT URL ────────────────────────────────────────────────────────────


class TestMintSignedPutUrl:
    """Tests for mint_signed_put_url."""

    @patch("src.services.gcs_service._get_cached_client")
    def test_returns_signed_url(self, mock_client):
        mock_blob = MagicMock()
        mock_blob.generate_signed_url.return_value = "https://storage.googleapis.com/signed-put"
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client.return_value.bucket.return_value = mock_bucket

        url = mint_signed_put_url("datasets/ds_123/raw.zip")

        assert url == "https://storage.googleapis.com/signed-put"
        mock_bucket.blob.assert_called_once_with("datasets/ds_123/raw.zip")
        mock_blob.generate_signed_url.assert_called_once()

    @patch("src.services.gcs_service._get_cached_client")
    def test_uses_v4_method_put_and_content_type(self, mock_client):
        mock_blob = MagicMock()
        mock_blob.generate_signed_url.return_value = "https://signed"
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client.return_value.bucket.return_value = mock_bucket

        mint_signed_put_url("datasets/ds_x/raw.zip", content_type="application/zip")

        call_kwargs = mock_blob.generate_signed_url.call_args[1]
        assert call_kwargs["version"] == "v4"
        assert call_kwargs["method"] == "PUT"
        assert call_kwargs["content_type"] == "application/zip"

    @patch("src.services.gcs_service._get_cached_client")
    def test_ttl_passed_as_timedelta(self, mock_client):
        mock_blob = MagicMock()
        mock_blob.generate_signed_url.return_value = "https://signed"
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client.return_value.bucket.return_value = mock_bucket

        mint_signed_put_url("datasets/ds_x/raw.zip", ttl_seconds=600)

        call_kwargs = mock_blob.generate_signed_url.call_args[1]
        assert call_kwargs["expiration"] == datetime.timedelta(seconds=600)

    def test_rejects_invalid_path(self):
        with pytest.raises(GCSServiceError, match="must start with one of"):
            mint_signed_put_url("bad/path/file.zip")

    @patch("src.services.gcs_service._get_cached_client")
    def test_wraps_sdk_exception(self, mock_client):
        mock_blob = MagicMock()
        mock_blob.generate_signed_url.side_effect = RuntimeError("SDK error")
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client.return_value.bucket.return_value = mock_bucket

        with pytest.raises(GCSServiceError, match="Failed to mint signed PUT URL"):
            mint_signed_put_url("datasets/ds_x/raw.zip")


# ── Signed GET URL ────────────────────────────────────────────────────────────


class TestMintSignedGetUrl:
    """Tests for mint_signed_get_url."""

    @patch("src.services.gcs_service._get_cached_client")
    def test_returns_signed_url(self, mock_client):
        mock_blob = MagicMock()
        mock_blob.generate_signed_url.return_value = "https://storage.googleapis.com/signed-get"
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client.return_value.bucket.return_value = mock_bucket

        url = mint_signed_get_url("results/job_abc/best.pt")

        assert url == "https://storage.googleapis.com/signed-get"
        mock_bucket.blob.assert_called_once_with("results/job_abc/best.pt")

    @patch("src.services.gcs_service._get_cached_client")
    def test_uses_v4_method_get(self, mock_client):
        mock_blob = MagicMock()
        mock_blob.generate_signed_url.return_value = "https://signed"
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client.return_value.bucket.return_value = mock_bucket

        mint_signed_get_url("weights/base.pt")

        call_kwargs = mock_blob.generate_signed_url.call_args[1]
        assert call_kwargs["version"] == "v4"
        assert call_kwargs["method"] == "GET"
        # GET URLs should NOT have a content_type restriction
        assert "content_type" not in call_kwargs

    def test_rejects_invalid_path(self):
        with pytest.raises(GCSServiceError, match="must start with one of"):
            mint_signed_get_url("unauthorized/secrets.json")

    @patch("src.services.gcs_service._get_cached_client")
    def test_wraps_sdk_exception(self, mock_client):
        mock_blob = MagicMock()
        mock_blob.generate_signed_url.side_effect = RuntimeError("boom")
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client.return_value.bucket.return_value = mock_bucket

        with pytest.raises(GCSServiceError, match="Failed to mint signed GET URL"):
            mint_signed_get_url("results/job_x/metrics.json")


# ── Object exists ─────────────────────────────────────────────────────────────


class TestObjectExists:
    """Tests for object_exists."""

    @patch("src.services.gcs_service._get_cached_client")
    def test_returns_true_when_exists(self, mock_client):
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client.return_value.bucket.return_value = mock_bucket

        assert object_exists("datasets/ds_123/raw.zip") is True

    @patch("src.services.gcs_service._get_cached_client")
    def test_returns_false_when_not_exists(self, mock_client):
        mock_blob = MagicMock()
        mock_blob.exists.return_value = False
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client.return_value.bucket.return_value = mock_bucket

        assert object_exists("datasets/ds_missing/raw.zip") is False

    def test_rejects_invalid_path(self):
        with pytest.raises(GCSServiceError, match="must start with one of"):
            object_exists("etc/passwd")

    @patch("src.services.gcs_service._get_cached_client")
    def test_wraps_sdk_exception(self, mock_client):
        mock_blob = MagicMock()
        mock_blob.exists.side_effect = RuntimeError("network error")
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client.return_value.bucket.return_value = mock_bucket

        with pytest.raises(GCSServiceError, match="Failed to check existence"):
            object_exists("datasets/ds_x/raw.zip")


# ── Delete object ─────────────────────────────────────────────────────────────


class TestDeleteObject:
    """Tests for delete_object."""

    @patch("src.services.gcs_service._get_cached_client")
    def test_deletes_existing_object(self, mock_client):
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client.return_value.bucket.return_value = mock_bucket

        assert delete_object("datasets/ds_old/raw.zip") is True
        mock_blob.delete.assert_called_once()

    @patch("src.services.gcs_service._get_cached_client")
    def test_returns_false_for_nonexistent(self, mock_client):
        mock_blob = MagicMock()
        mock_blob.exists.return_value = False
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client.return_value.bucket.return_value = mock_bucket

        assert delete_object("datasets/ds_ghost/raw.zip") is False
        mock_blob.delete.assert_not_called()

    def test_rejects_invalid_path(self):
        with pytest.raises(GCSServiceError, match="must start with one of"):
            delete_object("../../etc/shadow")


# ── Security: no raw URL in logs ──────────────────────────────────────────────


class TestSecurityNoUrlInLogs:
    """Ensure signed URLs are never logged (only metadata)."""

    @patch("src.services.gcs_service._get_cached_client")
    def test_put_url_not_in_log_output(self, mock_client, caplog):
        mock_blob = MagicMock()
        fake_url = "https://storage.googleapis.com/terafac-datasets/SECRET_SIGNED_TOKEN"
        mock_blob.generate_signed_url.return_value = fake_url
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client.return_value.bucket.return_value = mock_bucket

        import logging

        with caplog.at_level(logging.DEBUG, logger="src.services.gcs_service"):
            mint_signed_put_url("datasets/ds_test/raw.zip")

        # The actual signed URL string should NOT appear in logs
        assert "SECRET_SIGNED_TOKEN" not in caplog.text

    @patch("src.services.gcs_service._get_cached_client")
    def test_get_url_not_in_log_output(self, mock_client, caplog):
        mock_blob = MagicMock()
        fake_url = "https://storage.googleapis.com/terafac-datasets/SECRET_GET_TOKEN"
        mock_blob.generate_signed_url.return_value = fake_url
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client.return_value.bucket.return_value = mock_bucket

        import logging

        with caplog.at_level(logging.DEBUG, logger="src.services.gcs_service"):
            mint_signed_get_url("results/job_abc/best.pt")

        # The actual signed URL string should NOT appear in logs
        assert "SECRET_GET_TOKEN" not in caplog.text
