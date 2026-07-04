"""
Comprehensive Health Check System for Pricing Engine.

This module provides detailed health checks for all pricing engine components,
including pricing models, external APIs, and system resources.
"""

import asyncio
import time
import psutil
import sys
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import structlog

# Import pricing engine components for testing
try:
    import pricing_engine
    PRICING_ENGINE_AVAILABLE = True
except ImportError:
    pricing_engine = None
    PRICING_ENGINE_AVAILABLE = False

from .error_handling import ErrorHandler, ErrorCategory, ErrorSeverity, PricingEngineError

logger = structlog.get_logger(__name__)


class HealthStatus(Enum):
    """Health check status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Result of a health check"""
    name: str
    status: HealthStatus
    message: str
    details: Optional[Dict[str, Any]] = None
    response_time_ms: Optional[float] = None
    timestamp: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        data = asdict(self)
        data['status'] = self.status.value
        if self.timestamp:
            data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class SystemHealthReport:
    """Comprehensive system health report"""
    overall_status: HealthStatus
    checks: List[HealthCheckResult]
    summary: Dict[str, Any]
    timestamp: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'overall_status': self.overall_status.value,
            'checks': [check.to_dict() for check in self.checks],
            'summary': self.summary,
            'timestamp': self.timestamp.isoformat()
        }


