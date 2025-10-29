"""
Smoke tests for command-line interface.

These tests verify that the CLI module structure is correct.
Note: Full CLI testing requires D-Bus, so we test structure only.
"""

# pylint: disable=import-outside-toplevel,import-error,too-few-public-methods

from pathlib import Path


class TestCLIStructure:
    """Test CLI module structure."""

    def test_main_module_file_exists(self):
        """Test that systemd_monitor.py module file exists."""
        import systemd_monitor

        main_path = Path(systemd_monitor.__file__).parent / "systemd_monitor.py"
        assert main_path.exists(), f"systemd_monitor.py not found: {main_path}"
        assert main_path.is_file()

    def test_console_script_entry_point(self):
        """Test that package has console script entry point configured."""
        try:
            import tomllib  # Python 3.11+
        except ImportError:
            import tomli as tomllib  # Fallback for older Python

        # Read pyproject.toml to verify console script is configured
        pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
        if pyproject_path.exists():
            with open(pyproject_path, "rb") as f:
                config = tomllib.load(f)

            scripts = config.get("project", {}).get("scripts", {})
            assert "systemd-monitor" in scripts
            assert "systemd_monitor.systemd_monitor:main" in scripts["systemd-monitor"]

    def test_config_module_has_parse_arguments(self):
        """Test that config module has argument parsing."""
        from systemd_monitor import config

        assert hasattr(config, "parse_arguments")
        assert callable(config.parse_arguments)

    def test_version_available(self):
        """Test that version is accessible for --version flag."""
        import systemd_monitor

        assert hasattr(systemd_monitor, "__version__")
        version = systemd_monitor.__version__
        assert isinstance(version, str)
        assert len(version) > 0


class TestPackageEntryPoint:
    """Test that package entry point is configured."""

    def test_systemd_monitor_module_has_main(self):
        """Test that systemd_monitor.py file contains a main() function."""
        import systemd_monitor

        # Read the file content without importing (avoids D-Bus connection)
        main_path = Path(systemd_monitor.__file__).parent / "systemd_monitor.py"
        content = main_path.read_text()

        # Check that main() function is defined
        assert "def main()" in content
        assert '__name__ == "__main__"' in content or "__name__=='__main__'" in content
