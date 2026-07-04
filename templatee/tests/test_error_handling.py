"""
Unit tests for enhanced error handling and logging functionality.

Tests comprehensive error handling, structured logging, and diagnostic information
across all pricing engine components.
"""

import pytest
import json
import time
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
from fastapi import HTTPException

# Import error handling components
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from error_handling import (
    ErrorSeverity, ErrorCategory, ErrorContext, DiagnosticInfo,
    PricingEngineError, ValidationError, CalculationError, 
    NumericalInstabilityError, ExternalAPIError, SystemError,
    ErrorHandler, create_error_context, handle_api_error,
    configure_logging
)


class TestErrorTypes:
    """Test error type definitions and functionality"""
    
    def test_error_severity_enum(self):
        """Test error severity enumeration"""
        assert ErrorSeverity.LOW.value == "low"
        assert ErrorSeverity.MEDIUM.value == "medium"
        assert ErrorSeverity.HIGH.value == "high"
        assert ErrorSeverity.CRITICAL.value == "critical"
    
    def test_error_category_enum(self):
        """Test error category enumeration"""
        assert ErrorCategory.VALIDATION.value == "validation"
        assert ErrorCategory.CALCULATION.value == "calculation"
        assert ErrorCategory.NETWORK.value == "network"
        assert ErrorCategory.SYSTEM.value == "system"
        assert ErrorCategory.EXTERNAL_API.value == "external_api"
        assert ErrorCategory.CONFIGURATION.value == "configuration"
    
    def test_error_context_creation(self):
        """Test error context creation and serialization"""
        context = ErrorContext(
            timestamp=datetime.now(timezone.utc),
            request_id="test-123",
            user_id="user-456",
            endpoint="/test/endpoint",
            parameters={"param1": "value1"},
            system_info={"version": "1.0.0"}
        )
        
        assert context.request_id == "test-123"
        assert context.user_id == "user-456"
        assert context.endpoint == "/test/endpoint"
        assert context.parameters["param1"] == "value1"
        
        # Test serialization
        context_dict = context.to_dict()
        assert "timestamp" in context_dict
        assert context_dict["request_id"] == "test-123"
    
    def test_diagnostic_info_creation(self):
        """Test diagnostic information creation and serialization"""
        context = ErrorContext(timestamp=datetime.now(timezone.utc))
        
        diagnostic = DiagnosticInfo(
            error_id="PE_VALIDATION_123456",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.LOW,
            message="Test error message",
            details="Additional details",
            suggested_action="Fix the input",
            recovery_possible=True,
            context=context,
            stack_trace="Mock stack trace"
        )
        
        assert diagnostic.error_id == "PE_VALIDATION_123456"
        assert diagnostic.category == ErrorCategory.VALIDATION
        assert diagnostic.severity == ErrorSeverity.LOW
        assert diagnostic.recovery_possible is True
        
        # Test serialization
        diagnostic_dict = diagnostic.to_dict()
        assert diagnostic_dict["category"] == "validation"
        assert diagnostic_dict["severity"] == "low"
        assert "context" in diagnostic_dict


