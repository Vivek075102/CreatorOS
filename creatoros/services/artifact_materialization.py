"""Local runtime artifact materialization for provider-generated media."""

from __future__ import annotations

import os
import re
import tempfile
from enum import StrEnum
from pathlib import Path

from pydantic import Field, field_validator

from creatoros.config import Settings, get_settings
from creatoros.core import (
    ArtifactAlreadyExistsError,
    ArtifactPathError,
    ArtifactPayloadError,
    CreatorOSValidationError,
)
from creatoros.domain import CreatorOSModel, GeneratedAsset
from creatoros.observability import get_logger
from creatoros.providers import GeneratedAudio, GeneratedImage, GeneratedVideo
from creatoros.services.media_generation import GeneratedMediaPackage

_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        "com1",
        "com2",
        "com3",
        "com4",
        "com5",
        "com6",
        "com7",
        "com8",
        "com9",
        "lpt1",
        "lpt2",
        "lpt3",
        "lpt4",
        "lpt5",
        "lpt6",
        "lpt7",
        "lpt8",
        "lpt9",
    }
)
_FILENAME_INVALID_CHARS_PATTERN = re.compile(r'[\*\?"<>\|]+')
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_MIME_EXTENSION_MAP = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/ogg": ".ogg",
    "video/mp4": ".mp4",
}


class ArtifactKind(StrEnum):
    """Allowlisted local runtime artifact categories."""

    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"


class ArtifactWorkspace(CreatorOSModel):
    """Deterministic local workspace for one materialization run."""

    run_id: str
    root_path: Path

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        """Reject blank, unsafe, or traversal-capable run identifiers."""

        normalized_value = value.strip()
        if not normalized_value:
            raise ArtifactPathError(
                "run_id must not be blank",
                code="artifact_workspace_invalid_run_id",
            )
        if (
            normalized_value in {".", ".."}
            or ".." in normalized_value
            or "/" in normalized_value
            or "\\" in normalized_value
            or ":" in normalized_value
            or not _RUN_ID_PATTERN.fullmatch(normalized_value)
        ):
            raise ArtifactPathError(
                "run_id contains unsafe path characters",
                code="artifact_workspace_invalid_run_id",
                details={"run_id": normalized_value},
            )
        return normalized_value

    @field_validator("root_path", mode="before")
    @classmethod
    def normalize_root_path(cls, value: Path | str) -> Path:
        """Normalize the configured artifact root into an absolute path."""

        return Path(value).resolve()

    @property
    def workspace_path(self) -> Path:
        """Return the deterministic root for this run-specific workspace."""

        return self.root_path / self.run_id

    @property
    def images_dir(self) -> Path:
        """Return the local images directory for this workspace."""

        return self.workspace_path / "images"

    @property
    def audio_dir(self) -> Path:
        """Return the local audio directory for this workspace."""

        return self.workspace_path / "audio"

    @property
    def video_dir(self) -> Path:
        """Return the local video directory for this workspace."""

        return self.workspace_path / "video"

    def prepare(self) -> None:
        """Create the deterministic directory layout for this workspace."""

        for directory in (self.images_dir, self.audio_dir, self.video_dir):
            directory.mkdir(parents=True, exist_ok=True)


class MaterializedArtifact(CreatorOSModel):
    """Typed local artifact reference produced by runtime materialization."""

    artifact_id: str
    kind: ArtifactKind
    path: Path
    mime_type: str
    size_bytes: int = Field(gt=0)
    source_provider: str
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("artifact_id", "mime_type", "source_provider")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        """Trim and reject blank materialized-artifact text fields."""

        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError(f"{info.field_name} must not be blank")
        return normalized_value

    @field_validator("path", mode="before")
    @classmethod
    def normalize_path(cls, value: Path | str) -> Path:
        """Normalize artifact paths to absolute filesystem paths."""

        return Path(value).resolve()


