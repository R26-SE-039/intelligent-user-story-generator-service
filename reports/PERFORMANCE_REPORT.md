# Performance Report: Intelligent User Story Generator Service

Generated: 2026-08-28 12:46:19 UTC

## Stage A: ModernBERT NLP Classifier Benchmark

### Single Utterance Latency (100 iterations, post warm-up)

| Metric   |   Value (ms) |
|----------|--------------|
| Min      |         0.92 |
| Max      |         2.01 |
| Mean     |         1.12 |
| StdDev   |         0.18 |
| P50      |         1.08 |
| P95      |         1.44 |
| P99      |         1.98 |


### Batch Inference: Throughput & Latency

|   Batch Size |   Mean (ms) |   P50 (ms) |   P95 (ms) |   P99 (ms) |   Throughput (utt/s) |   DELTA RAM (MB) |
|--------------|-------------|------------|------------|------------|----------------------|------------------|
|            1 |        1.1  |       1.08 |       1.36 |       1.58 |                910.1 |              0   |
|            8 |        9.32 |       9.31 |      10.25 |      10.85 |                858.1 |             -0.5 |
|           16 |       20.23 |      19.88 |      22.58 |      24.07 |                791   |              0   |
|           32 |       40.65 |      40.17 |      43.2  |      43.67 |                787.2 |              0   |
|           64 |       78.38 |      78.47 |      81.06 |      83.73 |                816.5 |              0   |

## Stage B: FastAPI Endpoint Benchmark

| Endpoint   | P50 (ms)   | P90 (ms)   | P95 (ms)   | P99 (ms)   | RPS   | Error %             |
|------------|------------|------------|------------|------------|-------|---------------------|
| HEALTH     | N/A        | N/A        | N/A        | N/A        | N/A   | All requests failed |
| PIPELINE   | N/A        | N/A        | N/A        | N/A        | N/A   | All requests failed |

## Stage C: Concurrency / Load Test

|   Concurrent Users |   Mean (ms) |   P95 (ms) |   RPS | Error %   |   Peak RAM (MB) |
|--------------------|-------------|------------|-------|-----------|-----------------|
|                 25 |          -1 |         -1 |  10.5 | 100.0%    |            46.7 |
|                 50 |          -1 |         -1 |  21.6 | 100.0%    |            48.1 |
|                100 |          -1 |         -1 |  43.1 | 100.0%    |            50.2 |
|                200 |          -1 |         -1 |  41.1 | 100.0%    |            51.8 |

---
Benchmarking suite authored for NextGenQA research CI/CD pipeline.