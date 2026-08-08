"""Unit tests for the CreatorOS artifact materialization service."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from creatoros.config import Settings
from creatoros.core import ArtifactAlreadyExistsError, ArtifactPathError, ArtifactPayloadError
from creatoros.domain import AssetType, GeneratedAsset
from creatoros.providers import GeneratedAudio, GeneratedImage, GeneratedVideo
from creatoros.services import (
    ArtifactKind,
    ArtifactMaterializationService,
    GeneratedMediaPackage,
    MaterializedArtifact,
    MaterializedMediaPackage,
)
from creatoros.services.artifact_materialization import build_safe_filename

MINIMAL_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\x0bIDATx\x9cc``\x00\x00\x00\x02\x00\x01H\xaf\xa4q"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)
MINIMAL_WAV_BYTES = (
    b"RIFF(\x00\x00\x00WAVEfmt "
    b"\x10\x00\x00\x00\x01\x00\x01\x00@\x1f\x00\x00@\x1f\x00\x00"
    b"\x01\x00\x08\x00data\x04\x00\x00\x00\x80\x80\x80\x80"
)


def build_settings(tmp_path: Path) -> Settings:
    """Create isolated settings with a temporary artifact root."""

    return Settings.model_construct(
        app_name="CreatorOS",
        app_env="testing",
        debug=True,
        log_level="INFO",
        database_url="postgresql+psycopg://creatoros_user:change_me@localhost:5432/creatoros_test",
        default_llm_provider="mock",
        default_llm_model="mock-model",
        default_image_provider="mock",
        default_image_model=None,
        default_tts_provider="mock",
        default_tts_model=None,
        default_video_provider="mock",
        default_render_provider="mock",
        openai_api_key=None,
        anthropic_api_key=None,
        youtube_client_id=None,
        youtube_client_secret=None,
        provider_timeout_seconds=30.0,
        provider_max_retries=3,
        artifact_root=tmp_path / "artifacts",
        assets_dir=tmp_path / "assets",
        logs_dir=tmp_path / "logs",
        prompts_dir=tmp_path / "prompts",
    )


def build_image(*, payload_bytes: bytes | None = MINIMAL_PNG_BYTES, mime_type: str = "image/png") -> GeneratedImage:
    """Create a reusable generated image result."""

    return GeneratedImage(
        artifact=GeneratedAsset(asset_type=AssetType.IMAGE, uri="mock://generated/image/example.png"),
        provider_name="mock",
        model="mock-image-model",
        mime_type=mime_type,
        width=1024,
        height=1024,
        request_id="req_img_123",
        metadata={"mock": True},
        payload_bytes=payload_bytes,
    )


def build_audio(*, payload_bytes: bytes | None = MINIMAL_WAV_BYTES, mime_type: str = "audio/wav") -> GeneratedAudio:
    """Create a reusable generated audio result."""

    return GeneratedAudio(
        artifact=GeneratedAsset(asset_type=AssetType.AUDIO, uri="mock://generated/audio/example.wav"),
        provider_name="mock",
        model="mock-tts-model",
        mime_type=mime_type,
        estimated_duration_seconds=3.0,
        request_id="req_tts_123",
        metadata={"mock": True},
        payload_bytes=payload_bytes,
    )


def build_video(*, payload_bytes: bytes | None = None, mime_type: str = "video/mp4") -> GeneratedVideo:
    """Create a reusable generated video result."""

    return GeneratedVideo(
        artifact=GeneratedAsset(asset_type=AssetType.VIDEO, uri="mock://generated/video/example.mp4"),
        provider_name="mock",
        model="mock-video-model",
        mime_type=mime_type,
        duration_seconds=4.0,
        width=1080,
        height=1920,
        fps=30.0,
        request_id="req_vid_123",
        metadata={"mock": True},
        payload_bytes=payload_bytes,
    )


def build_service(tmp_path: Path) -> ArtifactMaterializationService:
    """Create a materialization service with isolated test settings."""

    return ArtifactMaterializationService(build_settings(tmp_path))


def test_valid_run_id_is_accepted_and_directories_are_deterministic(tmp_path: Path) -> None:
    """Valid run IDs should build deterministic workspace directories safely."""

    service = build_service(tmp_path)

    workspace = service.create_workspace(run_id="run_001")

    assert workspace.workspace_path == service.settings.artifact_root / "run_001"
    assert workspace.images_dir == workspace.workspace_path / "images"
    assert workspace.audio_dir == workspace.workspace_path / "audio"
    assert workspace.video_dir == workspace.workspace_path / "video"


@pytest.mark.parametrize("run_id", ["", "   ", "../bad", "..\\bad", "a/b", "a\\b", "C:\\temp", ".", ".."])
def test_unsafe_run_ids_are_rejected(run_id: str, tmp_path: Path) -> None:
    """Blank or traversal-capable run IDs should fail safely."""

    service = build_service(tmp_path)

    with pytest.raises(ArtifactPathError):
        service.create_workspace(run_id=run_id)


def test_workspace_prepare_creates_only_expected_directories(tmp_path: Path) -> None:
    """Preparing one workspace should create the expected local directory layout."""

    service = build_service(tmp_path)
    workspace = service.create_workspace(run_id="job-abc123")

    workspace.prepare()

    assert workspace.images_dir.is_dir()
    assert workspace.audio_dir.is_dir()
    assert workspace.video_dir.is_dir()
    assert sorted(path.name for path in workspace.workspace_path.iterdir()) == ["audio", "images", "video"]


def test_safe_filename_is_deterministic_and_controlled() -> None:
    """Filename building should sanitize safe characters and derive the extension from MIME type."""

    filename = build_safe_filename(logical_name='Scene 001*?"<>|', mime_type="image/png")

    assert filename == "Scene_001.png"


@pytest.mark.parametrize("logical_name", ["../bad", "..\\bad", "a/b", "a\\b", "C:\\temp", ".", "..", "   "])
def test_unsafe_logical_names_are_rejected(logical_name: str) -> None:
    """Unsafe logical names should fail safely before any filesystem write."""

    with pytest.raises(ArtifactPathError):
        build_safe_filename(logical_name=logical_name, mime_type="image/png")


def test_unsupported_mime_type_is_rejected() -> None:
    """Only allowlisted MIME types should produce local artifact filenames."""

    with pytest.raises(ArtifactPathError):
        build_safe_filename(logical_name="thumbnail", mime_type="application/octet-stream")


def test_payload_bytes_remain_ephemeral_and_excluded_from_serialization() -> None:
    """Binary payload bytes should stay off normal serialized results."""

    image = build_image()
    dumped = image.model_dump()

    assert image.payload_bytes == MINIMAL_PNG_BYTES
    assert "payload_bytes" not in dumped
    assert "mock" in dumped["metadata"]


def test_image_materialization_writes_expected_bytes_and_extension(tmp_path: Path) -> None:
    """Images should materialize into the images directory with exact payload bytes."""

    service = build_service(tmp_path)
    workspace = service.create_workspace(run_id="run_001")

    artifact = service.materialize_image(build_image(), workspace=workspace, logical_name="thumbnail")

    assert isinstance(artifact, MaterializedArtifact)
    assert artifact.kind is ArtifactKind.IMAGE
    assert artifact.path.parent == workspace.images_dir
    assert artifact.path.name == "thumbnail.png"
    assert artifact.path.read_bytes() == MINIMAL_PNG_BYTES
    assert artifact.size_bytes == len(MINIMAL_PNG_BYTES)


def test_audio_materialization_writes_expected_bytes_and_extension(tmp_path: Path) -> None:
    """Audio should materialize into the audio directory with exact payload bytes."""

    service = build_service(tmp_path)
    workspace = service.create_workspace(run_id="run_001")

    artifact = service.materialize_audio(build_audio(), workspace=workspace, logical_name="narration")

    assert artifact.kind is ArtifactKind.AUDIO
    assert artifact.path.parent == workspace.audio_dir
    assert artifact.path.name == "narration.wav"
    assert artifact.path.read_bytes() == MINIMAL_WAV_BYTES
    assert artifact.size_bytes == len(MINIMAL_WAV_BYTES)


def test_missing_video_payload_fails_safely(tmp_path: Path) -> None:
    """Video materialization should fail clearly when no payload exists yet."""

    service = build_service(tmp_path)
    workspace = service.create_workspace(run_id="run_001")

    with pytest.raises(ArtifactPayloadError):
        service.materialize_video(build_video(payload_bytes=None), workspace=workspace, logical_name="clip_001")


def test_atomic_write_cleans_temporary_file_on_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A failed atomic write should leave no final or temporary artifact file behind."""

    service = build_service(tmp_path)
    workspace = service.create_workspace(run_id="run_001")
    destination_dir = workspace.images_dir
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_path = destination_dir / "thumbnail.png"

    def exploding_replace(src: str | bytes | os.PathLike[str] | os.PathLike[bytes], dst: str | bytes | os.PathLike[str] | os.PathLike[bytes]) -> None:
        raise OSError("replace failed")

    import creatoros.services.artifact_materialization as artifact_module

    monkeypatch.setattr(artifact_module.os, "replace", exploding_replace)

    with pytest.raises(OSError):
        service._atomic_write_bytes(destination_path, MINIMAL_PNG_BYTES)

    assert destination_path.exists() is False
    assert list(destination_dir.glob(".artifact_tmp_*")) == []


