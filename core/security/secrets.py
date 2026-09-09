"""Gayatri AI — Secure secrets management.

Stores API keys and other sensitive data using Windows DPAPI.
Keys are encrypted at rest and never appear in plaintext on disk
or in logs.

Falls back gracefully on non-Windows platforms (development/testing).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from core.config import SETTINGS_PATH

logger = logging.getLogger("gayatri.security.secrets")


class SecretsVault:
    """Secure storage for API keys and secrets.

    Windows: Uses DPAPI (CryptProtectData/CryptUnprotectData) via ctypes.
    Non-Windows: Falls back to base64 (development only — NOT secure).

    Keys are NEVER:
    - Stored in plaintext
    - Logged
    - Exposed in error messages
    - Included in telemetry
    """

    def __init__(self, vault_path: str | Path | None = None):
        self.vault_path = Path(vault_path) if vault_path else SETTINGS_PATH.parent / "secrets.enc"
        self._is_windows = os.name == "nt"

    def _encrypt(self, plaintext: str) -> bytes:
        """Encrypt a string using platform-appropriate method."""
        if self._is_windows:
            return self._dpapi_encrypt(plaintext)
        else:
            # Development fallback — NOT secure
            logger.warning("DPAPI unavailable — using base64 encoding (dev only)")
            import base64
            return base64.b64encode(plaintext.encode("utf-8"))

    def _decrypt(self, ciphertext: bytes) -> str:
        """Decrypt bytes using platform-appropriate method."""
        if self._is_windows:
            return self._dpapi_decrypt(ciphertext)
        else:
            import base64
            return base64.b64decode(ciphertext).decode("utf-8")

    def _dpapi_encrypt(self, plaintext: str) -> bytes:
        """Encrypt using Windows DPAPI (current user scope)."""
        import ctypes
        from ctypes import wintypes

        # Prepare input
        plaintext_bytes = plaintext.encode("utf-8")
        data_in = plaintext_bytes

        # Call CryptProtectData
        CRYPTPROTECT_UI_FORBIDDEN = 0x01

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_byte)),
            ]

        blob_in = DATA_BLOB(cbData=len(data_in))
        buf_in = (ctypes.c_byte * len(data_in))(*data_in)
        blob_in.pbData = ctypes.cast(buf_in, ctypes.POINTER(ctypes.c_byte))

        blob_out = DATA_BLOB()

        result = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in),
            None,  # description
            None,  # optional entropy
            None,  # reserved
            None,  # prompt struct
            CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(blob_out),
        )

        if not result:
            raise RuntimeError("DPAPI encryption failed")

        # Extract encrypted bytes
        encrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)

        # Free the blob memory
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)

        return encrypted

    def _dpapi_decrypt(self, ciphertext: bytes) -> str:
        """Decrypt using Windows DPAPI."""
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_byte)),
            ]

        blob_in = DATA_BLOB(cbData=len(ciphertext))
        buf_in = (ctypes.c_byte * len(ciphertext))(*ciphertext)
        blob_in.pbData = ctypes.cast(buf_in, ctypes.POINTER(ctypes.c_byte))

        blob_out = DATA_BLOB()

        result = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in),
            None,  # description out
            None,  # optional entropy
            None,  # reserved
            None,  # prompt struct
            0,     # flags
            ctypes.byref(blob_out),
        )

        if not result:
            raise RuntimeError("DPAPI decryption failed — data may be corrupted or from another user")

        decrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)

        return decrypted.decode("utf-8")

    def store_key(self, provider_key: str, api_key: str) -> None:
        """Store an API key securely.

        Args:
            provider_key: Machine key (e.g. "openai", "anthropic")
            api_key: The API key to store
        """
        # Load existing vault
        vault = self._load_vault()
        vault[provider_key] = api_key
        self._save_vault(vault)
        logger.info(f"Key stored: {provider_key}")

    def retrieve_key(self, provider_key: str) -> str | None:
        """Retrieve a stored API key.

        Args:
            provider_key: Machine key (e.g. "openai", "anthropic")

        Returns:
            The API key, or None if not found
        """
        vault = self._load_vault()
        key = vault.get(provider_key)
        if key:
            logger.debug(f"Key retrieved: {provider_key}")
        return key

    def delete_key(self, provider_key: str) -> None:
        """Delete a stored API key."""
        vault = self._load_vault()
        if provider_key in vault:
            del vault[provider_key]
            self._save_vault(vault)
            logger.info(f"Key deleted: {provider_key}")

    def list_keys(self) -> list[str]:
        """List provider keys that have stored secrets (not the keys themselves)."""
        vault = self._load_vault()
        return list(vault.keys())

    def has_key(self, provider_key: str) -> bool:
        """Check if a key is stored."""
        return provider_key in self._load_vault()

    def _load_vault(self) -> dict[str, str]:
        """Load the vault from disk, decrypting each entry."""
        if not self.vault_path.exists():
            return {}

        try:
            with open(self.vault_path, "rb") as f:
                encrypted_data = json.loads(f.read().decode("utf-8"))

            vault = {}
            for key, encrypted_b64 in encrypted_data.items():
                try:
                    import base64
                    encrypted = base64.b64decode(encrypted_b64)
                    vault[key] = self._decrypt(encrypted)
                except Exception as exc:
                    logger.error(f"Failed to decrypt key {key}: {exc}")
                    # Skip corrupted entries
                    continue
            return vault
        except Exception as exc:
            logger.error(f"Failed to load vault: {exc}")
            return {}

    def _save_vault(self, vault: dict[str, str]) -> None:
        """Save the vault to disk, encrypting each entry."""
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)

        encrypted_data = {}
        for key, plaintext in vault.items():
            try:
                encrypted = self._encrypt(plaintext)
                import base64
                encrypted_data[key] = base64.b64encode(encrypted).decode("utf-8")
            except Exception as exc:
                logger.error(f"Failed to encrypt key {key}: {exc}")
                raise

        # Write atomically
        tmp_path = self.vault_path.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            json.dump(encrypted_data, f, indent=2)
        tmp_path.replace(self.vault_path)

        # Set restrictive permissions (non-Windows fallback)
        if not self._is_windows:
            try:
                os.chmod(self.vault_path, 0o600)
            except Exception:
                pass


# Global vault instance
_vault: SecretsVault | None = None


def get_vault() -> SecretsVault:
    """Get the global secrets vault."""
    global _vault
    if _vault is None:
        _vault = SecretsVault()
    return _vault
