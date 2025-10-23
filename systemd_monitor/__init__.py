"""
systemd_monitor package.

Provides tools for monitoring systemd services via D-Bus.
"""

# Version is automatically generated from git tags by setuptools_scm
try:
    from systemd_monitor._version import version as __version__
except ImportError:
    # Fallback for development without installation
    # Version will be derived from git tags on next install
    try:
        from setuptools_scm import get_version

        __version__ = get_version(root="..", relative_to=__file__)
    except Exception:  # pylint: disable=broad-exception-caught
        __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
