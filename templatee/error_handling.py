"""
Enhanced Error Handling and Logging for Pricing Engine.

This module provides comprehensive error handling, structured logging,
and diagnostic information for all pricing engine components.
"""

import logging
import traceback
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass, asdict
import structlog
from fastapi import HTTPException
import json


class ErrorSeverity(Enum):
    """Error severity levels for classification"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for classification"""
    VALIDATION = "validation"
    CALCULATION = "calculation"
    NETWORK = "network"
    SYSTEM = "system"
    EXTERNAL_API = "external_api"
    CONFIGURATION = "configuration"


@dataclass
class ErrorContext:
    """Context information for error reporting"""
    timestamp: datetime
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    endpoint: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    system_info: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class DiagnosticInfo:
    """Diagnostic information for error analysis"""
    error_id: str
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    details: Optional[str] = None
    suggested_action: Optional[str] = None
    recovery_possible: bool = True
    context: Optional[ErrorContext] = None
    stack_trace: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging and API responses"""
        data = asdict(self)
        data['category'] = self.category.value
        data['severity'] = self.severity.value
        if self.context:
            data['context'] = self.context.to_dict()
        return data


class PricingEngineError(Exception):
    """Base exception for pricing engine errors"""
    
    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.SYSTEM,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        details: Optional[str] = None,
        suggested_action: Optional[str] = None,
        recovery_possible: bool = True,
        context: Optional[ErrorContext] = None
    ):
        super().__init__(message)
        self.message = message
        self.category = category
        self.severity = severity
        self.details = details
        self.suggested_action = suggested_action
        self.recovery_possible = recovery_possible
        self.context = context
        self.error_id = self._generate_error_id()
        
    def _generate_error_id(self) -> str:
        """Generate unique error ID for tracking"""
        timestamp = int(time.time() * 1000)
        return f"PE_{self.category.value.upper()}_{timestamp}"
    
    def get_diagnostic_info(self) -> DiagnosticInfo:
        """Get comprehensive diagnostic information"""
        return DiagnosticInfo(
            error_id=self.error_id,
            category=self.category,
            severity=self.severity,
            message=self.message,
            details=self.details,
            suggested_action=self.suggested_action,
            recovery_possible=self.recovery_possible,
            context=self.context,
            stack_trace=traceback.format_exc() if self.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL] else None
        )


class ValidationError(PricingEngineError):
    """Error for input validation failures"""
    
    def __init__(self, message: str, field: Optional[str] = None, value: Any = None, **kwargs):
        self.field = field
        self.value = value
        details = f"Field: {field}, Value: {value}" if field else None
        suggested_action = f"Please provide a valid value for {field}" if field else "Please check input parameters"
        
        super().__init__(
            message=message,
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.LOW,
            details=details,
            suggested_action=suggested_action,
            recovery_possible=True,
            **kwargs
        )


class CalculationError(PricingEngineError):
    """Error for pricing calculation failures"""
    
    def __init__(self, message: str, model: Optional[str] = None, parameters: Optional[Dict] = None, **kwargs):
        self.model = model
        self.parameters = parameters
        details = f"Model: {model}" if model else None
        
        # Set defaults that can be overridden by kwargs
        kwargs.setdefault('category', ErrorCategory.CALCULATION)
        kwargs.setdefault('severity', ErrorSeverity.MEDIUM)
        kwargs.setdefault('details', details)
        kwargs.setdefault('suggested_action', "Try adjusting parameters or using alternative pricing model")
        kwargs.setdefault('recovery_possible', True)
        
        super().__init__(message=message, **kwargs)


class NumericalInstabilityError(CalculationError):
    """Error for numerical instability in calculations"""
    
    def __init__(self, message: str, **kwargs):
        # Override the default suggested action and severity
        kwargs.setdefault('severity', ErrorSeverity.HIGH)
        kwargs.setdefault('suggested_action', "Adjust numerical parameters or use alternative method")
        
        super().__init__(message, **kwargs)


class ExternalAPIError(PricingEngineError):
    """Error for external API failures"""
    
    def __init__(self, message: str, api_name: Optional[str] = None, status_code: Optional[int] = None, **kwargs):
        self.api_name = api_name
        self.status_code = status_code
        details = f"API: {api_name}, Status: {status_code}" if api_name else None
        suggested_action = "Check API connectivity and credentials, or use manual input mode"
        
        super().__init__(
            message=message,
            category=ErrorCategory.EXTERNAL_API,
            severity=ErrorSeverity.MEDIUM,
            details=details,
            suggested_action=suggested_action,
            recovery_possible=True,
            **kwargs
        )


class SystemError(PricingEngineError):
    """Error for system-level failures"""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.SYSTEM,
            severity=ErrorSeverity.HIGH,
            suggested_action="Contact system administrator",
            recovery_possible=False,
            **kwargs
        )


# Configure structured logging
def configure_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """Configure structured logging for the application"""
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if log_format == "json" else structlog.dev.ConsoleRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper()),
    )


# Get structured logger
logger = structlog.get_logger(__name__)


class ErrorHandler:
    """Centralized error handling and logging"""
    
    def __init__(self):
        self.error_counts: Dict[str, int] = {}
        self.recent_errors: List[DiagnosticInfo] = []
        self.max_recent_errors = 100
    
    def handle_error(
        self,
        error: Exception,
        context: Optional[ErrorContext] = None,
        log_level: str = "error"
    ) -> DiagnosticInfo:
        """Handle and log an error with full diagnostic information"""
        
        # Convert to PricingEngineError if needed
        if not isinstance(error, PricingEngineError):
            pricing_error = PricingEngineError(
                message=str(error),
                category=ErrorCategory.SYSTEM,
                severity=ErrorSeverity.MEDIUM,
                context=context
            )
        else:
            pricing_error = error
            if context and not pricing_error.context:
                pricing_error.context = context
        
        # Get diagnostic information
        diagnostic = pricing_error.get_diagnostic_info()
        
        # Update error tracking
        self.error_counts[diagnostic.category.value] = self.error_counts.get(diagnostic.category.value, 0) + 1
        self.recent_errors.append(diagnostic)
        
        # Trim recent errors list
        if len(self.recent_errors) > self.max_recent_errors:
            self.recent_errors = self.recent_errors[-self.max_recent_errors:]
        
        # Log the error
        log_data = diagnostic.to_dict()
        
        if diagnostic.severity == ErrorSeverity.CRITICAL:
            logger.critical("Critical error occurred", **log_data)
        elif diagnostic.severity == ErrorSeverity.HIGH:
            logger.error("High severity error occurred", **log_data)
        elif diagnostic.severity == ErrorSeverity.MEDIUM:
            logger.warning("Medium severity error occurred", **log_data)
        else:
            logger.info("Low severity error occurred", **log_data)
        
        return diagnostic
    
    def get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics for monitoring"""
        return {
            "error_counts_by_category": self.error_counts.copy(),
            "recent_errors_count": len(self.recent_errors),
            "recent_errors": [error.to_dict() for error in self.recent_errors[-10:]]  # Last 10 errors
        }
    
    def clear_error_history(self) -> None:
        """Clear error history (for testing or maintenance)"""
        self.error_counts.clear()
        self.recent_errors.clear()
        logger.info("Error history cleared")


