"""
Performance benchmark tests for the pricing engine.

This module tests response times for all pricing models to ensure they meet
the performance requirements specified in the design document:
- Black-Scholes calculations: under 100ms
- Heston model pricing: within 500ms
- FFT pricing: under 100ms (optimized version)
- Greeks calculations: under 200ms

Requirements: 6.1, 6.2, 6.3
"""

import pytest
import time
import statistics
import sys
import os
import threading
import concurrent.futures
from typing import List, Dict, Any, Callable
import gc

# Add the parent directory to the path to import pricing_engine
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import pricing_engine
    PRICING_ENGINE_AVAILABLE = True
except ImportError:
    import pricing_engine_mock as pricing_engine
    PRICING_ENGINE_AVAILABLE = False
    print("Warning: Using mock pricing engine for performance tests")


class TestBlackScholesPerformance:
    """Performance benchmarks for Black-Scholes pricing model"""
    
    def setup_method(self):
        """Set up test parameters"""
        self.s = 100.0  # Spot price
        self.k = 100.0  # Strike price
        self.tau = 0.25  # 3 months
        self.r = 0.05   # 5% risk-free rate
        self.sigma = 0.2  # 20% volatility
        
    def test_single_call_performance(self):
        """Test single Black-Scholes call pricing performance"""
        # Warmup call to avoid module loading overhead
        pricing_engine.price_call(self.s, self.k, self.tau, self.r, self.sigma)
        
        start_time = time.perf_counter()
        price = pricing_engine.price_call(self.s, self.k, self.tau, self.r, self.sigma)
        elapsed = (time.perf_counter() - start_time) * 1000  # Convert to milliseconds
        
        assert price > 0, "Call price should be positive"
        assert elapsed < 100, f"Black-Scholes call pricing took {elapsed:.2f}ms, should be under 100ms"
        
    def test_single_put_performance(self):
        """Test single Black-Scholes put pricing performance"""
        start_time = time.perf_counter()
        price = pricing_engine.price_put(self.s, self.k, self.tau, self.r, self.sigma)
        elapsed = (time.perf_counter() - start_time) * 1000  # Convert to milliseconds
        
        assert price > 0, "Put price should be positive"
        assert elapsed < 100, f"Black-Scholes put pricing took {elapsed:.2f}ms, should be under 100ms"
        
    def test_batch_pricing_performance(self):
        """Test batch Black-Scholes pricing performance"""
        num_calculations = 1000
        
        start_time = time.perf_counter()
        for i in range(num_calculations):
            strike = 90 + i * 0.02  # Vary strikes from 90 to 110
            pricing_engine.price_call(self.s, strike, self.tau, self.r, self.sigma)
        elapsed = (time.perf_counter() - start_time) * 1000  # Convert to milliseconds
        
        avg_time_per_calc = elapsed / num_calculations
        assert avg_time_per_calc < 1.0, f"Average Black-Scholes pricing took {avg_time_per_calc:.3f}ms per calculation, should be under 1ms"
        
    def test_concurrent_pricing_simulation(self):
        """Simulate concurrent pricing requests"""
        num_concurrent = 100
        times = []
        
        for _ in range(num_concurrent):
            start_time = time.perf_counter()
            pricing_engine.price_call(self.s, self.k, self.tau, self.r, self.sigma)
            elapsed = (time.perf_counter() - start_time) * 1000
            times.append(elapsed)
        
        avg_time = statistics.mean(times)
        max_time = max(times)
        p95_time = sorted(times)[int(0.95 * len(times))]
        
        assert avg_time < 50, f"Average concurrent pricing time {avg_time:.2f}ms should be under 50ms"
        assert p95_time < 100, f"95th percentile pricing time {p95_time:.2f}ms should be under 100ms"


