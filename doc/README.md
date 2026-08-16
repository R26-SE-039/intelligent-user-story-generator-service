# API Documentation

> [!NOTE]
> The primary project documentation has been moved to the root level.
> Please refer to the main [README.md](../README.md) in the project root directory for configuration, setup guide, database schemas, and API documentation.

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