def test_existing_artifact_is_not_silently_overwritten(tmp_path: Path) -> None:
    """Existing final files should remain unchanged on name collision."""

    service = build_service(tmp_path)
    workspace = service.create_workspace(run_id="run_001")
    first = service.materialize_image(build_image(), workspace=workspace, logical_name="thumbnail")

    with pytest.raises(ArtifactAlreadyExistsError):
        service.materialize_image(build_image(payload_bytes=b"new-bytes"), workspace=workspace, logical_name="thumbnail")

    assert first.path.read_bytes() == MINIMAL_PNG_BYTES


def test_materialize_package_returns_typed_result_and_preserves_order(tmp_path: Path) -> None:
    """Package materialization should preserve deterministic ordering and naming."""

    service = build_service(tmp_path)
    package = GeneratedMediaPackage(
        thumbnail=build_image(),
        narration=build_audio(),
        scene_images=(build_image(), build_image(payload_bytes=MINIMAL_PNG_BYTES + b"2")),
    )

    result = service.materialize_package(package, run_id="run_001")

    assert isinstance(result, MaterializedMediaPackage)
    assert result.thumbnail is not None and result.thumbnail.path.name == "thumbnail.png"
    assert result.narration is not None and result.narration.path.name == "narration.wav"
    assert [artifact.path.name for artifact in result.scene_images] == ["scene_001.png", "scene_002.png"]
    assert result.scene_videos == ()


def test_package_failure_cleans_only_files_created_by_that_operation(tmp_path: Path) -> None:
    """A failed package materialization should clean new files but not pre-existing ones."""

    service = build_service(tmp_path)
    workspace = service.create_workspace(run_id="run_001")
    workspace.prepare()
    preexisting = workspace.images_dir / "thumbnail.png"
    preexisting.write_bytes(b"preexisting")
    package = GeneratedMediaPackage(
        thumbnail=build_image(),
        narration=build_audio(),
    )

    with pytest.raises(ArtifactAlreadyExistsError):
        service.materialize_package(package, run_id="run_001")

    assert preexisting.read_bytes() == b"preexisting"
    assert list(workspace.audio_dir.iterdir()) == []


def test_materializer_module_stays_local_only_and_does_not_call_providers_or_rendering() -> None:
    """The artifact materializer should remain a local filesystem layer only."""

    module_source = Path("creatoros/services/artifact_materialization.py").read_text(encoding="utf-8")

    assert "MediaGenerationService" not in module_source
    assert "RenderProvider" not in module_source
    assert "MediaRenderService" not in module_source
    assert "publish(" not in module_source
    assert "ffmpeg" not in module_source.lower()
    assert "cloudinary" not in module_source.lower()