class TestFFTPricingPerformance:
    """Performance benchmarks for FFT pricing models"""
    
    def setup_method(self):
        """Set up test parameters"""
        self.s = 100.0
        self.k = 100.0
        self.tau = 0.25
        self.r = 0.05
        self.sigma = 0.2
        
    def test_fft_optimized_call_performance(self):
        """Test FFT optimized call pricing performance"""
        start_time = time.perf_counter()
        price = pricing_engine.price_call_fft_optimized(self.s, self.k, self.tau, self.r, self.sigma)
        elapsed = (time.perf_counter() - start_time) * 1000
        
        assert price > 0, "FFT call price should be positive"
        assert elapsed < 100, f"FFT optimized call pricing took {elapsed:.2f}ms, should be under 100ms"
        
    def test_fft_optimized_put_performance(self):
        """Test FFT optimized put pricing performance"""
        start_time = time.perf_counter()
        price = pricing_engine.price_put_fft_optimized(self.s, self.k, self.tau, self.r, self.sigma)
        elapsed = (time.perf_counter() - start_time) * 1000
        
        assert price > 0, "FFT put price should be positive"
        assert elapsed < 100, f"FFT optimized put pricing took {elapsed:.2f}ms, should be under 100ms"
        
    def test_fft_enhanced_performance(self):
        """Test FFT enhanced pricing performance with manual parameters"""
        # Manual FFT parameters
        k_min = 50.0
        delta_v = 0.01
        delta_k = 0.5
        n = 2048
        alpha = 1.5
        
        start_time = time.perf_counter()
        price = pricing_engine.price_call_fft_enhanced(
            self.s, self.k, k_min, delta_v, delta_k, n, self.tau, self.r, self.sigma, alpha
        )
        elapsed = (time.perf_counter() - start_time) * 1000
        
        assert price > 0, "FFT enhanced call price should be positive"
        assert elapsed < 150, f"FFT enhanced call pricing took {elapsed:.2f}ms, should be under 150ms"


class TestHestonModelPerformance:
    """Performance benchmarks for Heston stochastic volatility model"""
    
    def setup_method(self):
        """Set up test parameters"""
        self.s = 100.0
        self.k = 100.0
        self.tau = 0.25
        self.r = 0.05
        self.v0 = 0.04      # Initial variance (20% vol)
        self.theta = 0.04   # Long-term variance
        self.kappa = 2.0    # Mean reversion speed
        self.sigma_v = 0.3  # Volatility of volatility
        self.rho = -0.7     # Correlation
        
    def test_heston_call_performance(self):
        """Test Heston call pricing performance"""
        start_time = time.perf_counter()
        price = pricing_engine.price_heston_call(
            self.s, self.k, self.v0, self.r, self.kappa, 
            self.theta, self.sigma_v, self.rho, self.tau
        )
        elapsed = (time.perf_counter() - start_time) * 1000
        
        assert price > 0, "Heston call price should be positive"
        assert elapsed < 500, f"Heston call pricing took {elapsed:.2f}ms, should be under 500ms"
        
    def test_heston_put_performance(self):
        """Test Heston put pricing performance"""
        start_time = time.perf_counter()
        price = pricing_engine.price_heston_put(
            self.s, self.k, self.v0, self.r, self.kappa, 
            self.theta, self.sigma_v, self.rho, self.tau
        )
        elapsed = (time.perf_counter() - start_time) * 1000
        
        assert price > 0, "Heston put price should be positive"
        assert elapsed < 500, f"Heston put pricing took {elapsed:.2f}ms, should be under 500ms"
        
    def test_heston_batch_performance(self):
        """Test Heston model batch pricing performance"""
        num_calculations = 50  # Fewer calculations due to complexity
        times = []
        
        for i in range(num_calculations):
            strike = 90 + i * 0.4  # Vary strikes from 90 to 110
            start_time = time.perf_counter()
            pricing_engine.price_heston_call(
                self.s, strike, self.v0, self.r, self.kappa, 
                self.theta, self.sigma_v, self.rho, self.tau
            )
            elapsed = (time.perf_counter() - start_time) * 1000
            times.append(elapsed)
        
        avg_time = statistics.mean(times)
        max_time = max(times)
        
        assert avg_time < 400, f"Average Heston pricing time {avg_time:.2f}ms should be under 400ms"
        assert max_time < 800, f"Maximum Heston pricing time {max_time:.2f}ms should be under 800ms"


