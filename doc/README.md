# Technical Documentation

> [!NOTE]
> The primary project documentation is maintained in the root [README.md](../README.md).

---

## Technical Guides in `doc/`

1. **[Testing Guide](TESTING_GUIDE.md)**: Complete guide for unit and integration testing suite execution, module stubbing, fixture architecture, and test cases.
2. **[Architecture & Data Flow Diagram](COMPLETE_ARCHITECTURE_AND_DATAFLOW_DIAGRAM.md)**: Comprehensive architectural specification, meeting lifecycle sequence diagrams, and 5-layer story validation engine details.

---

## Postman Collection
The file `postman_collection.json` in this directory can be imported directly into Postman to test the API endpoints.

### Quick Setup:
1. **Import**: Open Postman -> Import -> Select `postman_collection.json`.
2. **Set Collection Variables**:
   - `base_url`: Defaults to `http://localhost:8001` (or your Gateway/Microservice base url).
   - `auth_token`: Your JWT obtained from the Auth Service.
   - `meeting_id`: Specific meeting UUID you want to test.
   - `passcode`: Passcode generated when creating a meeting.