class MaterializedMediaPackage(CreatorOSModel):
    """Typed aggregate of all local files created from one generated-media package."""

    workspace: ArtifactWorkspace
    thumbnail: MaterializedArtifact | None = None
    narration: MaterializedArtifact | None = None
    background_music: MaterializedArtifact | None = None
    sound_effects: tuple[MaterializedArtifact, ...] = Field(default_factory=tuple)
    scene_images: tuple[MaterializedArtifact, ...] = Field(default_factory=tuple)
    scene_videos: tuple[MaterializedArtifact, ...] = Field(default_factory=tuple)


def _artifact_kind_from_asset(asset: GeneratedAsset) -> ArtifactKind:
    """Return the local artifact kind for one generated asset reference."""

    asset_type = asset.asset_type.value
    if asset_type == "image":
        return ArtifactKind.IMAGE
    if asset_type in {"audio", "narration"}:
        return ArtifactKind.AUDIO
    if asset_type == "video":
        return ArtifactKind.VIDEO
    raise ArtifactPathError(
        "generated asset type is not supported for local materialization",
        code="artifact_kind_unsupported",
        details={"asset_type": asset_type},
    )


def _filename_base_from_logical_name(logical_name: str) -> str:
    """Normalize one caller-supplied logical artifact name into a safe basename."""

    normalized_value = logical_name.strip()
    if not normalized_value:
        raise ArtifactPathError(
            "logical_name must not be blank",
            code="artifact_filename_invalid",
        )
    if (
        normalized_value in {".", ".."}
        or ".." in normalized_value
        or "/" in normalized_value
        or "\\" in normalized_value
        or ":" in normalized_value
    ):
        raise ArtifactPathError(
            "logical_name contains unsafe path characters",
            code="artifact_filename_invalid",
            details={"logical_name": normalized_value},
        )

    sanitized_value = _FILENAME_INVALID_CHARS_PATTERN.sub("_", normalized_value)
    sanitized_value = re.sub(r"\s+", "_", sanitized_value)
    sanitized_value = re.sub(r"[^0-9A-Za-z._-]+", "_", sanitized_value)
    sanitized_value = re.sub(r"_+", "_", sanitized_value).strip(" ._")
    if not sanitized_value:
        raise ArtifactPathError(
            "logical_name did not produce a usable filename",
            code="artifact_filename_invalid",
            details={"logical_name": normalized_value},
        )
    if sanitized_value.lower() in _WINDOWS_RESERVED_NAMES:
        raise ArtifactPathError(
            "logical_name resolves to a reserved Windows filename",
            code="artifact_filename_invalid",
            details={"logical_name": normalized_value},
        )
    return sanitized_value


def build_safe_filename(*, logical_name: str, mime_type: str) -> str:
    """Build one deterministic safe filename from a logical name and allowed MIME type."""

    extension = _MIME_EXTENSION_MAP.get(mime_type.strip().lower())
    if extension is None:
        raise ArtifactPathError(
            "mime_type is not supported for local artifact materialization",
            code="artifact_mime_type_unsupported",
            details={"mime_type": mime_type.strip().lower()},
        )
    return f"{_filename_base_from_logical_name(logical_name)}{extension}"