class TestGreeksPerformance:
    """Performance benchmarks for Greeks calculations"""
    
    def setup_method(self):
        """Set up test parameters"""
        self.s = 100.0
        self.k = 100.0
        self.tau = 0.25
        self.r = 0.05
        self.sigma = 0.2
        
    def test_bs_greeks_performance(self):
        """Test Black-Scholes Greeks calculation performance"""
        start_time = time.perf_counter()
        greeks = pricing_engine.calculate_bs_call_greeks(self.s, self.k, self.tau, self.r, self.sigma)
        elapsed = (time.perf_counter() - start_time) * 1000
        
        assert hasattr(greeks, 'delta'), "Greeks should have delta"
        assert hasattr(greeks, 'gamma'), "Greeks should have gamma"
        assert hasattr(greeks, 'theta'), "Greeks should have theta"
        assert hasattr(greeks, 'vega'), "Greeks should have vega"
        assert hasattr(greeks, 'rho'), "Greeks should have rho"
        assert elapsed < 50, f"BS Greeks calculation took {elapsed:.2f}ms, should be under 50ms"
        
    def test_numerical_greeks_performance(self):
        """Test numerical Greeks calculation performance"""
        start_time = time.perf_counter()
        greeks = pricing_engine.calculate_numerical_call_greeks(self.s, self.k, self.tau, self.r, self.sigma)
        elapsed = (time.perf_counter() - start_time) * 1000
        
        assert hasattr(greeks, 'delta'), "Greeks should have delta"
        assert elapsed < 200, f"Numerical Greeks calculation took {elapsed:.2f}ms, should be under 200ms"
        
    def test_fft_greeks_performance(self):
        """Test FFT-based Greeks calculation performance"""
        start_time = time.perf_counter()
        greeks = pricing_engine.calculate_fft_call_greeks(self.s, self.k, self.tau, self.r, self.sigma)
        elapsed = (time.perf_counter() - start_time) * 1000
        
        assert hasattr(greeks, 'delta'), "Greeks should have delta"
        assert elapsed < 300, f"FFT Greeks calculation took {elapsed:.2f}ms, should be under 300ms"
        
    def test_heston_greeks_performance(self):
        """Test Heston Greeks calculation performance"""
        v0 = 0.04
        theta = 0.04
        kappa = 2.0
        sigma_v = 0.3
        rho = -0.7
        
        start_time = time.perf_counter()
        greeks = pricing_engine.calculate_heston_call_greeks(
            self.s, self.k, self.tau, self.r, v0, theta, kappa, sigma_v, rho
        )
        elapsed = (time.perf_counter() - start_time) * 1000
        
        assert hasattr(greeks, 'delta'), "Greeks should have delta"
        assert elapsed < 800, f"Heston Greeks calculation took {elapsed:.2f}ms, should be under 800ms"


