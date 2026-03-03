"""Unit tests for configuration management."""

import os
import pytest
from unittest.mock import patch

# Add app directory to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import config
from config import Settings, get_settings, setup_logging, validate_config


class TestSettings:
    """Tests for Settings class."""
    
    def test_default_values(self):
        """Test that default values are correctly set."""
        settings = Settings()
        
        assert settings.service_host == "0.0.0.0"
        assert settings.service_port == 8001
        assert settings.use_gpu_bool is False
        assert settings.model_dir == "./models"
        assert settings.min_confidence_default == 0.5
        assert settings.max_image_size_mb == 10
        assert settings.request_timeout_seconds == 30
        assert settings.log_level == "INFO"
    
    def test_env_var_aliases(self):
        """Test that environment variable aliases work correctly."""
        with patch.dict(os.environ, {
            "SERVICE_HOST": "127.0.0.1",
            "SERVICE_PORT": "8080",
            "PADDLEOCR_USE_GPU": "true",
            "PADDLEOCR_MODEL_DIR": "/custom/models",
            "PADDLEOCR_MIN_CONFIDENCE_DEFAULT": "0.75",
            "PADDLEOCR_MAX_IMAGE_SIZE_MB": "20",
            "PADDLEOCR_REQUEST_TIMEOUT_SECONDS": "60",
            "LOG_LEVEL": "DEBUG"
        }):
            settings = Settings()
            
            assert settings.service_host == "127.0.0.1"
            assert settings.service_port == 8080
            assert settings.use_gpu_bool is True
            assert settings.model_dir == "/custom/models"
            assert settings.min_confidence_default == 0.75
            assert settings.max_image_size_mb == 20
            assert settings.request_timeout_seconds == 60
            assert settings.log_level == "DEBUG"
    
    def test_use_gpu_boolean_string_validation(self):
        """Test validation of PADDLEOCR_USE_GPU boolean strings."""
        valid_true_values = ["true", "True", "TRUE", "1", "yes", "Yes", "YES"]
        valid_false_values = ["false", "False", "FALSE", "0", "no", "No", "NO"]
        
        for val in valid_true_values:
            with patch.dict(os.environ, {"PADDLEOCR_USE_GPU": val}):
                settings = Settings()
                assert settings.use_gpu_bool is True, f"Failed for value: {val}"
        
        for val in valid_false_values:
            with patch.dict(os.environ, {"PADDLEOCR_USE_GPU": val}):
                settings = Settings()
                assert settings.use_gpu_bool is False, f"Failed for value: {val}"
    
    def test_use_gpu_invalid_boolean_string(self):
        """Test that invalid boolean strings raise ValueError."""
        invalid_values = ["invalid", "2", "maybe", "on", "off"]
        
        for val in invalid_values:
            with patch.dict(os.environ, {"PADDLEOCR_USE_GPU": val}, clear=True):
                with pytest.raises(ValueError) as exc_info:
                    Settings()
                assert "PADDLEOCR_USE_GPU must be a valid boolean string" in str(exc_info.value)
    
    def test_min_confidence_default_validation(self):
        """Test validation of min_confidence_default."""
        # Valid values
        with patch.dict(os.environ, {"PADDLEOCR_MIN_CONFIDENCE_DEFAULT": "0.0"}):
            settings = Settings()
            assert settings.min_confidence_default == 0.0
        
        with patch.dict(os.environ, {"PADDLEOCR_MIN_CONFIDENCE_DEFAULT": "1.0"}):
            settings = Settings()
            assert settings.min_confidence_default == 1.0
        
        # Invalid values
        with patch.dict(os.environ, {"PADDLEOCR_MIN_CONFIDENCE_DEFAULT": "-0.1"}):
            with pytest.raises(ValueError) as exc_info:
                Settings()
            assert "PADDLEOCR_MIN_CONFIDENCE_DEFAULT must be between 0.0 and 1.0" in str(exc_info.value)
        
        with patch.dict(os.environ, {"PADDLEOCR_MIN_CONFIDENCE_DEFAULT": "1.1"}):
            with pytest.raises(ValueError) as exc_info:
                Settings()
            assert "PADDLEOCR_MIN_CONFIDENCE_DEFAULT must be between 0.0 and 1.0" in str(exc_info.value)
    
    def test_max_image_size_mb_validation(self):
        """Test validation of max_image_size_mb."""
        # Valid values
        with patch.dict(os.environ, {"PADDLEOCR_MAX_IMAGE_SIZE_MB": "1"}):
            settings = Settings()
            assert settings.max_image_size_mb == 1
        
        with patch.dict(os.environ, {"PADDLEOCR_MAX_IMAGE_SIZE_MB": "100"}):
            settings = Settings()
            assert settings.max_image_size_mb == 100
        
        # Invalid values
        with patch.dict(os.environ, {"PADDLEOCR_MAX_IMAGE_SIZE_MB": "0"}):
            with pytest.raises(ValueError) as exc_info:
                Settings()
            assert "PADDLEOCR_MAX_IMAGE_SIZE_MB must be a positive integer" in str(exc_info.value)
        
        with patch.dict(os.environ, {"PADDLEOCR_MAX_IMAGE_SIZE_MB": "-5"}):
            with pytest.raises(ValueError) as exc_info:
                Settings()
            assert "PADDLEOCR_MAX_IMAGE_SIZE_MB must be a positive integer" in str(exc_info.value)
    
    def test_request_timeout_seconds_validation(self):
        """Test validation of request_timeout_seconds."""
        # Valid values
        with patch.dict(os.environ, {"PADDLEOCR_REQUEST_TIMEOUT_SECONDS": "1"}):
            settings = Settings()
            assert settings.request_timeout_seconds == 1
        
        with patch.dict(os.environ, {"PADDLEOCR_REQUEST_TIMEOUT_SECONDS": "300"}):
            settings = Settings()
            assert settings.request_timeout_seconds == 300
        
        # Invalid values
        with patch.dict(os.environ, {"PADDLEOCR_REQUEST_TIMEOUT_SECONDS": "0"}):
            with pytest.raises(ValueError) as exc_info:
                Settings()
            assert "PADDLEOCR_REQUEST_TIMEOUT_SECONDS must be a positive integer" in str(exc_info.value)
        
        with patch.dict(os.environ, {"PADDLEOCR_REQUEST_TIMEOUT_SECONDS": "-10"}):
            with pytest.raises(ValueError) as exc_info:
                Settings()
            assert "PADDLEOCR_REQUEST_TIMEOUT_SECONDS must be a positive integer" in str(exc_info.value)
    
    def test_service_port_validation(self):
        """Test validation of service_port."""
        # Valid values
        with patch.dict(os.environ, {"SERVICE_PORT": "1"}):
            settings = Settings()
            assert settings.service_port == 1
        
        with patch.dict(os.environ, {"SERVICE_PORT": "65535"}):
            settings = Settings()
            assert settings.service_port == 65535
        
        # Invalid values
        with patch.dict(os.environ, {"SERVICE_PORT": "0"}):
            with pytest.raises(ValueError) as exc_info:
                Settings()
            assert "SERVICE_PORT must be a valid port number" in str(exc_info.value)
        
        with patch.dict(os.environ, {"SERVICE_PORT": "65536"}):
            with pytest.raises(ValueError) as exc_info:
                Settings()
            assert "SERVICE_PORT must be a valid port number" in str(exc_info.value)
        
        with patch.dict(os.environ, {"SERVICE_PORT": "-1"}):
            with pytest.raises(ValueError) as exc_info:
                Settings()
            assert "SERVICE_PORT must be a valid port number" in str(exc_info.value)
    
    def test_log_level_validation(self):
        """Test validation of LOG_LEVEL."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        
        for level in valid_levels:
            with patch.dict(os.environ, {"LOG_LEVEL": level}):
                settings = Settings()
                assert settings.log_level == level
        
        # Test case insensitivity
        with patch.dict(os.environ, {"LOG_LEVEL": "debug"}):
            settings = Settings()
            assert settings.log_level == "DEBUG"
        
        with patch.dict(os.environ, {"LOG_LEVEL": "info"}):
            settings = Settings()
            assert settings.log_level == "INFO"
        
        # Invalid level
        with patch.dict(os.environ, {"LOG_LEVEL": "TRACE"}):
            with pytest.raises(ValueError) as exc_info:
                Settings()
            assert "LOG_LEVEL must be one of" in str(exc_info.value)
    
    def test_logging_config(self):
        """Test logging configuration."""
        settings = Settings()
        config = settings.logging_config
        
        assert "version" in config
        assert config["version"] == 1
        assert "formatters" in config
        assert "handlers" in config
        assert "root" in config
        assert "console" in config["handlers"]
        assert config["handlers"]["console"]["level"] == settings.log_level


class TestSetupLogging:
    """Tests for setup_logging function."""
    
    def test_setup_logging(self):
        """Test that logging is configured correctly."""
        # This test just verifies the function doesn't raise an exception
        # Actual logging output is not tested as it would interfere with test output
        try:
            setup_logging()
        except Exception as e:
            pytest.fail(f"setup_logging raised exception: {e}")


class TestValidateConfig:
    """Tests for validate_config function."""
    
    def test_validate_config_cpu_mode(self):
        """Test configuration validation in CPU mode."""
        with patch.dict(os.environ, {"PADDLEOCR_USE_GPU": "false"}):
            try:
                result = validate_config()
                assert result is True
            except Exception as e:
                # May fail if paddle is not installed, which is expected
                # The important thing is that it doesn't fail due to config validation
                if "GPU enabled but PaddlePaddle not compiled with CUDA" not in str(e):
                    pytest.fail(f"validate_config raised unexpected exception: {e}")
    
    def test_validate_config_creates_model_dir(self):
        """Test that model directory is created if it doesn't exist."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = os.path.join(tmpdir, "test_models")
            assert not os.path.exists(model_dir)
            
            # Temporarily change the model_dir in settings
            original_model_dir = config.settings.model_dir
            config.settings.model_dir = model_dir
            
            try:
                result = config.validate_config()
                assert result is True
                assert os.path.exists(model_dir)
            except Exception as e:
                if "GPU enabled but PaddlePaddle not compiled with CUDA" not in str(e):
                    pytest.fail(f"validate_config raised unexpected exception: {e}")
            finally:
                # Restore original model_dir
                config.settings.model_dir = original_model_dir


class TestGetSettings:
    """Tests for get_settings function."""
    
    def test_get_settings_returns_settings_instance(self):
        """Test that get_settings returns a Settings instance."""
        settings = get_settings()
        assert isinstance(settings, Settings)