class TestPricingEngineError:
    """Test base PricingEngineError functionality"""
    
    def test_basic_error_creation(self):
        """Test basic error creation with default values"""
        error = PricingEngineError("Test error message")
        
        assert str(error) == "Test error message"
        assert error.message == "Test error message"
        assert error.category == ErrorCategory.SYSTEM
        assert error.severity == ErrorSeverity.MEDIUM
        assert error.recovery_possible is True
        assert error.error_id.startswith("PE_SYSTEM_")
    
    def test_error_with_custom_attributes(self):
        """Test error creation with custom attributes"""
        context = ErrorContext(timestamp=datetime.now(timezone.utc))
        
        error = PricingEngineError(
            message="Custom error",
            category=ErrorCategory.CALCULATION,
            severity=ErrorSeverity.HIGH,
            details="Custom details",
            suggested_action="Custom action",
            recovery_possible=False,
            context=context
        )
        
        assert error.category == ErrorCategory.CALCULATION
        assert error.severity == ErrorSeverity.HIGH
        assert error.details == "Custom details"
        assert error.suggested_action == "Custom action"
        assert error.recovery_possible is False
        assert error.context == context
    
    def test_error_id_generation(self):
        """Test unique error ID generation"""
        error1 = PricingEngineError("Error 1", category=ErrorCategory.VALIDATION)
        error2 = PricingEngineError("Error 2", category=ErrorCategory.CALCULATION)
        
        assert error1.error_id != error2.error_id
        assert error1.error_id.startswith("PE_VALIDATION_")
        assert error2.error_id.startswith("PE_CALCULATION_")
    
    def test_diagnostic_info_generation(self):
        """Test diagnostic information generation from error"""
        error = PricingEngineError(
            "Test diagnostic error",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.HIGH,
            details="Test details"
        )
        
        diagnostic = error.get_diagnostic_info()
        
        assert diagnostic.error_id == error.error_id
        assert diagnostic.category == error.category
        assert diagnostic.severity == error.severity
        assert diagnostic.message == error.message
        assert diagnostic.details == error.details


class TestSpecificErrorTypes:
    """Test specific error type implementations"""
    
    def test_validation_error(self):
        """Test ValidationError specific functionality"""
        error = ValidationError(
            "Invalid parameter value",
            field="test_field",
            value="invalid_value"
        )
        
        assert error.category == ErrorCategory.VALIDATION
        assert error.severity == ErrorSeverity.LOW
        assert error.field == "test_field"
        assert error.value == "invalid_value"
        assert "Field: test_field" in error.details
        assert error.recovery_possible is True
    
    def test_calculation_error(self):
        """Test CalculationError specific functionality"""
        error = CalculationError(
            "Calculation failed",
            model="Black-Scholes",
            parameters={"s": 100, "k": 100}
        )
        
        assert error.category == ErrorCategory.CALCULATION
        assert error.severity == ErrorSeverity.MEDIUM
        assert error.model == "Black-Scholes"
        assert error.parameters == {"s": 100, "k": 100}
        assert "Model: Black-Scholes" in error.details
    
    def test_numerical_instability_error(self):
        """Test NumericalInstabilityError specific functionality"""
        error = NumericalInstabilityError("Numerical instability detected")
        
        assert error.category == ErrorCategory.CALCULATION
        assert error.severity == ErrorSeverity.HIGH
        assert "alternative method" in error.suggested_action
    
    def test_external_api_error(self):
        """Test ExternalAPIError specific functionality"""
        error = ExternalAPIError(
            "API request failed",
            api_name="Deriv API",
            status_code=503
        )
        
        assert error.category == ErrorCategory.EXTERNAL_API
        assert error.severity == ErrorSeverity.MEDIUM
        assert error.api_name == "Deriv API"
        assert error.status_code == 503
        assert "API: Deriv API" in error.details
    
    def test_system_error(self):
        """Test SystemError specific functionality"""
        error = SystemError("System failure")
        
        assert error.category == ErrorCategory.SYSTEM
        assert error.severity == ErrorSeverity.HIGH
        assert error.recovery_possible is False
        assert "administrator" in error.suggested_action