class TestOverallSystemPerformance:
    """Overall system performance tests"""
    
    def setup_method(self):
        """Set up test parameters"""
        self.s = 100.0
        self.k = 100.0
        self.tau = 0.25
        self.r = 0.05
        self.sigma = 0.2
        
    def test_mixed_workload_performance(self):
        """Test performance under mixed pricing model workload"""
        operations = [
            ("bs_call", lambda: pricing_engine.price_call(self.s, self.k, self.tau, self.r, self.sigma)),
            ("bs_put", lambda: pricing_engine.price_put(self.s, self.k, self.tau, self.r, self.sigma)),
            ("fft_call", lambda: pricing_engine.price_call_fft_optimized(self.s, self.k, self.tau, self.r, self.sigma)),
            ("fft_put", lambda: pricing_engine.price_put_fft_optimized(self.s, self.k, self.tau, self.r, self.sigma)),
            ("bs_greeks", lambda: pricing_engine.calculate_bs_call_greeks(self.s, self.k, self.tau, self.r, self.sigma)),
        ]
        
        total_time = 0
        operation_times = {}
        
        # Run each operation 20 times
        for op_name, op_func in operations:
            times = []
            for _ in range(20):
                start_time = time.perf_counter()
                result = op_func()
                elapsed = (time.perf_counter() - start_time) * 1000
                times.append(elapsed)
                total_time += elapsed
            
            operation_times[op_name] = {
                'avg': statistics.mean(times),
                'max': max(times),
                'min': min(times)
            }
        
        # Verify individual operation performance
        assert operation_times['bs_call']['avg'] < 50, f"BS call average time too high: {operation_times['bs_call']['avg']:.2f}ms"
        assert operation_times['fft_call']['avg'] < 100, f"FFT call average time too high: {operation_times['fft_call']['avg']:.2f}ms"
        assert operation_times['bs_greeks']['avg'] < 100, f"BS Greeks average time too high: {operation_times['bs_greeks']['avg']:.2f}ms"
        
        # Overall throughput check
        total_operations = len(operations) * 20
        avg_time_per_operation = total_time / total_operations
        assert avg_time_per_operation < 75, f"Average time per operation {avg_time_per_operation:.2f}ms too high"
        
    def test_stress_test_performance(self):
        """Stress test with high volume of calculations"""
        num_iterations = 500
        start_time = time.perf_counter()
        
        for i in range(num_iterations):
            # Vary parameters slightly to avoid caching effects
            s_var = self.s + (i % 10) * 0.1
            k_var = self.k + (i % 15) * 0.2
            
            # Mix of operations
            if i % 4 == 0:
                pricing_engine.price_call(s_var, k_var, self.tau, self.r, self.sigma)
            elif i % 4 == 1:
                pricing_engine.price_put(s_var, k_var, self.tau, self.r, self.sigma)
            elif i % 4 == 2:
                pricing_engine.price_call_fft_optimized(s_var, k_var, self.tau, self.r, self.sigma)
            else:
                pricing_engine.calculate_bs_call_greeks(s_var, k_var, self.tau, self.r, self.sigma)
        
        total_elapsed = (time.perf_counter() - start_time) * 1000
        avg_time_per_calc = total_elapsed / num_iterations
        
        assert avg_time_per_calc < 10, f"Stress test average time {avg_time_per_calc:.2f}ms per calculation too high"
        assert total_elapsed < 5000, f"Stress test total time {total_elapsed:.0f}ms too high (should be under 5000ms)"


class TestPerformanceRegression:
    """Performance regression detection tests"""
    
    def test_performance_baseline_establishment(self):
        """Establish performance baselines for regression detection"""
        s, k, tau, r, sigma = 100.0, 100.0, 0.25, 0.05, 0.2
        
        # Measure baseline performance for key operations
        baselines = {}
        
        # Black-Scholes call
        times = []
        for _ in range(100):
            start = time.perf_counter()
            pricing_engine.price_call(s, k, tau, r, sigma)
            times.append((time.perf_counter() - start) * 1000)
        baselines['bs_call'] = statistics.median(times)
        
        # FFT optimized call
        times = []
        for _ in range(50):
            start = time.perf_counter()
            pricing_engine.price_call_fft_optimized(s, k, tau, r, sigma)
            times.append((time.perf_counter() - start) * 1000)
        baselines['fft_call'] = statistics.median(times)
        
        # BS Greeks
        times = []
        for _ in range(100):
            start = time.perf_counter()
            pricing_engine.calculate_bs_call_greeks(s, k, tau, r, sigma)
            times.append((time.perf_counter() - start) * 1000)
        baselines['bs_greeks'] = statistics.median(times)
        
        # Print baselines for reference
        print(f"\nPerformance Baselines:")
        print(f"Black-Scholes Call: {baselines['bs_call']:.3f}ms")
        print(f"FFT Optimized Call: {baselines['fft_call']:.3f}ms")
        print(f"BS Greeks: {baselines['bs_greeks']:.3f}ms")
        
        # Verify baselines are within acceptable ranges
        assert baselines['bs_call'] < 10, f"BS call baseline {baselines['bs_call']:.3f}ms too high"
        assert baselines['fft_call'] < 50, f"FFT call baseline {baselines['fft_call']:.3f}ms too high"
        assert baselines['bs_greeks'] < 20, f"BS Greeks baseline {baselines['bs_greeks']:.3f}ms too high"


