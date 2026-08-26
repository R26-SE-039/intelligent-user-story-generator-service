# Intelligent User Story Generator Service — Testing Guide

Comprehensive technical documentation for running, extending, and maintaining the **Unit and Integration Testing Suite** for the Intelligent User Story Generator Service.

---

## 1. Executive Summary & Test Philosophy

The testing suite is designed with **100% in-memory isolation**, ensuring fast, repeatable, and reliable test execution across developer workstations and CI/CD pipelines without requiring live external services.

- **Zero Live Dependencies Required**: Tests execute without live connections to PostgreSQL, Azure Speech Service, Gemini/LLM APIs, ChromaDB, or Jira Cloud.
- **Ultra-Fast Performance**: All **70 automated tests** run in **under 2 seconds** (`~1.94s`).
- **Heavy Module Pre-Stubbing**: Heavy native extensions (`azure.cognitiveservices.speech`) and machine learning libraries (`torch`, `transformers`) are pre-stubbed in `sys.modules` at collection time, preventing C-extension hangs and 5+ minute cold-start delays.

---

## 2. Directory & Fixture Structure

```
intelligent-user-story-generator-service/
├── pytest.ini                         # Global pytest configuration & flags
├── doc/
│   └── TESTING_GUIDE.md               # This documentation file
└── tests/
    ├── __init__.py
    ├── conftest.py                    # Shared fixtures, stubs & TestClient factory
    ├── unit/                          # Isolated unit test suites
    │   ├── __init__.py
    │   ├── test_security.py           # JWT security & claim extraction logic
    │   ├── test_formatter.py          # Filler word removal & whitespace normalization
    │   ├── test_helpers.py            # UTC ISO timestamp utilities
    │   ├── test_rule_validator.py     # Layer 1 structural rule validation
    │   ├── test_story_generator.py    # LLM story generation & JSON response parsing
    │   └── test_repositories.py       # Meeting & Requirement repository persistence
    └── integration/                   # FastAPI endpoint integration test suites
        ├── __init__.py
        ├── test_health_api.py         # Service liveness check (/health)
        ├── test_pipeline_api.py       # End-to-end pipeline & requirements endpoints
        └── test_jira_api.py           # Jira connection & story sync endpoints
```

---

## 3. Global Configuration (`pytest.ini`)

