"""
API endpoint performance tests.

This module tests the performance of HTTP API endpoints to ensure they meet
response time requirements under various load conditions.

Requirements: 6.1, 6.2, 6.3
"""

import pytest
import asyncio
import aiohttp
import time
import statistics
import json
from concurrent.futures import ThreadPoolExecutor
import sys
import os

# Add the parent directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Test configuration
BASE_URL = "http://localhost:8000"
TIMEOUT = aiohttp.ClientTimeout(total=30)


class TestAPIPerformance:
    """Performance tests for API endpoints"""
    
    @pytest.fixture(scope="class")
    def event_loop(self):
        """Create an event loop for async tests"""
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()
    
    @pytest.fixture
    def sample_option_request(self):
        """Standard option pricing request"""
        return {
            "s": 100.0,
            "k": 100.0,
            "tau": 0.25,
            "r": 0.05,
            "sigma": 0.2
        }
    
    @pytest.fixture
    def sample_heston_request(self):
        """Standard Heston model request"""
        return {
            "s": 100.0,
            "k": 100.0,
            "tau": 0.25,
            "r": 0.05,
            "v0": 0.04,
            "theta": 0.04,
            "kappa": 2.0,
            "sigma_v": 0.3,
            "rho": -0.7
        }
    
    @pytest.fixture
    def sample_greeks_request(self):
        """Standard Greeks calculation request"""
        return {
            "s": 100.0,
            "k": 100.0,
            "tau": 0.25,
            "r": 0.05,
            "sigma": 0.2,
            "model": "bs"
        }
    
    async def make_request(self, session, endpoint, data):
        """Make a single API request and measure response time"""
        start_time = time.perf_counter()
        try:
            async with session.post(f"{BASE_URL}{endpoint}", json=data) as response:
                result = await response.json()
                elapsed = (time.perf_counter() - start_time) * 1000  # Convert to ms
                return {
                    'success': response.status == 200,
                    'elapsed_ms': elapsed,
                    'status_code': response.status,
                    'result': result
                }
        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            return {
                'success': False,
                'elapsed_ms': elapsed,
                'error': str(e)
            }
    
    @pytest.mark.asyncio
    async def test_black_scholes_call_performance(self, sample_option_request):
        """Test Black-Scholes call pricing performance"""
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            result = await self.make_request(session, "/price/call/bs", sample_option_request)
            
            assert result['success'], f"Request failed: {result.get('error', 'Unknown error')}"
            assert result['elapsed_ms'] < 100, f"BS call pricing took {result['elapsed_ms']:.2f}ms, should be under 100ms"
            assert 'price' in result['result'], "Response should contain price"
    
    @pytest.mark.asyncio
    async def test_black_scholes_put_performance(self, sample_option_request):
        """Test Black-Scholes put pricing performance"""
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            result = await self.make_request(session, "/price/put/bs", sample_option_request)
            
            assert result['success'], f"Request failed: {result.get('error', 'Unknown error')}"
            assert result['elapsed_ms'] < 100, f"BS put pricing took {result['elapsed_ms']:.2f}ms, should be under 100ms"
            assert 'price' in result['result'], "Response should contain price"
    
    @pytest.mark.asyncio
    async def test_fft_optimized_call_performance(self, sample_option_request):
        """Test FFT optimized call pricing performance"""
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            result = await self.make_request(session, "/price/call/fft-optimized", sample_option_request)
            
            assert result['success'], f"Request failed: {result.get('error', 'Unknown error')}"
            assert result['elapsed_ms'] < 150, f"FFT call pricing took {result['elapsed_ms']:.2f}ms, should be under 150ms"
            assert 'price' in result['result'], "Response should contain price"
    
    @pytest.mark.asyncio
    async def test_heston_call_performance(self, sample_heston_request):
        """Test Heston call pricing performance"""
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            result = await self.make_request(session, "/price/call/heston", sample_heston_request)
            
            assert result['success'], f"Request failed: {result.get('error', 'Unknown error')}"
            assert result['elapsed_ms'] < 600, f"Heston call pricing took {result['elapsed_ms']:.2f}ms, should be under 600ms"
            assert 'price' in result['result'], "Response should contain price"
    
    @pytest.mark.asyncio
    async def test_greeks_calculation_performance(self, sample_greeks_request):
        """Test Greeks calculation performance"""
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            result = await self.make_request(session, "/greeks/call", sample_greeks_request)
            
            assert result['success'], f"Request failed: {result.get('error', 'Unknown error')}"
            assert result['elapsed_ms'] < 100, f"Greeks calculation took {result['elapsed_ms']:.2f}ms, should be under 100ms"
            assert 'greeks' in result['result'], "Response should contain greeks"
    
    @pytest.mark.asyncio
    async def test_concurrent_requests_performance(self, sample_option_request):
        """Test performance under concurrent load"""
        num_concurrent = 50
        
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            # Create concurrent requests
            tasks = []
            for i in range(num_concurrent):
                # Vary strike prices to avoid caching effects
                request_data = sample_option_request.copy()
                request_data['k'] = 95 + (i % 10) * 1.0
                
                task = self.make_request(session, "/price/call/bs", request_data)
                tasks.append(task)
            
            # Execute all requests concurrently
            start_time = time.perf_counter()
            results = await asyncio.gather(*tasks)
            total_elapsed = (time.perf_counter() - start_time) * 1000
            
            # Analyze results
            successful_results = [r for r in results if r['success']]
            response_times = [r['elapsed_ms'] for r in successful_results]
            
            assert len(successful_results) >= num_concurrent * 0.95, f"Too many failed requests: {len(successful_results)}/{num_concurrent}"
            
            avg_response_time = statistics.mean(response_times)
            p95_response_time = sorted(response_times)[int(0.95 * len(response_times))]
            max_response_time = max(response_times)
            
            assert avg_response_time < 150, f"Average concurrent response time {avg_response_time:.2f}ms too high"
            assert p95_response_time < 200, f"95th percentile response time {p95_response_time:.2f}ms too high"
            assert total_elapsed < 5000, f"Total concurrent execution time {total_elapsed:.0f}ms too high"
    
    @pytest.mark.asyncio
    async def test_mixed_workload_performance(self, sample_option_request, sample_heston_request, sample_greeks_request):
        """Test performance with mixed API workload"""
        num_iterations = 30
        
        # Define workload mix
        workload = [
            ("/price/call/bs", sample_option_request, 100),  # (endpoint, data, max_time_ms)
            ("/price/put/bs", sample_option_request, 100),
            ("/price/call/fft-optimized", sample_option_request, 150),
            ("/greeks/call", sample_greeks_request, 100),
            ("/price/call/heston", sample_heston_request, 600),
        ]
        
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            tasks = []
            
            for i in range(num_iterations):
                # Select operation based on realistic distribution
                if i % 10 < 4:  # 40% Black-Scholes
                    endpoint, data, max_time = workload[0]
                elif i % 10 < 7:  # 30% FFT
                    endpoint, data, max_time = workload[2]
                elif i % 10 < 9:  # 20% Greeks
                    endpoint, data, max_time = workload[3]
                else:  # 10% Heston
                    endpoint, data, max_time = workload[4]
                
                # Vary parameters slightly
                request_data = data.copy()
                if 'k' in request_data:
                    request_data['k'] = 95 + (i % 15) * 0.7
                
                task = self.make_request(session, endpoint, request_data)
                tasks.append((task, max_time))
            
            # Execute mixed workload
            start_time = time.perf_counter()
            results_with_limits = await asyncio.gather(*[task for task, _ in tasks])
            total_elapsed = (time.perf_counter() - start_time) * 1000
            
            # Verify individual operation performance
            for i, (result, (_, max_time)) in enumerate(zip(results_with_limits, tasks)):
                assert result['success'], f"Request {i} failed: {result.get('error', 'Unknown error')}"
                # Allow some tolerance for mixed workload
                tolerance_factor = 1.5
                assert result['elapsed_ms'] < max_time * tolerance_factor, \
                    f"Request {i} took {result['elapsed_ms']:.2f}ms, should be under {max_time * tolerance_factor:.0f}ms"
            
            # Overall performance metrics
            response_times = [r['elapsed_ms'] for r in results_with_limits]
            avg_response_time = statistics.mean(response_times)
            
            assert avg_response_time < 200, f"Mixed workload average response time {avg_response_time:.2f}ms too high"
            assert total_elapsed < 15000, f"Mixed workload total time {total_elapsed:.0f}ms too high"
    
    @pytest.mark.asyncio
    async def test_health_check_performance(self):
        """Test health check endpoint performance"""
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            result = await self.make_request(session, "/health", {})
            
            assert result['success'], f"Health check failed: {result.get('error', 'Unknown error')}"
            assert result['elapsed_ms'] < 50, f"Health check took {result['elapsed_ms']:.2f}ms, should be under 50ms"
    
    @pytest.mark.asyncio
    async def test_model_comparison_performance(self, sample_option_request):
        """Test model comparison endpoint performance"""
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            result = await self.make_request(session, "/compare/models", sample_option_request)
            
            assert result['success'], f"Model comparison failed: {result.get('error', 'Unknown error')}"
            assert result['elapsed_ms'] < 300, f"Model comparison took {result['elapsed_ms']:.2f}ms, should be under 300ms"
            assert 'results' in result['result'], "Response should contain results"