class TestParallelProcessingPerformance:
    """Test parallel processing optimizations"""
    
    def setup_method(self):
        """Set up test parameters"""
        self.s = 100.0
        self.k = 100.0
        self.tau = 0.25
        self.r = 0.05
        self.sigma = 0.2
        
    def test_sequential_vs_parallel_batch_pricing(self):
        """Compare sequential vs parallel batch pricing performance"""
        num_calculations = 100
        strikes = [90 + i * 0.2 for i in range(num_calculations)]
        
        # Sequential execution
        start_time = time.perf_counter()
        sequential_results = []
        for strike in strikes:
            result = pricing_engine.price_call(self.s, strike, self.tau, self.r, self.sigma)
            sequential_results.append(result)
        sequential_time = (time.perf_counter() - start_time) * 1000
        
        # Parallel execution using ThreadPoolExecutor
        start_time = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(pricing_engine.price_call, self.s, strike, self.tau, self.r, self.sigma)
                for strike in strikes
            ]
            parallel_results = [future.result() for future in concurrent.futures.as_completed(futures)]
        parallel_time = (time.perf_counter() - start_time) * 1000
        
        # Verify results are consistent
        assert len(sequential_results) == len(parallel_results)
        assert all(abs(a - b) < 1e-10 for a, b in zip(sorted(sequential_results), sorted(parallel_results)))
        
        # Performance comparison
        speedup = sequential_time / parallel_time if parallel_time > 0 else 0
        print(f"\nBatch Pricing Performance:")
        print(f"Sequential: {sequential_time:.2f}ms")
        print(f"Parallel: {parallel_time:.2f}ms")
        print(f"Speedup: {speedup:.2f}x")
        
        # Parallel should be faster for large batches (allowing some overhead)
        # Note: For very fast operations, parallel overhead may exceed benefits
        if num_calculations >= 50 and sequential_time > 100:  # Only expect speedup for slower operations
            assert speedup > 1.2, f"Parallel processing speedup {speedup:.2f}x insufficient for {num_calculations} calculations"
        else:
            # For fast operations, just verify parallel execution works
            assert speedup > 0.5, f"Parallel processing severely degraded performance: {speedup:.2f}x"
    
    def test_memory_efficient_batch_processing(self):
        """Test memory efficiency in batch processing"""
        num_calculations = 1000
        
        # Monitor memory usage during batch processing
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Process large batch
        start_time = time.perf_counter()
        for i in range(num_calculations):
            strike = 90 + (i % 100) * 0.2
            pricing_engine.price_call(self.s, strike, self.tau, self.r, self.sigma)
            
            # Force garbage collection every 100 iterations
            if i % 100 == 0:
                gc.collect()
        
        processing_time = (time.perf_counter() - start_time) * 1000
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        print(f"\nMemory Efficiency Test:")
        print(f"Initial memory: {initial_memory:.2f}MB")
        print(f"Final memory: {final_memory:.2f}MB")
        print(f"Memory increase: {memory_increase:.2f}MB")
        print(f"Processing time: {processing_time:.2f}ms")
        print(f"Time per calculation: {processing_time/num_calculations:.3f}ms")
        
        # Memory increase should be reasonable
        assert memory_increase < 50, f"Memory increase {memory_increase:.2f}MB too high for {num_calculations} calculations"
        
        # Average time per calculation should be efficient
        avg_time = processing_time / num_calculations
        assert avg_time < 1.0, f"Average time per calculation {avg_time:.3f}ms too high"