class TestErrorHandler:
    """Test ErrorHandler functionality"""
    
    def setup_method(self):
        """Set up test environment"""
        self.error_handler = ErrorHandler()
    
    def test_handle_pricing_engine_error(self):
        """Test handling of PricingEngineError"""
        error = ValidationError("Test validation error", field="test_field")
        context = create_error_context(request_id="test-123")
        
        diagnostic = self.error_handler.handle_error(error, context)
        
        assert diagnostic.error_id == error.error_id
        assert diagnostic.category == ErrorCategory.VALIDATION
        assert diagnostic.context == context
        
        # Check error tracking
        assert self.error_handler.error_counts["validation"] == 1
        assert len(self.error_handler.recent_errors) == 1
    
    def test_handle_generic_exception(self):
        """Test handling of generic exceptions"""
        error = ValueError("Generic error")
        context = create_error_context(request_id="test-456")
        
        diagnostic = self.error_handler.handle_error(error, context)
        
        assert diagnostic.category == ErrorCategory.SYSTEM
        assert diagnostic.severity == ErrorSeverity.MEDIUM
        assert "Generic error" in diagnostic.message
        assert diagnostic.context == context
    
    def test_error_statistics(self):
        """Test error statistics generation"""
        # Generate some errors
        self.error_handler.handle_error(ValidationError("Error 1"))
        self.error_handler.handle_error(ValidationError("Error 2"))
        self.error_handler.handle_error(CalculationError("Error 3"))
        
        stats = self.error_handler.get_error_stats()
        
        assert stats["error_counts_by_category"]["validation"] == 2
        assert stats["error_counts_by_category"]["calculation"] == 1
        assert stats["recent_errors_count"] == 3
        assert len(stats["recent_errors"]) == 3
    
    def test_clear_error_history(self):
        """Test clearing error history"""
        # Generate some errors
        self.error_handler.handle_error(ValidationError("Error 1"))
        self.error_handler.handle_error(CalculationError("Error 2"))
        
        assert len(self.error_handler.recent_errors) == 2
        assert len(self.error_handler.error_counts) == 2
        
        # Clear history
        self.error_handler.clear_error_history()
        
        assert len(self.error_handler.recent_errors) == 0
        assert len(self.error_handler.error_counts) == 0
    
    def test_recent_errors_limit(self):
        """Test recent errors list size limit"""
        # Set a small limit for testing
        self.error_handler.max_recent_errors = 5
        
        # Generate more errors than the limit
        for i in range(10):
            self.error_handler.handle_error(ValidationError(f"Error {i}"))
        
        # Should only keep the most recent errors
        assert len(self.error_handler.recent_errors) == 5
        assert "Error 9" in self.error_handler.recent_errors[-1].message


class TestUtilityFunctions:
    """Test utility functions"""
    
    def test_create_error_context(self):
        """Test error context creation utility"""
        context = create_error_context(
            request_id="test-123",
            user_id="user-456",
            endpoint="/test",
            parameters={"param": "value"}
        )
        
        assert context.request_id == "test-123"
        assert context.user_id == "user-456"
        assert context.endpoint == "/test"
        assert context.parameters == {"param": "value"}
        assert context.system_info is not None
        assert isinstance(context.timestamp, datetime)
    
    def test_handle_api_error_validation(self):
        """Test API error handling for validation errors"""
        error = ValidationError("Invalid input", field="test_field")
        context = create_error_context(request_id="test-123")
        
        http_exception = handle_api_error(error, context)
        
        assert isinstance(http_exception, HTTPException)
        assert http_exception.status_code == 400
        assert isinstance(http_exception.detail, dict)
        assert http_exception.detail["category"] == "validation"
        assert http_exception.detail["error_id"] == error.error_id
    
    def test_handle_api_error_calculation(self):
        """Test API error handling for calculation errors"""
        error = CalculationError("Calculation failed", model="FFT")
        
        http_exception = handle_api_error(error)
        
        assert http_exception.status_code == 422
        assert http_exception.detail["category"] == "calculation"
    
    def test_handle_api_error_system(self):
        """Test API error handling for system errors"""
        error = SystemError("System failure")
        
        http_exception = handle_api_error(error)
        
        assert http_exception.status_code == 500
        assert http_exception.detail["category"] == "system"
    
    def test_handle_api_error_external_api(self):
        """Test API error handling for external API errors"""
        error = ExternalAPIError("API unavailable", api_name="Deriv")
        
        http_exception = handle_api_error(error)
        
        assert http_exception.status_code == 502
        assert http_exception.detail["category"] == "external_api"