class TestAPIStressTest:
    """Stress testing for API endpoints"""
    
    @pytest.mark.asyncio
    async def test_sustained_load_performance(self):
        """Test performance under sustained load"""
        duration_seconds = 10
        requests_per_second = 20
        total_requests = duration_seconds * requests_per_second
        
        request_data = {
            "s": 100.0,
            "k": 100.0,
            "tau": 0.25,
            "r": 0.05,
            "sigma": 0.2
        }
        
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            start_time = time.perf_counter()
            
            # Create batches of requests to maintain steady rate
            batch_size = 10
            batches = total_requests // batch_size
            
            all_results = []
            
            for batch in range(batches):
                batch_start = time.perf_counter()
                
                # Create batch of concurrent requests
                tasks = []
                for i in range(batch_size):
                    # Vary parameters to avoid caching
                    data = request_data.copy()
                    data['k'] = 95 + ((batch * batch_size + i) % 20) * 0.5
                    
                    task = self.make_request(session, "/price/call/bs", data)
                    tasks.append(task)
                
                # Execute batch
                batch_results = await asyncio.gather(*tasks)
                all_results.extend(batch_results)
                
                # Rate limiting - ensure we don't exceed target RPS
                batch_elapsed = time.perf_counter() - batch_start
                target_batch_time = batch_size / requests_per_second
                if batch_elapsed < target_batch_time:
                    await asyncio.sleep(target_batch_time - batch_elapsed)
            
            total_elapsed = time.perf_counter() - start_time
            
            # Analyze results
            successful_results = [r for r in all_results if r['success']]
            response_times = [r['elapsed_ms'] for r in successful_results]
            
            success_rate = len(successful_results) / len(all_results)
            avg_response_time = statistics.mean(response_times)
            p95_response_time = sorted(response_times)[int(0.95 * len(response_times))]
            actual_rps = len(all_results) / total_elapsed
            
            # Performance assertions
            assert success_rate >= 0.95, f"Success rate {success_rate:.2%} too low"
            assert avg_response_time < 100, f"Average response time {avg_response_time:.2f}ms too high under load"
            assert p95_response_time < 200, f"95th percentile response time {p95_response_time:.2f}ms too high under load"
            assert actual_rps >= requests_per_second * 0.9, f"Actual RPS {actual_rps:.1f} too low"
    
    @pytest.mark.asyncio
    async def test_burst_load_performance(self):
        """Test performance under burst load conditions"""
        burst_size = 100
        
        request_data = {
            "s": 100.0,
            "k": 100.0,
            "tau": 0.25,
            "r": 0.05,
            "sigma": 0.2
        }
        
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            # Create burst of requests
            tasks = []
            for i in range(burst_size):
                data = request_data.copy()
                data['k'] = 90 + (i % 30) * 0.7  # Vary strikes
                
                task = self.make_request(session, "/price/call/bs", data)
                tasks.append(task)
            
            # Execute burst
            start_time = time.perf_counter()
            results = await asyncio.gather(*tasks)
            total_elapsed = (time.perf_counter() - start_time) * 1000
            
            # Analyze burst performance
            successful_results = [r for r in results if r['success']]
            response_times = [r['elapsed_ms'] for r in successful_results]
            
            success_rate = len(successful_results) / len(results)
            avg_response_time = statistics.mean(response_times)
            max_response_time = max(response_times)
            
            # Burst performance assertions (more lenient than sustained load)
            assert success_rate >= 0.90, f"Burst success rate {success_rate:.2%} too low"
            assert avg_response_time < 200, f"Burst average response time {avg_response_time:.2f}ms too high"
            assert max_response_time < 500, f"Burst max response time {max_response_time:.2f}ms too high"
            assert total_elapsed < 10000, f"Burst total time {total_elapsed:.0f}ms too high"


if __name__ == "__main__":
    # Note: These tests require the API server to be running
    # Start the server with: uvicorn app.main:app --reload
    pytest.main([__file__, "-v", "-s", "--tb=short"])