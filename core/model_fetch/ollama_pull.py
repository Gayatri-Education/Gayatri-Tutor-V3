"""Gayatri AI — Ollama registry model puller.

Downloads GGUF models from registry.ollama.ai WITHOUT needing Ollama installed.
Handles manifest parsing, resumable blob downloads, and sha256 verification.

Confirmed model: DBERT/DBERT_AI:latest (531 MB, 32K ctx, GGUF)
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger("gayatri.model_fetch")

# Ollama registry base URL
OLLAMA_REGISTRY = "https://registry.ollama.ai"

# Confirmed model coordinates
DEFAULT_MODEL_NAMESPACE = "DBERT"
DEFAULT_MODEL_NAME = "DBERT_AI"
DEFAULT_MODEL_TAG = "latest"

# Manifest media types
MEDIA_TYPE_MODEL = "application/vnd.ollama.image.model"
MEDIA_TYPE_SYSTEM = "application/vnd.ollama.image.system"
MEDIA_TYPE_PARAMS = "application/vnd.ollama.image.params"


class OllamaPullError(Exception):
    """Error pulling model from Ollama registry."""
    pass


class ModelManifest:
    """Parsed Ollama manifest."""

    def __init__(self, digest: str, layers: list[dict], config: dict):
        self.digest = digest
        self.layers = layers
        self.config = config

    @property
    def model_blob(self) -> dict | None:
        """The GGUF model layer."""
        for layer in self.layers:
            if layer.get("mediaType") == MEDIA_TYPE_MODEL:
                return layer
        return None

    @property
    def system_blob(self) -> dict | None:
        """The chat template layer."""
        for layer in self.layers:
            if layer.get("mediaType") == MEDIA_TYPE_SYSTEM:
                return layer
        return None

    @property
    def params_blob(self) -> dict | None:
        """The model params layer."""
        for layer in self.layers:
            if layer.get("mediaType") == MEDIA_TYPE_PARAMS:
                return layer
        return None

    @classmethod
    def from_dict(cls, data: dict) -> ModelManifest:
        """Parse from Ollama manifest API response."""
        return cls(
            digest=data.get("config", {}).get("digest", ""),
            layers=data.get("layers", []),
            config=data.get("config", {}),
        )


def _get_manifest(namespace: str, name: str, tag: str) -> ModelManifest:
    """Fetch and parse the Ollama manifest for a model.

    Args:
        namespace: Model namespace (e.g. "DBERT")
        name: Model name (e.g. "DBERT_AI")
        tag: Model tag (e.g. "latest")

    Returns:
        Parsed ModelManifest

    Raises:
        OllamaPullError: If manifest fetch fails
    """
    import httpx

    url = f"{OLLAMA_REGISTRY}/v2/{namespace}/{name}/manifests/{tag}"
    headers = {"Accept": "application/vnd.docker.distribution.manifest.v2+json"}

    logger.info(f"Fetching manifest: {url}")
    response = httpx.get(url, headers=headers, timeout=30.0, follow_redirects=True)

    if response.status_code != 200:
        raise OllamaPullError(
            f"Failed to fetch manifest: HTTP {response.status_code} — {response.text[:300]}"
        )

    try:
        data = response.json()
        manifest = ModelManifest.from_dict(data)
        logger.info(
            f"Manifest: {len(manifest.layers)} layers "
            f"(model={manifest.model_blob is not None}, "
            f"system={manifest.system_blob is not None}, "
            f"params={manifest.params_blob is not None})"
        )
        return manifest
    except Exception as exc:
        raise OllamaPullError(f"Failed to parse manifest: {exc}") from exc


def _get_blob_url(namespace: str, name: str, digest: str) -> str:
    """Build the download URL for a blob."""
    return f"{OLLAMA_REGISTRY}/v2/{namespace}/{name}/blobs/{digest}"


def _verify_sha256(filepath: Path, expected_digest: str) -> bool:
    """Verify a file's sha256 digest.

    Args:
        filepath: Path to file
        expected_digest: Expected sha256 digest (with or without 'sha256:' prefix)

    Returns:
        True if digest matches
    """
    expected = expected_digest.replace("sha256:", "")
    h = hashlib.sha256()

    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)

    actual = h.hexdigest()
    matches = actual == expected

    if matches:
        logger.info(f"Digest verified: {filepath.name} ({filepath.stat().st_size / 1024 / 1024:.1f} MB)")
    else:
        logger.error(f"Digest mismatch: expected {expected[:16]}..., got {actual[:16]}...")

    return matches


def _download_blob(
    url: str,
    dest: Path,
    expected_digest: str,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> None:
    """Download a blob with resumable Range requests and digest verification.

    Args:
        url: Download URL
        dest: Destination file path
        expected_digest: Expected sha256 digest
        progress_callback: Optional callback(label, downloaded, total)
    """
    import httpx

    downloaded = 0
    headers = {}

    # Check for partial download
    if dest.exists():
        downloaded = dest.stat().st_size
        if downloaded > 0:
            headers["Range"] = f"bytes={downloaded}-"
            logger.info(f"Resuming download: {downloaded / 1024 / 1024:.1f} MB already downloaded")

    try:
        with httpx.stream("GET", url, headers=headers, timeout=300.0, follow_redirects=True) as response:
            if response.status_code == 200:
                # Full download
                mode = "wb"
                downloaded = 0
                total = int(response.headers.get("content-length", 0))
                logger.info(f"Downloading: {url.split('/')[-1][:40]} ({total / 1024 / 1024:.1f} MB)")
            elif response.status_code == 206:
                # Resume accepted
                mode = "ab"
                content_range = response.headers.get("content-range", "")
                total_str = content_range.split("/")[-1] if "/" in content_range else "0"
                total = int(total_str) if total_str.isdigit() else 0
                logger.info(f"Resuming from {downloaded / 1024 / 1024:.1f} MB")
            else:
                raise OllamaPullError(f"HTTP {response.status_code}: {response.text[:200]}")

            with open(dest, mode) as f:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback("model", downloaded, total)

    except httpx.HTTPStatusError as exc:
        raise OllamaPullError(f"Download failed: HTTP {exc.response.status_code}") from exc
    except Exception as exc:
        raise OllamaPullError(f"Download failed: {exc}") from exc

    logger.info(f"Download complete: {downloaded / 1024 / 1024:.1f} MB")

    # Verify digest
    if not _verify_sha256(dest, expected_digest):
        dest.unlink(missing_ok=True)
        raise OllamaPullError(f"Digest verification failed for {dest.name}")


def pull_model(
    namespace: str = DEFAULT_MODEL_NAMESPACE,
    name: str = DEFAULT_MODEL_NAME,
    tag: str = DEFAULT_MODEL_TAG,
    dest_dir: Path | None = None,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> dict:
    """Pull a model from the Ollama registry.

    Args:
        namespace: Model namespace (e.g. "DBERT")
        name: Model name (e.g. "DBERT_AI")
        tag: Model tag (e.g. "latest")
        dest_dir: Destination directory (default: MODELS_DIR/dbert_ai)
        progress_callback: Optional callback(label, downloaded, total)

    Returns:
        Dict with model info: {namespace, name, tag, path, size_mb, digest}

    Raises:
        OllamaPullError: If any step fails
    """
    from core.config import LOCAL_MODEL_FILE, MODELS_DIR

    dest_dir = dest_dir or MODELS_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Pulling {namespace}/{name}:{tag} -> {dest_dir}")

    # 1. Fetch manifest
    manifest = _get_manifest(namespace, name, tag)

    # 2. Download model blob (GGUF)
    model_blob = manifest.model_blob
    if model_blob is None:
        raise OllamaPullError("No model blob in manifest")

    model_digest = model_blob["digest"]
    model_url = _get_blob_url(namespace, name, model_digest)
    model_path = dest_dir / LOCAL_MODEL_FILE

    def _model_progress(label: str, downloaded: int, total: int):
        if progress_callback:
            progress_callback(label, downloaded, total)

    _download_blob(model_url, model_path, model_digest, _model_progress)

    # 3. Download system blob (chat template) if present
    system_blob = manifest.system_blob
    if system_blob:
        system_digest = system_blob["digest"]
        system_url = _get_blob_url(namespace, name, system_digest)
        system_path = dest_dir / "chat_template.txt"
        _download_blob(system_url, system_path, system_digest)
        logger.info(f"Chat template saved: {system_path}")
    else:
        logger.info("No chat template in manifest (using default)")

    # 4. Download params blob if present
    params_blob = manifest.params_blob
    if params_blob:
        params_digest = params_blob["digest"]
        params_url = _get_blob_url(namespace, name, params_digest)
        params_path = dest_dir / "params.json"
        _download_blob(params_url, params_path, params_digest)
        logger.info(f"Params saved: {params_path}")
    else:
        logger.info("No params in manifest (using defaults)")

    size_mb = model_path.stat().st_size / 1024 / 1024
    logger.info(f"Pull complete: {model_path} ({size_mb:.1f} MB)")

    return {
        "namespace": namespace,
        "name": name,
        "tag": tag,
        "path": str(model_path),
        "size_mb": round(size_mb, 1),
        "digest": model_digest,
        "has_chat_template": system_blob is not None,
        "has_params": params_blob is not None,
    }


def check_model_available(namespace: str = DEFAULT_MODEL_NAMESPACE,
                          name: str = DEFAULT_MODEL_NAME,
                          tag: str = DEFAULT_MODEL_TAG) -> dict:
    """Check if a model is available without downloading.

    Returns:
        Dict with availability info: {available, size_mb, layers, ...}
    """
    try:
        manifest = _get_manifest(namespace, name, tag)
        model_blob = manifest.model_blob

        if model_blob is None:
            return {"available": False, "reason": "No model blob in manifest"}

        size_str = model_blob.get("size", "0")
        try:
            size_bytes = int(size_str)
            size_mb = size_bytes / 1024 / 1024
        except (ValueError, TypeError):
            size_mb = 0

        return {
            "available": True,
            "namespace": namespace,
            "name": name,
            "tag": tag,
            "size_mb": round(size_mb, 1),
            "layers": len(manifest.layers),
            "digest": model_blob["digest"],
        }
    except Exception as exc:
        return {
            "available": False,
            "reason": str(exc)[:200],
        }
