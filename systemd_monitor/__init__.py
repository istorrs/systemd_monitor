"""
systemd_monitor package.

Provides tools for monitoring systemd services via D-Bus.
"""

# Version is managed in pyproject.toml
# Use importlib.metadata to read the installed package version
try:
    from importlib.metadata import version

    __version__ = version("systemd_monitor")
except Exception:  # pylint: disable=broad-exception-caught
    # Fallback for development without installation
    # Catches ImportError, PackageNotFoundError, and any other edge cases
    __version__ = "0.1.0-dev"

__all__ = ["__version__"]