class TestCriticalPathOptimization:
    """Test optimizations for critical calculation paths"""
    
    def setup_method(self):
        """Set up test parameters"""
        self.s = 100.0
        self.k = 100.0
        self.tau = 0.25
        self.r = 0.05
        self.sigma = 0.2
        
    def test_hot_path_performance(self):
        """Test performance of most frequently used calculations"""
        # Simulate hot path: at-the-money options with standard parameters
        num_iterations = 1000
        
        operations = [
            ("bs_call", lambda: pricing_engine.price_call(self.s, self.k, self.tau, self.r, self.sigma)),
            ("bs_put", lambda: pricing_engine.price_put(self.s, self.k, self.tau, self.r, self.sigma)),
            ("bs_delta", lambda: pricing_engine.calculate_bs_call_greeks(self.s, self.k, self.tau, self.r, self.sigma).delta),
        ]
        
        hot_path_times = {}
        
        for op_name, op_func in operations:
            # Warmup
            for _ in range(10):
                op_func()
            
            # Measure hot path performance
            times = []
            for _ in range(num_iterations):
                start = time.perf_counter()
                result = op_func()
                elapsed = (time.perf_counter() - start) * 1000
                times.append(elapsed)
            
            hot_path_times[op_name] = {
                'min': min(times),
                'max': max(times),
                'mean': statistics.mean(times),
                'median': statistics.median(times),
                'p95': sorted(times)[int(0.95 * len(times))],
                'p99': sorted(times)[int(0.99 * len(times))]
            }
        
        # Print hot path performance metrics
        print(f"\nHot Path Performance (μs):")
        for op_name, metrics in hot_path_times.items():
            print(f"{op_name}:")
            print(f"  Min: {metrics['min']*1000:.1f}μs")
            print(f"  Median: {metrics['median']*1000:.1f}μs")
            print(f"  Mean: {metrics['mean']*1000:.1f}μs")
            print(f"  P95: {metrics['p95']*1000:.1f}μs")
            print(f"  P99: {metrics['p99']*1000:.1f}μs")
        
        # Hot path performance requirements (adjusted for realistic performance)
        assert hot_path_times['bs_call']['median'] < 1.0, f"BS call hot path median {hot_path_times['bs_call']['median']:.3f}ms too slow"
        assert hot_path_times['bs_put']['median'] < 1.0, f"BS put hot path median {hot_path_times['bs_put']['median']:.3f}ms too slow"
        assert hot_path_times['bs_delta']['median'] < 1.0, f"BS delta hot path median {hot_path_times['bs_delta']['median']:.3f}ms too slow"
    
    def test_parameter_variation_performance(self):
        """Test performance across different parameter ranges"""
        base_params = [self.s, self.k, self.tau, self.r, self.sigma]
        
        # Test different volatility levels (affects calculation complexity)
        volatilities = [0.05, 0.1, 0.2, 0.5, 1.0, 2.0]
        vol_times = []
        
        for vol in volatilities:
            times = []
            for _ in range(50):
                start = time.perf_counter()
                pricing_engine.price_call(self.s, self.k, self.tau, self.r, vol)
                times.append((time.perf_counter() - start) * 1000)
            vol_times.append(statistics.median(times))
        
        # Test different time to expiration (affects numerical stability)
        expirations = [0.01, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0]
        exp_times = []
        
        for tau in expirations:
            times = []
            for _ in range(50):
                start = time.perf_counter()
                pricing_engine.price_call(self.s, self.k, tau, self.r, self.sigma)
                times.append((time.perf_counter() - start) * 1000)
            exp_times.append(statistics.median(times))
        
        # Test different moneyness levels
        moneyness_levels = [0.5, 0.8, 0.9, 1.0, 1.1, 1.2, 1.5, 2.0]
        moneyness_times = []
        
        for moneyness in moneyness_levels:
            strike = self.s * moneyness
            times = []
            for _ in range(50):
                start = time.perf_counter()
                pricing_engine.price_call(self.s, strike, self.tau, self.r, self.sigma)
                times.append((time.perf_counter() - start) * 1000)
            moneyness_times.append(statistics.median(times))
        
        print(f"\nParameter Variation Performance:")
        print(f"Volatility range: {min(vol_times):.3f}ms - {max(vol_times):.3f}ms")
        print(f"Expiration range: {min(exp_times):.3f}ms - {max(exp_times):.3f}ms")
        print(f"Moneyness range: {min(moneyness_times):.3f}ms - {max(moneyness_times):.3f}ms")
        
        # Performance should be consistent across parameter ranges
        assert max(vol_times) < 1.0, f"Max volatility time {max(vol_times):.3f}ms too high"
        assert max(exp_times) < 1.0, f"Max expiration time {max(exp_times):.3f}ms too high"
        assert max(moneyness_times) < 1.0, f"Max moneyness time {max(moneyness_times):.3f}ms too high"
        
        # Variation should be reasonable (no extreme outliers)
        vol_variation = max(vol_times) / min(vol_times)
        exp_variation = max(exp_times) / min(exp_times)
        moneyness_variation = max(moneyness_times) / min(moneyness_times)
        
        assert vol_variation < 5.0, f"Volatility performance variation {vol_variation:.2f}x too high"
        assert exp_variation < 5.0, f"Expiration performance variation {exp_variation:.2f}x too high"
        assert moneyness_variation < 3.0, f"Moneyness performance variation {moneyness_variation:.2f}x too high"


