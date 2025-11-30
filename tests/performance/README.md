# Performance Benchmarks

Performance benchmarks for CodeWarden to detect performance regressions.

## Overview

This test suite measures the performance of critical code paths:
- **Diff Parsing** - Parsing Git diffs of various sizes
- **Response Caching** - Hash generation and cache operations
- **Idempotency Checking** - Request ID generation and deduplication
- **Token Counting** - Prompt building and token estimation
- **Circuit Breaker** - State management overhead
- **Model Operations** - Pydantic model creation and validation

## Running Benchmarks

### Run All Benchmarks

```bash
pytest tests/performance/test_benchmarks.py --benchmark-only
```

### Run Specific Group

```bash
pytest tests/performance/test_benchmarks.py --benchmark-only -k "diff-parsing"
pytest tests/performance/test_benchmarks.py --benchmark-only -k "cache"
pytest tests/performance/test_benchmarks.py --benchmark-only -k "circuit-breaker"
```

### Save Baseline

```bash
pytest tests/performance/test_benchmarks.py --benchmark-only --benchmark-save=baseline
```

### Compare Against Baseline

```bash
pytest tests/performance/test_benchmarks.py --benchmark-only --benchmark-compare=baseline
```

### Generate HTML Report

```bash
pytest tests/performance/test_benchmarks.py --benchmark-only --benchmark-html=benchmark_report.html
```

## Performance Thresholds

Target performance for key operations:

| Operation | Target | Critical Threshold |
|-----------|--------|-------------------|
| Small diff parsing | <1ms | <5ms |
| Medium diff parsing | <10ms | <50ms |
| Large diff parsing | <100ms | <500ms |
| Cache hash generation | <1ms | <5ms |
| Request ID generation | <0.1ms | <1ms |
| Circuit breaker check | <0.1ms | <1ms |
| Token estimation | <1ms | <5ms |
| Prompt building | <10ms | <50ms |

## Interpreting Results

### Benchmark Output

```
Name (time in ms)                Min      Max     Mean    StdDev
test_parse_small_diff          0.5000   0.6000   0.5500   0.0200
test_cache_hash_generation     0.3000   0.4000   0.3500   0.0150
```

- **Min**: Fastest execution time
- **Max**: Slowest execution time
- **Mean**: Average execution time
- **StdDev**: Standard deviation (consistency)

### Regression Detection

A performance regression is indicated when:
1. Mean execution time increases >20% from baseline
2. Max execution time exceeds critical threshold
3. StdDev increases significantly (inconsistent performance)

## Adding New Benchmarks

1. Create test method with `@pytest.mark.benchmark` decorator
2. Use `benchmark` fixture to wrap the operation
3. Add performance threshold to `PERFORMANCE_THRESHOLDS` dict
4. Update this README with the new benchmark

Example:

```python
@pytest.mark.benchmark(group="my-feature")
def test_my_operation(self, benchmark):
    """Benchmark my operation."""

    def operation():
        # Your operation here
        return my_function()

    result = benchmark(operation)
    assert result is not None
```

## CI/CD Integration

Benchmarks run automatically in CI/CD:
- On every pull request (comparison mode)
- On main branch commits (baseline update)
- Nightly (trend analysis)

Alerts triggered when:
- Mean execution time >20% above baseline
- Any operation exceeds critical threshold
- Consistent degradation over 3+ commits

## Profiling for Deeper Analysis

For detailed profiling of slow operations:

```bash
# CPU profiling
python -m cProfile -o profile.stats your_script.py
python -m pstats profile.stats

# Memory profiling
python -m memory_profiler your_script.py

# Line-by-line profiling
kernprof -l -v your_script.py
```

## Optimization Tips

### Diff Parsing
- Use compiled regex patterns
- Minimize string allocations
- Process line-by-line vs loading entire diff

### Caching
- Use efficient hash algorithms (SHA256 is fast)
- Minimize serialization overhead
- Batch cache operations when possible

### Token Counting
- Cache token counts for repeated text
- Use approximate counting for estimates
- Avoid tokenizing full prompts unnecessarily

### Circuit Breaker
- Keep state in memory (no I/O)
- Use simple counters vs complex logic
- Minimize lock contention

## Dependencies

```bash
pip install pytest-benchmark pytest-asyncio
```

## References

- [pytest-benchmark docs](https://pytest-benchmark.readthedocs.io/)
- [Python Performance Tips](https://wiki.python.org/moin/PythonSpeed/PerformanceTips)
- [Azure Functions Performance](https://docs.microsoft.com/en-us/azure/azure-functions/functions-best-practices)