class ArtifactMaterializationService:
    """Materialize supported generated-media payloads into a safe local workspace."""

    def __init__(self, settings: Settings) -> None:
        if not isinstance(settings, Settings):
            raise CreatorOSValidationError(
                "settings must be a Settings instance",
                code="service_invalid_dependency",
                details={"dependency": "settings"},
            )
        self.settings = settings
        self.logger = get_logger("services.artifact_materialization")

    def create_workspace(self, *, run_id: str) -> ArtifactWorkspace:
        """Create one validated workspace bound to the configured artifact root."""

        return ArtifactWorkspace(run_id=run_id, root_path=self.settings.artifact_root)

    def materialize_image(
        self,
        image: GeneratedImage,
        *,
        workspace: ArtifactWorkspace,
        logical_name: str,
    ) -> MaterializedArtifact:
        """Materialize one generated image payload into the workspace images directory."""

        return self._materialize_generated_media(
            media=image,
            workspace=workspace,
            logical_name=logical_name,
        )

    def materialize_audio(
        self,
        audio: GeneratedAudio,
        *,
        workspace: ArtifactWorkspace,
        logical_name: str,
    ) -> MaterializedArtifact:
        """Materialize one generated audio payload into the workspace audio directory."""

        return self._materialize_generated_media(
            media=audio,
            workspace=workspace,
            logical_name=logical_name,
        )

    def materialize_video(
        self,
        video: GeneratedVideo,
        *,
        workspace: ArtifactWorkspace,
        logical_name: str,
    ) -> MaterializedArtifact:
        """Materialize one generated video payload into the workspace video directory."""

        return self._materialize_generated_media(
            media=video,
            workspace=workspace,
            logical_name=logical_name,
        )

    def materialize_package(
        self,
        package: GeneratedMediaPackage,
        *,
        run_id: str,
    ) -> MaterializedMediaPackage:
        """Materialize one generated-media package into a deterministic local workspace."""

        workspace = self.create_workspace(run_id=run_id)
        workspace.prepare()
        created_paths: list[Path] = []

        try:
            thumbnail = None
            if package.thumbnail is not None:
                thumbnail = self.materialize_image(
                    package.thumbnail,
                    workspace=workspace,
                    logical_name="thumbnail",
                )
                created_paths.append(thumbnail.path)

            narration = None
            if package.narration is not None:
                narration = self.materialize_audio(
                    package.narration,
                    workspace=workspace,
                    logical_name="narration",
                )
                created_paths.append(narration.path)

            background_music = None
            if package.background_music is not None:
                background_music = self.materialize_audio(
                    package.background_music,
                    workspace=workspace,
                    logical_name="background_music",
                )
                created_paths.append(background_music.path)

            sound_effects: list[MaterializedArtifact] = []
            for index, sound_effect in enumerate(package.sound_effects, start=1):
                materialized_sound_effect = self.materialize_audio(
                    sound_effect,
                    workspace=workspace,
                    logical_name=f"sfx_{index:03d}",
                )
                sound_effects.append(materialized_sound_effect)
                created_paths.append(materialized_sound_effect.path)

            scene_images: list[MaterializedArtifact] = []
            for index, image in enumerate(package.scene_images, start=1):
                materialized_image = self.materialize_image(
                    image,
                    workspace=workspace,
                    logical_name=f"scene_{index:03d}",
                )
                scene_images.append(materialized_image)
                created_paths.append(materialized_image.path)

            scene_videos: list[MaterializedArtifact] = []
            for index, video in enumerate(package.scene_videos, start=1):
                materialized_video = self.materialize_video(
                    video,
                    workspace=workspace,
                    logical_name=f"clip_{index:03d}",
                )
                scene_videos.append(materialized_video)
                created_paths.append(materialized_video.path)
        except Exception:
            self._cleanup_created_paths(created_paths)
            raise

        return MaterializedMediaPackage(
            workspace=workspace,
            thumbnail=thumbnail,
            narration=narration,
            background_music=background_music,
            sound_effects=tuple(sound_effects),
            scene_images=tuple(scene_images),
            scene_videos=tuple(scene_videos),
        )

    def _materialize_generated_media(
        self,
        *,
        media: GeneratedImage | GeneratedAudio | GeneratedVideo,
        workspace: ArtifactWorkspace,
        logical_name: str,
    ) -> MaterializedArtifact:
        """Materialize one supported generated media result into the proper workspace directory."""

        payload_bytes = media.payload_bytes
        if payload_bytes is None:
            raise ArtifactPayloadError(
                "generated media does not contain a materializable payload",
                code="artifact_payload_missing",
                details={
                    "provider_name": media.provider_name,
                    "artifact_type": media.artifact.asset_type.value,
                },
            )
        if not payload_bytes:
            raise ArtifactPayloadError(
                "generated media payload is empty",
                code="artifact_payload_empty",
                details={
                    "provider_name": media.provider_name,
                    "artifact_type": media.artifact.asset_type.value,
                },
            )

        workspace.prepare()
        kind = _artifact_kind_from_asset(media.artifact)
        filename = build_safe_filename(logical_name=logical_name, mime_type=media.mime_type)
        destination_dir = self._destination_dir_for_kind(workspace, kind)
        destination_path = self._ensure_safe_destination_path(destination_dir, filename)
        self._atomic_write_bytes(destination_path, payload_bytes)

        materialized_artifact = MaterializedArtifact(
            artifact_id=media.artifact.id,
            kind=kind,
            path=destination_path,
            mime_type=media.mime_type,
            size_bytes=len(payload_bytes),
            source_provider=media.provider_name,
            metadata={"request_id": media.request_id, **dict(media.metadata)},
        )
        self.logger.info(
            "artifact_materialized",
            run_id=workspace.run_id,
            artifact_kind=materialized_artifact.kind.value,
            filename=materialized_artifact.path.name,
            size_bytes=materialized_artifact.size_bytes,
            source_provider=materialized_artifact.source_provider,
            success=True,
        )
        return materialized_artifact

    @staticmethod
    def _destination_dir_for_kind(workspace: ArtifactWorkspace, kind: ArtifactKind) -> Path:
        """Return the destination directory for one local artifact kind."""

        if kind is ArtifactKind.IMAGE:
            return workspace.images_dir
        if kind is ArtifactKind.AUDIO:
            return workspace.audio_dir
        if kind is ArtifactKind.VIDEO:
            return workspace.video_dir
        raise ArtifactPathError(
            "artifact kind is not supported",
            code="artifact_kind_unsupported",
            details={"artifact_kind": kind.value},
        )

    @staticmethod
    def _ensure_safe_destination_path(destination_dir: Path, filename: str) -> Path:
        """Return one validated destination path inside the intended workspace directory."""

        destination_dir.mkdir(parents=True, exist_ok=True)
        destination_path = (destination_dir / filename).resolve()
        if not destination_path.is_relative_to(destination_dir.resolve()):
            raise ArtifactPathError(
                "artifact destination path escaped the workspace directory",
                code="artifact_destination_outside_workspace",
                details={"filename": filename},
            )
        return destination_path

    @staticmethod
    def _atomic_write_bytes(destination_path: Path, payload_bytes: bytes) -> None:
        """Write payload bytes atomically without silently overwriting final artifacts."""

        if destination_path.exists():
            raise ArtifactAlreadyExistsError(
                f"artifact already exists at '{destination_path.name}'",
                code="artifact_already_exists",
                details={"filename": destination_path.name},
            )

        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                delete=False,
                dir=destination_path.parent,
                prefix=".artifact_tmp_",
                suffix=".part",
            ) as temporary_file:
                temp_path = Path(temporary_file.name)
                temporary_file.write(payload_bytes)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            os.replace(temp_path, destination_path)
        except Exception:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _cleanup_created_paths(created_paths: list[Path]) -> None:
        """Remove only the new final artifact files created during one failed package operation."""

        for created_path in reversed(created_paths):
            created_path.unlink(missing_ok=True)


def create_artifact_materialization_service(
    *,
    settings: Settings | None = None,
) -> ArtifactMaterializationService:
    """Create one artifact materialization service using the current settings."""

    resolved_settings = get_settings() if settings is None else settings
    return ArtifactMaterializationService(resolved_settings)


__all__ = [
    "ArtifactKind",
    "ArtifactMaterializationService",
    "ArtifactWorkspace",
    "MaterializedArtifact",
    "MaterializedMediaPackage",
    "build_safe_filename",
    "create_artifact_materialization_service",
]