class TestLoggingConfiguration:
    """Test logging configuration"""
    
    def test_configure_logging_json(self):
        """Test JSON logging configuration"""
        # This test mainly ensures the function runs without error
        configure_logging(log_level="DEBUG", log_format="json")
        
        # Test that we can create a logger
        import structlog
        logger = structlog.get_logger("test")
        assert logger is not None
    
    def test_configure_logging_console(self):
        """Test console logging configuration"""
        configure_logging(log_level="INFO", log_format="console")
        
        import structlog
        logger = structlog.get_logger("test")
        assert logger is not None


class TestErrorHandlingIntegration:
    """Integration tests for error handling system"""
    
    def setup_method(self):
        """Set up test environment"""
        self.error_handler = ErrorHandler()
    
    def test_error_flow_validation_to_api(self):
        """Test complete error flow from validation to API response"""
        # Create validation error
        error = ValidationError(
            "Spot price must be positive",
            field="s",
            value=-100.0
        )
        
        # Create context
        context = create_error_context(
            request_id="test-flow-123",
            endpoint="/price/call/bs",
            parameters={"s": -100.0, "k": 100.0}
        )
        
        # Handle error
        diagnostic = self.error_handler.handle_error(error, context)
        
        # Convert to API error
        http_exception = handle_api_error(error, context)
        
        # Verify complete flow
        assert diagnostic.error_id == error.error_id
        assert http_exception.status_code == 400
        assert http_exception.detail["error_id"] == error.error_id
        assert http_exception.detail["suggested_action"] is not None
    
    def test_error_logging_and_tracking(self):
        """Test error logging and tracking functionality"""
        errors = [
            ValidationError("Error 1", field="field1"),
            CalculationError("Error 2", model="BS"),
            NumericalInstabilityError("Error 3"),
            ExternalAPIError("Error 4", api_name="Deriv"),
            SystemError("Error 5")
        ]
        
        # Handle all errors
        for error in errors:
            self.error_handler.handle_error(error)
        
        # Check statistics
        stats = self.error_handler.get_error_stats()
        
        assert stats["error_counts_by_category"]["validation"] == 1
        assert stats["error_counts_by_category"]["calculation"] == 2  # CalculationError + NumericalInstabilityError
        assert stats["error_counts_by_category"]["external_api"] == 1
        assert stats["error_counts_by_category"]["system"] == 1
        assert stats["recent_errors_count"] == 5
    
    @patch('error_handling.logger')
    def test_error_logging_levels(self, mock_logger):
        """Test that errors are logged at appropriate levels"""
        # Test different severity levels
        errors = [
            ValidationError("Low severity"),  # LOW
            CalculationError("Medium severity"),  # MEDIUM
            NumericalInstabilityError("High severity"),  # HIGH
            SystemError("Critical severity")  # HIGH (SystemError defaults to HIGH)
        ]
        
        for error in errors:
            self.error_handler.handle_error(error)
        
        # Verify logging calls were made
        assert mock_logger.info.called or mock_logger.warning.called or mock_logger.error.called
    
    def test_concurrent_error_handling(self):
        """Test error handling under concurrent conditions"""
        import threading
        import time
        
        def generate_errors():
            for i in range(10):
                error = ValidationError(f"Concurrent error {i}")
                self.error_handler.handle_error(error)
                time.sleep(0.01)  # Small delay to simulate real conditions
        
        # Start multiple threads
        threads = []
        for _ in range(3):
            thread = threading.Thread(target=generate_errors)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify all errors were handled
        stats = self.error_handler.get_error_stats()
        assert stats["error_counts_by_category"]["validation"] == 30
        assert stats["recent_errors_count"] == 30


if __name__ == "__main__":
    pytest.main([__file__])