class HealthChecker:
    """Comprehensive health checking system"""
    
    def __init__(self):
        self.checks: Dict[str, Callable] = {}
        self.error_handler = ErrorHandler()
        self.last_check_time: Optional[datetime] = None
        self.cached_report: Optional[SystemHealthReport] = None
        self.cache_ttl_seconds = 30  # Cache health checks for 30 seconds
        
    def register_check(self, name: str, check_func: Callable) -> None:
        """Register a health check function"""
        self.checks[name] = check_func
        logger.info("Health check registered", check_name=name)
    
    async def run_check(self, name: str, check_func: Callable) -> HealthCheckResult:
        """Run a single health check with timing and error handling"""
        start_time = time.time()
        timestamp = datetime.now(timezone.utc)
        
        try:
            logger.debug("Running health check", check_name=name)
            
            # Run the check (handle both sync and async functions)
            if asyncio.iscoroutinefunction(check_func):
                result = await check_func()
            else:
                result = check_func()
            
            response_time = (time.time() - start_time) * 1000
            
            # Handle different return types
            if isinstance(result, HealthCheckResult):
                result.response_time_ms = response_time
                result.timestamp = timestamp
                return result
            elif isinstance(result, dict):
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus(result.get('status', 'unknown')),
                    message=result.get('message', 'Check completed'),
                    details=result.get('details'),
                    response_time_ms=response_time,
                    timestamp=timestamp
                )
            elif isinstance(result, bool):
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY,
                    message="Check passed" if result else "Check failed",
                    response_time_ms=response_time,
                    timestamp=timestamp
                )
            else:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.HEALTHY,
                    message=str(result),
                    response_time_ms=response_time,
                    timestamp=timestamp
                )
                
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            
            # Log the error
            self.error_handler.handle_error(
                PricingEngineError(
                    f"Health check failed: {name}",
                    category=ErrorCategory.SYSTEM,
                    severity=ErrorSeverity.MEDIUM,
                    details=str(e)
                )
            )
            
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {str(e)}",
                details={"error": str(e), "error_type": type(e).__name__},
                response_time_ms=response_time,
                timestamp=timestamp
            )
    
    async def run_all_checks(self, use_cache: bool = True) -> SystemHealthReport:
        """Run all registered health checks and generate report"""
        
        # Check cache first
        if use_cache and self.cached_report and self.last_check_time:
            age = (datetime.now(timezone.utc) - self.last_check_time).total_seconds()
            if age < self.cache_ttl_seconds:
                logger.debug("Returning cached health report", age_seconds=age)
                return self.cached_report
        
        logger.info("Running comprehensive health checks", check_count=len(self.checks))
        
        # Run all checks concurrently
        check_tasks = [
            self.run_check(name, check_func)
            for name, check_func in self.checks.items()
        ]
        
        results = await asyncio.gather(*check_tasks, return_exceptions=True)
        
        # Process results
        check_results = []
        for result in results:
            if isinstance(result, Exception):
                check_results.append(HealthCheckResult(
                    name="unknown",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check execution failed: {str(result)}",
                    timestamp=datetime.now(timezone.utc)
                ))
            else:
                check_results.append(result)
        
        # Determine overall status
        overall_status = self._determine_overall_status(check_results)
        
        # Generate summary
        summary = self._generate_summary(check_results)
        
        # Create report
        report = SystemHealthReport(
            overall_status=overall_status,
            checks=check_results,
            summary=summary,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Cache the report
        self.cached_report = report
        self.last_check_time = report.timestamp
        
        logger.info("Health check completed", 
                   overall_status=overall_status.value,
                   check_count=len(check_results))
        
        return report
    
    def _determine_overall_status(self, results: List[HealthCheckResult]) -> HealthStatus:
        """Determine overall system health from individual check results"""
        if not results:
            return HealthStatus.UNKNOWN
        
        statuses = [result.status for result in results]
        
        # If any critical checks are unhealthy, system is unhealthy
        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY
        
        # If any checks are degraded, system is degraded
        if HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED
        
        # If all checks are healthy, system is healthy
        if all(status == HealthStatus.HEALTHY for status in statuses):
            return HealthStatus.HEALTHY
        
        # Otherwise, status is unknown
        return HealthStatus.UNKNOWN
    
    def _generate_summary(self, results: List[HealthCheckResult]) -> Dict[str, Any]:
        """Generate summary statistics from health check results"""
        if not results:
            return {}
        
        status_counts = {}
        total_response_time = 0
        response_time_count = 0
        
        for result in results:
            status = result.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
            
            if result.response_time_ms is not None:
                total_response_time += result.response_time_ms
                response_time_count += 1
        
        avg_response_time = total_response_time / response_time_count if response_time_count > 0 else None
        
        return {
            'total_checks': len(results),
            'status_counts': status_counts,
            'average_response_time_ms': avg_response_time,
            'system_info': self._get_system_info()
        }
    
    def _get_system_info(self) -> Dict[str, Any]:
        """Get system information for health reporting"""
        try:
            return {
                'python_version': sys.version,
                'cpu_percent': psutil.cpu_percent(interval=1),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_percent': psutil.disk_usage('/').percent,
                'uptime_seconds': time.time() - psutil.boot_time(),
                'pricing_engine_available': PRICING_ENGINE_AVAILABLE
            }
        except Exception as e:
            logger.warning("Failed to get system info", error=str(e))
            return {'error': str(e)}


# Global health checker instance
health_checker = HealthChecker()


# Built-in health checks
def check_pricing_engine_basic() -> HealthCheckResult:
    """Check if pricing engine is available and basic functions work"""
    if not PRICING_ENGINE_AVAILABLE:
        return HealthCheckResult(
            name="pricing_engine_basic",
            status=HealthStatus.UNHEALTHY,
            message="Pricing engine not available",
            details={"error": "Failed to import pricing_engine module"}
        )
    
    try:
        # Test basic Black-Scholes calculation
        price = pricing_engine.price_call(100.0, 100.0, 0.25, 0.05, 0.2)
        
        if not isinstance(price, (int, float)) or price <= 0:
            return HealthCheckResult(
                name="pricing_engine_basic",
                status=HealthStatus.UNHEALTHY,
                message="Pricing engine returned invalid result",
                details={"result": price}
            )
        
        return HealthCheckResult(
            name="pricing_engine_basic",
            status=HealthStatus.HEALTHY,
            message="Pricing engine basic functionality working",
            details={"test_price": price}
        )
        
    except Exception as e:
        return HealthCheckResult(
            name="pricing_engine_basic",
            status=HealthStatus.UNHEALTHY,
            message=f"Pricing engine test failed: {str(e)}",
            details={"error": str(e), "error_type": type(e).__name__}
        )


def check_pricing_models() -> HealthCheckResult:
    """Check all pricing models are functioning"""
    if not PRICING_ENGINE_AVAILABLE:
        return HealthCheckResult(
            name="pricing_models",
            status=HealthStatus.UNHEALTHY,
            message="Pricing engine not available"
        )
    
    test_params = {
        's': 100.0, 'k': 100.0, 'tau': 0.25, 'r': 0.05, 'sigma': 0.2
    }
    
    models_tested = {}
    failed_models = []
    
    # Test Black-Scholes
    try:
        call_price = pricing_engine.price_call(**test_params)
        put_price = pricing_engine.price_put(**test_params)
        models_tested['black_scholes'] = {'call': call_price, 'put': put_price}
    except Exception as e:
        failed_models.append(f"Black-Scholes: {str(e)}")
    
    # Test FFT Optimized
    try:
        fft_call = pricing_engine.price_call_fft_optimized(**test_params)
        fft_put = pricing_engine.price_put_fft_optimized(**test_params)
        models_tested['fft_optimized'] = {'call': fft_call, 'put': fft_put}
    except Exception as e:
        failed_models.append(f"FFT-Optimized: {str(e)}")
    
    # Test Heston (with valid parameters)
    try:
        heston_params = {
            's': 100.0, 'k': 100.0, 'tau': 0.25, 'r': 0.05,
            'v0': 0.04, 'theta': 0.04, 'kappa': 2.0, 'sigma_v': 0.3, 'rho': -0.5
        }
        heston_call = pricing_engine.price_heston_call(**heston_params)
        heston_put = pricing_engine.price_heston_put(**heston_params)
        models_tested['heston'] = {'call': heston_call, 'put': heston_put}
    except Exception as e:
        failed_models.append(f"Heston: {str(e)}")
    
    # Determine status
    if failed_models:
        if len(failed_models) == 3:  # All models failed
            status = HealthStatus.UNHEALTHY
            message = "All pricing models failed"
        else:
            status = HealthStatus.DEGRADED
            message = f"{len(failed_models)} pricing model(s) failed"
    else:
        status = HealthStatus.HEALTHY
        message = "All pricing models working correctly"
    
    return HealthCheckResult(
        name="pricing_models",
        status=status,
        message=message,
        details={
            'models_tested': models_tested,
            'failed_models': failed_models,
            'total_models': 3,
            'working_models': 3 - len(failed_models)
        }
    )


def check_greeks_calculation() -> HealthCheckResult:
    """Check Greeks calculation functionality"""
    if not PRICING_ENGINE_AVAILABLE:
        return HealthCheckResult(
            name="greeks_calculation",
            status=HealthStatus.UNHEALTHY,
            message="Pricing engine not available"
        )
    
    test_params = {
        's': 100.0, 'k': 100.0, 'tau': 0.25, 'r': 0.05, 'sigma': 0.2
    }
    
    greeks_tested = {}
    failed_methods = []
    
    # Test Black-Scholes Greeks
    try:
        bs_call_greeks = pricing_engine.calculate_bs_call_greeks(**test_params)
        bs_put_greeks = pricing_engine.calculate_bs_put_greeks(**test_params)
        greeks_tested['black_scholes'] = {
            'call': {
                'delta': bs_call_greeks.delta,
                'gamma': bs_call_greeks.gamma,
                'theta': bs_call_greeks.theta,
                'vega': bs_call_greeks.vega,
                'rho': bs_call_greeks.rho
            },
            'put': {
                'delta': bs_put_greeks.delta,
                'gamma': bs_put_greeks.gamma,
                'theta': bs_put_greeks.theta,
                'vega': bs_put_greeks.vega,
                'rho': bs_put_greeks.rho
            }
        }
    except Exception as e:
        failed_methods.append(f"Black-Scholes Greeks: {str(e)}")
    
    # Test Numerical Greeks
    try:
        num_call_greeks = pricing_engine.calculate_numerical_call_greeks(**test_params)
        num_put_greeks = pricing_engine.calculate_numerical_put_greeks(**test_params)
        greeks_tested['numerical'] = {
            'call': {
                'delta': num_call_greeks.delta,
                'gamma': num_call_greeks.gamma,
                'theta': num_call_greeks.theta,
                'vega': num_call_greeks.vega,
                'rho': num_call_greeks.rho
            },
            'put': {
                'delta': num_put_greeks.delta,
                'gamma': num_put_greeks.gamma,
                'theta': num_put_greeks.theta,
                'vega': num_put_greeks.vega,
                'rho': num_put_greeks.rho
            }
        }
    except Exception as e:
        failed_methods.append(f"Numerical Greeks: {str(e)}")
    
    # Determine status
    if failed_methods:
        if len(failed_methods) == 2:  # All methods failed
            status = HealthStatus.UNHEALTHY
            message = "All Greeks calculation methods failed"
        else:
            status = HealthStatus.DEGRADED
            message = f"{len(failed_methods)} Greeks method(s) failed"
    else:
        status = HealthStatus.HEALTHY
        message = "Greeks calculation working correctly"
    
    return HealthCheckResult(
        name="greeks_calculation",
        status=status,
        message=message,
        details={
            'methods_tested': greeks_tested,
            'failed_methods': failed_methods,
            'total_methods': 2,
            'working_methods': 2 - len(failed_methods)
        }
    )


async def check_market_data_api() -> HealthCheckResult:
    """Check market data API connectivity"""
    try:
        # Import here to avoid circular imports
        from deriv_api_client import create_test_client
        
        async with create_test_client() as client:
            # Test basic connectivity
            is_connected = await client.validate_connection()
            
            if not is_connected:
                return HealthCheckResult(
                    name="market_data_api",
                    status=HealthStatus.DEGRADED,
                    message="Market data API connection failed",
                    details={"connection_test": False}
                )
            
            # Test data retrieval
            try:
                market_data = await client.get_market_data("AAPL")
                cache_stats = client.get_cache_stats()
                
                return HealthCheckResult(
                    name="market_data_api",
                    status=HealthStatus.HEALTHY,
                    message="Market data API working correctly",
                    details={
                        "connection_test": True,
                        "data_retrieval": True,
                        "sample_symbol": market_data.symbol,
                        "cache_stats": cache_stats
                    }
                )
            except Exception as e:
                return HealthCheckResult(
                    name="market_data_api",
                    status=HealthStatus.DEGRADED,
                    message=f"Market data retrieval failed: {str(e)}",
                    details={"connection_test": True, "data_retrieval": False, "error": str(e)}
                )
                
    except ImportError:
        return HealthCheckResult(
            name="market_data_api",
            status=HealthStatus.DEGRADED,
            message="Market data API client not available",
            details={"import_error": True}
        )
    except Exception as e:
        return HealthCheckResult(
            name="market_data_api",
            status=HealthStatus.UNHEALTHY,
            message=f"Market data API check failed: {str(e)}",
            details={"error": str(e), "error_type": type(e).__name__}
        )


def check_system_resources() -> HealthCheckResult:
    """Check system resource usage"""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Define thresholds
        cpu_warning = 80.0
        cpu_critical = 95.0
        memory_warning = 80.0
        memory_critical = 95.0
        disk_warning = 85.0
        disk_critical = 95.0
        
        issues = []
        status = HealthStatus.HEALTHY
        
        # Check CPU
        if cpu_percent > cpu_critical:
            issues.append(f"CPU usage critical: {cpu_percent:.1f}%")
            status = HealthStatus.UNHEALTHY
        elif cpu_percent > cpu_warning:
            issues.append(f"CPU usage high: {cpu_percent:.1f}%")
            if status == HealthStatus.HEALTHY:
                status = HealthStatus.DEGRADED
        
        # Check Memory
        if memory.percent > memory_critical:
            issues.append(f"Memory usage critical: {memory.percent:.1f}%")
            status = HealthStatus.UNHEALTHY
        elif memory.percent > memory_warning:
            issues.append(f"Memory usage high: {memory.percent:.1f}%")
            if status == HealthStatus.HEALTHY:
                status = HealthStatus.DEGRADED
        
        # Check Disk
        if disk.percent > disk_critical:
            issues.append(f"Disk usage critical: {disk.percent:.1f}%")
            status = HealthStatus.UNHEALTHY
        elif disk.percent > disk_warning:
            issues.append(f"Disk usage high: {disk.percent:.1f}%")
            if status == HealthStatus.HEALTHY:
                status = HealthStatus.DEGRADED
        
        message = "System resources normal" if not issues else "; ".join(issues)
        
        return HealthCheckResult(
            name="system_resources",
            status=status,
            message=message,
            details={
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_available_gb': memory.available / (1024**3),
                'disk_percent': disk.percent,
                'disk_free_gb': disk.free / (1024**3),
                'thresholds': {
                    'cpu_warning': cpu_warning,
                    'cpu_critical': cpu_critical,
                    'memory_warning': memory_warning,
                    'memory_critical': memory_critical,
                    'disk_warning': disk_warning,
                    'disk_critical': disk_critical
                }
            }
        )
        
    except Exception as e:
        return HealthCheckResult(
            name="system_resources",
            status=HealthStatus.UNKNOWN,
            message=f"Failed to check system resources: {str(e)}",
            details={"error": str(e)}
        )


# Register built-in health checks
health_checker.register_check("pricing_engine_basic", check_pricing_engine_basic)
health_checker.register_check("pricing_models", check_pricing_models)
health_checker.register_check("greeks_calculation", check_greeks_calculation)
health_checker.register_check("market_data_api", check_market_data_api)
health_checker.register_check("system_resources", check_system_resources)


# Convenience functions
async def get_health_report(use_cache: bool = True) -> SystemHealthReport:
    """Get comprehensive health report"""
    return await health_checker.run_all_checks(use_cache=use_cache)


async def get_basic_health() -> Dict[str, Any]:
    """Get basic health status (faster, cached)"""
    report = await health_checker.run_all_checks(use_cache=True)
    return {
        'status': report.overall_status.value,
        'timestamp': report.timestamp.isoformat(),
        'summary': report.summary
    }