Location: [`pytest.ini`](file:///d:/SLIIT/SLIIT-SE-Y4S1-Academic-Resources/Research/NextGenQA/intelligent-user-story-generator-service/pytest.ini)

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short --import-mode=importlib -p no:langsmith
filterwarnings =
    ignore::DeprecationWarning
    ignore::PendingDeprecationWarning
```

### Key Configuration Flags:
- `--import-mode=importlib`: Prevents pytest module name collision issues when stubs are injected into `sys.modules`.
- `-p no:langsmith`: Disables the LangSmith tracing plugin to prevent blocking network hooks during test execution.
- `filterwarnings`: Silences noisy deprecation warnings from third-party libraries (e.g., PyJWT key length warnings).

---

## 4. Shared Test Infrastructure (`conftest.py`)

Location: [`tests/conftest.py`](file:///d:/SLIIT/SLIIT-SE-Y4S1-Academic-Resources/Research/NextGenQA/intelligent-user-story-generator-service/tests/conftest.py)

### Module Pre-Stubbing
To eliminate external startup latencies, `conftest.py` injects mock module objects into Python's `sys.modules` before any application code imports occur:

1. **PyTorch Stub (`torch`)**: Mocks `torch.no_grad()`, `torch.cuda.is_available()`, and `torch.Tensor`.
2. **Transformers Stub (`transformers`)**: Mocks `AutoTokenizer` and `AutoModelForSequenceClassification`.
3. **Azure Speech SDK Stub (`azure.cognitiveservices.speech`)**: Preserves the `azure` PEP-420 namespace package while injecting mock classes for `SpeechConfig`, `PushAudioInputStream`, and `SpeechRecognizer`.

### Key Reusable Fixtures:
- `mock_settings`: Returns a mock application configuration (`Settings`).
- `mock_jwt_token`: Generates a valid signed HS256 JWT bearer token containing `userId`, `email`, `role`, and `organizationId` claims.
- `mock_auth_headers`: Returns HTTP header dictionary `{"Authorization": "Bearer <token>"}`.
- `mock_gateway`: Returns a mocked `PostgresGateway` instance with default empty query return values.
- `client`: Provides a FastAPI `TestClient` initialized with a no-op lifespan context manager, bypassing real database/Azure connection attempts and wiring `client.app.dependency_overrides`.

---

## 5. Test Suite Details

### A. Unit Test Suite (`tests/unit/`)

#### 1. Security & Token Decoding ([`test_security.py`](file:///d:/SLIIT/SLIIT-SE-Y4S1-Academic-Resources/Research/NextGenQA/intelligent-user-story-generator-service/tests/unit/test_security.py))
- **`TestDecodeJwtValidToken`**: Verifies correct extraction of `userId`, `email`, `role`, and `organizationId`. Tests claim fallback from `userId` to `sub`.
- **`TestDecodeJwtInvalidToken`**: Verifies `None` return on incorrect signature secret, expired timestamps, malformed token strings, or missing user identification claims.

#### 2. Text Normalization & Formatting ([`test_formatter.py`](file:///d:/SLIIT/SLIIT-SE-Y4S1-Academic-Resources/Research/NextGenQA/intelligent-user-story-generator-service/tests/unit/test_formatter.py))
- **`TestNormalizeTextFillerWords`**: Verifies removal of speech filler words (`um`, `uh`, `you know`, `like`) across upper/lower case occurrences.
- **`TestNormalizeTextWhitespace`**: Verifies collapsing of multiple spaces, tabs, and newlines into single spaces, as well as leading/trailing trimming.
- **`TestNormalizeTextEdgeCases`**: Handles empty inputs and strings composed entirely of filler words.

#### 3. Common Helpers ([`test_helpers.py`](file:///d:/SLIIT/SLIIT-SE-Y4S1-Academic-Resources/Research/NextGenQA/intelligent-user-story-generator-service/tests/unit/test_helpers.py))
- **`TestUtcNow`**: Validates UTC ISO 8601 timestamp string generation, timezone awareness (`tzinfo` presence), UTC offset equality to 0, and monotonic time progression.

#### 4. Layer 1 Rule Validation ([`test_rule_validator.py`](file:///d:/SLIIT/SLIIT-SE-Y4S1-Academic-Resources/Research/NextGenQA/intelligent-user-story-generator-service/tests/unit/test_rule_validator.py))
- **`TestValidateRulesValidStory`**: Confirms well-structured user stories receive high quality scores (75.0–100.0) with zero high-severity issues.
- **`TestValidateRulesMissingClauses`**: Tests detection of missing "As a", "I want", or "So that" clauses, as well as empty story text.
- **`TestValidateRulesMissingFields`**: Tests detection of missing titles, missing acceptance criteria, and missing transcript evidence references (`unsupported_claim`).
- **`TestValidateRulesDuplicates`**: Flags duplicate story titles (case-insensitive) within a single batch.
- **`TestValidateRulesPenaltyScoring`**: Verifies severity penalty score deductions (`high`: -25, `medium`: -10, `low`: -5).

#### 5. Story Generator & LLM Response Parsing ([`test_story_generator.py`](file:///d:/SLIIT/SLIIT-SE-Y4S1-Academic-Resources/Research/NextGenQA/intelligent-user-story-generator-service/tests/unit/test_story_generator.py))
- **`TestStoryGeneratorFallback`**: Verifies local deterministic fallback story generation when LLM client is `None`.
- **`TestStoryGeneratorJsonParsing`**: Tests parsing of plain JSON responses, markdown code fences (` ```json ... ``` `), unwrapping raw JSON lists into `StoryBatch` objects, and error raising on malformed JSON.

#### 6. Database Repositories ([`test_repositories.py`](file:///d:/SLIIT/SLIIT-SE-Y4S1-Academic-Resources/Research/NextGenQA/intelligent-user-story-generator-service/tests/unit/test_repositories.py))
- **`TestMeetingRepositorySaveMeeting`**: Verifies upsert table targeting and dictionary parameter passing.
- **`TestMeetingRepositoryGetMeeting`**: Tests meeting retrieval by ID and returns `None` on missing records.
- **`TestRequirementRepositoryGetByMeeting`**: Tests query execution using psycopg2 cursor context manager mocks.
- **`TestRequirementRepositorySave`**: Validates batch upserts for list of `Requirement` domain objects.

---

### B. Integration Test Suite (`tests/integration/`)

#### 1. Health Endpoint ([`test_health_api.py`](file:///d:/SLIIT/SLIIT-SE-Y4S1-Academic-Resources/Research/NextGenQA/intelligent-user-story-generator-service/tests/integration/test_health_api.py))
- Verifies `GET /health` returns HTTP 200 OK, `{"status": "ok"}`, service title `intelligent-user-story-generator`, and environment configuration.

#### 2. User Story Pipeline Endpoints ([`test_pipeline_api.py`](file:///d:/SLIIT/SLIIT-SE-Y4S1-Academic-Resources/Research/NextGenQA/intelligent-user-story-generator-service/tests/integration/test_pipeline_api.py))
- **`TestPipelineRunEndpoint`**:
  - `POST /api/v1/pipeline/run`: Validates successful pipeline response (HTTP 200) containing generated stories list.
  - Exception Handling: Verifies `ValueError` maps to HTTP 400 Bad Request (`Pipeline Validation Error`).
  - Validation: Verifies missing payload fields return HTTP 422 Unprocessable Entity.
- **`TestGenerateFromRequirementsEndpoint`**:
  - Auth Verification: Verifies `POST /api/v1/pipeline/upload` without bearer token yields HTTP 401 Unauthorized.
  - Execution: Verifies `POST /api/v1/pipeline/generate-from-requirements` returns HTTP 200 when dependency-overridden services succeed.

#### 3. Jira Integration Endpoints ([`test_jira_api.py`](file:///d:/SLIIT/SLIIT-SE-Y4S1-Academic-Resources/Research/NextGenQA/intelligent-user-story-generator-service/tests/integration/test_jira_api.py))
- **`TestJiraTestConnectionEndpoint`**: Tests `POST /api/v1/jira/test-connection` success (HTTP 200) and credential failure (HTTP 400).
- **`TestJiraSyncStoriesEndpoint`**:
  - Missing Auth: Rejects unauthenticated requests with HTTP 401 Unauthorized.
  - Missing Config: Returns HTTP 404 Not Found when project config is missing from Auth Service.
  - Story Export: Tests full happy path (fetching config, getting/creating iteration Epic, exporting user stories to Jira Cloud).

---

## 6. How to Run the Tests

Ensure dependencies are installed in your Python environment:
```bash
pip install -r requirements.txt pytest httpx PyJWT pydantic fastapi pytest-cov
```

### Execution Commands

| Command | Description | Expected Output |
| :--- | :--- | :--- |
| `python -m pytest -p no:langsmith` | Run the complete test suite (Unit + Integration) | `70 passed in ~1.94s` |
| `python -m pytest tests/unit/ -p no:langsmith` | Run unit tests only | `55 passed in ~1.08s` |
| `python -m pytest tests/integration/ -p no:langsmith` | Run integration tests only | `15 passed in ~2.39s` |
| `python -m pytest tests/unit/test_security.py` | Run a specific test module | `8 passed in ~0.10s` |
| `python -m pytest -k "test_missing_auth"` | Run a specific test function by name filter | `1 passed in ~0.20s` |

### Generating Test Coverage Reports

To measure code coverage across `src/`:

```bash
python -m pytest --cov=src --cov-report=term-missing -p no:langsmith
```

To generate an HTML coverage report:
```bash
python -m pytest --cov=src --cov-report=html -p no:langsmith
# Open htmlcov/index.html in a web browser
```

---

## 7. Development Guidelines & Best Practices

1. **Override Dependencies on `client.app`**:
   When overriding dependencies in integration tests, modify `client.app.dependency_overrides` instead of importing `from src.main import app`. Importing `src.main` executes module-level configuration code that can trigger unwanted side effects.
   ```python
   from src.api.dependencies import get_story_pipeline

   client.app.dependency_overrides[get_story_pipeline] = lambda: mock_pipeline
   try:
       response = client.post("/api/v1/pipeline/run", json=payload)
   finally:
       client.app.dependency_overrides.pop(get_story_pipeline, None)
   ```

2. **Use Sentinels in Factory Functions**:
   When writing model factories, avoid using `or` short-circuiting for default argument lists so that callers can explicitly test empty lists `[]`:
   ```python
   _SENTINEL = object()

   def _make_story(acceptance_criteria=_SENTINEL):
       if acceptance_criteria is _SENTINEL:
           acceptance_criteria = ["Given... When... Then..."]
       return GeneratedStory(..., acceptance_criteria=acceptance_criteria)
   ```

3. **Keep Tests Fully Isolated**:
   Do not modify shared state across tests. Always clear `dependency_overrides` or use clean context manager blocks.