# Global error handler instance
error_handler = ErrorHandler()


def create_error_context(
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
    endpoint: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None
) -> ErrorContext:
    """Create error context for request tracking"""
    return ErrorContext(
        timestamp=datetime.now(timezone.utc),
        request_id=request_id,
        user_id=user_id,
        endpoint=endpoint,
        parameters=parameters,
        system_info={
            "python_version": "3.x",
            "pricing_engine_version": "1.0.0"
        }
    )


def handle_api_error(error: Exception, context: Optional[ErrorContext] = None) -> HTTPException:
    """Convert pricing engine errors to FastAPI HTTP exceptions"""
    
    diagnostic = error_handler.handle_error(error, context)
    
    # Map error categories to HTTP status codes
    status_code_map = {
        ErrorCategory.VALIDATION: 400,
        ErrorCategory.CALCULATION: 422,
        ErrorCategory.NETWORK: 503,
        ErrorCategory.EXTERNAL_API: 502,
        ErrorCategory.SYSTEM: 500,
        ErrorCategory.CONFIGURATION: 500
    }
    
    status_code = status_code_map.get(diagnostic.category, 500)
    
    # Create detailed error response
    error_response = {
        "error_id": diagnostic.error_id,
        "message": diagnostic.message,
        "category": diagnostic.category.value,
        "severity": diagnostic.severity.value,
        "suggested_action": diagnostic.suggested_action,
        "recovery_possible": diagnostic.recovery_possible
    }
    
    # Add details for non-production environments
    if diagnostic.details:
        error_response["details"] = diagnostic.details
    
    return HTTPException(status_code=status_code, detail=error_response)


# Decorator for automatic error handling
def handle_errors(func):
    """Decorator to automatically handle errors in API endpoints"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except PricingEngineError as e:
            raise handle_api_error(e)
        except Exception as e:
            # Convert unexpected errors to PricingEngineError
            pricing_error = SystemError(f"Unexpected error: {str(e)}")
            raise handle_api_error(pricing_error)
    
    return wrapper


# Initialize logging on module import
configure_logging()