class TestPerformanceMonitoring:
    """Test performance monitoring and benchmarking capabilities"""
    
    def test_performance_profiling(self):
        """Profile performance of different pricing models"""
        models = [
            ("Black-Scholes Call", lambda: pricing_engine.price_call(100, 100, 0.25, 0.05, 0.2)),
            ("Black-Scholes Put", lambda: pricing_engine.price_put(100, 100, 0.25, 0.05, 0.2)),
            ("FFT Optimized Call", lambda: pricing_engine.price_call_fft_optimized(100, 100, 0.25, 0.05, 0.2)),
            ("FFT Optimized Put", lambda: pricing_engine.price_put_fft_optimized(100, 100, 0.25, 0.05, 0.2)),
            ("Heston Call", lambda: pricing_engine.price_heston_call(100, 100, 0.04, 0.05, 2.0, 0.04, 0.3, -0.7, 0.25)),
            ("BS Greeks", lambda: pricing_engine.calculate_bs_call_greeks(100, 100, 0.25, 0.05, 0.2)),
        ]
        
        profile_results = {}
        
        for model_name, model_func in models:
            # Warmup
            for _ in range(5):
                model_func()
            
            # Profile execution
            times = []
            for _ in range(100):
                start = time.perf_counter()
                result = model_func()
                elapsed = (time.perf_counter() - start) * 1000
                times.append(elapsed)
            
            profile_results[model_name] = {
                'min': min(times),
                'max': max(times),
                'mean': statistics.mean(times),
                'median': statistics.median(times),
                'std': statistics.stdev(times),
                'p95': sorted(times)[int(0.95 * len(times))],
                'p99': sorted(times)[int(0.99 * len(times))]
            }
        
        # Print comprehensive performance profile
        print(f"\nPerformance Profile:")
        print(f"{'Model':<20} {'Min':<8} {'Median':<8} {'Mean':<8} {'P95':<8} {'P99':<8} {'Max':<8} {'Std':<8}")
        print("-" * 80)
        
        for model_name, metrics in profile_results.items():
            print(f"{model_name:<20} "
                  f"{metrics['min']:<8.3f} "
                  f"{metrics['median']:<8.3f} "
                  f"{metrics['mean']:<8.3f} "
                  f"{metrics['p95']:<8.3f} "
                  f"{metrics['p99']:<8.3f} "
                  f"{metrics['max']:<8.3f} "
                  f"{metrics['std']:<8.3f}")
        
        # Verify performance targets (adjusted for realistic performance)
        assert profile_results['Black-Scholes Call']['p95'] < 5.0, "BS Call P95 performance target missed"
        assert profile_results['FFT Optimized Call']['p95'] < 50.0, "FFT Call P95 performance target missed"
        assert profile_results['Heston Call']['p95'] < 400.0, "Heston Call P95 performance target missed"
        assert profile_results['BS Greeks']['p95'] < 10.0, "BS Greeks P95 performance target missed"
    
    def test_throughput_benchmarking(self):
        """Benchmark throughput for different workload patterns"""
        
        # High-frequency trading simulation (simple calculations)
        hft_operations = 10000
        start_time = time.perf_counter()
        for i in range(hft_operations):
            strike = 99 + (i % 100) * 0.02  # Small variations
            pricing_engine.price_call(100, strike, 0.25, 0.05, 0.2)
        hft_time = time.perf_counter() - start_time
        hft_throughput = hft_operations / hft_time
        
        # Risk management simulation (Greeks calculations)
        risk_operations = 1000
        start_time = time.perf_counter()
        for i in range(risk_operations):
            strike = 90 + (i % 200) * 0.1
            pricing_engine.calculate_bs_call_greeks(100, strike, 0.25, 0.05, 0.2)
        risk_time = time.perf_counter() - start_time
        risk_throughput = risk_operations / risk_time
        
        # Portfolio valuation simulation (mixed models)
        portfolio_operations = 500
        start_time = time.perf_counter()
        for i in range(portfolio_operations):
            strike = 85 + (i % 300) * 0.1
            if i % 4 == 0:
                pricing_engine.price_call(100, strike, 0.25, 0.05, 0.2)
            elif i % 4 == 1:
                pricing_engine.price_put(100, strike, 0.25, 0.05, 0.2)
            elif i % 4 == 2:
                pricing_engine.price_call_fft_optimized(100, strike, 0.25, 0.05, 0.2)
            else:
                pricing_engine.calculate_bs_call_greeks(100, strike, 0.25, 0.05, 0.2)
        portfolio_time = time.perf_counter() - start_time
        portfolio_throughput = portfolio_operations / portfolio_time
        
        print(f"\nThroughput Benchmarks:")
        print(f"High-Frequency Trading: {hft_throughput:.0f} ops/sec ({hft_operations} operations in {hft_time:.3f}s)")
        print(f"Risk Management: {risk_throughput:.0f} ops/sec ({risk_operations} operations in {risk_time:.3f}s)")
        print(f"Portfolio Valuation: {portfolio_throughput:.0f} ops/sec ({portfolio_operations} operations in {portfolio_time:.3f}s)")
        
        # Throughput requirements (adjusted for realistic performance)
        assert hft_throughput >= 1000, f"HFT throughput {hft_throughput:.0f} ops/sec below requirement (1k ops/sec)"
        assert risk_throughput >= 500, f"Risk management throughput {risk_throughput:.0f} ops/sec below requirement (500 ops/sec)"
        assert portfolio_throughput >= 200, f"Portfolio throughput {portfolio_throughput:.0f} ops/sec below requirement (200 ops/sec)"


if __name__ == "__main__":
    # Run with verbose output and timing information
    pytest.main([__file__, "-v", "-s", "--tb=short"])