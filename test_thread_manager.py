"""Test script to verify Requirement Thread Manager and state machine lifecycle."""

import uuid
import logging
from src.db.postgres import PostgresGateway
from src.services.requirement.requirement_thread_service import RequirementThreadService, RequirementState
from src.repositories.thread_repository import ThreadRepository
from src.services.requirement.requirement_extractor import RequirementExtractorService

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

def test_requirement_thread_manager():
    gateway = PostgresGateway.from_env()
    thread_service = RequirementThreadService(gateway)
    req_extractor = RequirementExtractorService()
    
    meeting_id = str(uuid.uuid4())
    LOGGER.info("Starting Requirement Thread Manager test for meeting_id=%s", meeting_id)

    # Insert dummy meeting
    gateway.insert("meetings", {"id": meeting_id, "title": "Test Thread Meeting", "status": "active"})

    # 1. First requirement
    req1_id = str(uuid.uuid4())
    req1_text = "The system must provide an online appointment booking portal for patients."
    gateway.insert("requirements", {"id": req1_id, "meeting_id": meeting_id, "requirement_text": req1_text, "status": "active"})
    emb1 = req_extractor.get_embedding(req1_text)
    
    LOGGER.info("1. Processing first requirement (dim=%d)...", len(emb1))
    thread1 = thread_service.process_requirement(
        meeting_id=meeting_id,
        requirement_id=req1_id,
        requirement_text=req1_text,
        embedding=emb1
    )
    LOGGER.info("Thread 1 Result: ID=%s, State=%s, Title='%s'", thread1["id"], thread1["state"], thread1["requirement_title"])
    assert thread1["state"] == RequirementState.DISCOVERED.value, f"Expected DISCOVERED, got {thread1['state']}"

    # 2. Similar requirement (should group into same thread and transition state to DISCUSSION/REFINED)
    req2_id = str(uuid.uuid4())
    req2_text = "Patients should be able to select doctor availability and book time slots on the portal."
    gateway.insert("requirements", {"id": req2_id, "meeting_id": meeting_id, "requirement_text": req2_text, "status": "active"})
    emb2 = req_extractor.get_embedding(req2_text)

    LOGGER.info("2. Processing similar requirement...")
    thread2 = thread_service.process_requirement(
        meeting_id=meeting_id,
        requirement_id=req2_id,
        requirement_text=req2_text,
        embedding=emb2
    )
    LOGGER.info("Thread 2 Result: ID=%s, State=%s, Summary='%s'", thread2["id"], thread2["state"], thread2["summary"])
    assert thread2["id"] == thread1["id"], "Expected requirement 2 to join the same thread!"

    # 3. Confirmation utterance (should transition state to VALIDATED)
    req3_id = str(uuid.uuid4())
    req3_text = "Yes, this online booking workflow is agreed and finalized by the team."
    gateway.insert("requirements", {"id": req3_id, "meeting_id": meeting_id, "requirement_text": req3_text, "status": "active"})
    emb3 = req_extractor.get_embedding(req3_text)

    LOGGER.info("3. Processing confirmation requirement...")
    thread3 = thread_service.process_requirement(
        meeting_id=meeting_id,
        requirement_id=req3_id,
        requirement_text=req3_text,
        embedding=emb3
    )
    LOGGER.info("Thread 3 Result: ID=%s, State=%s, Summary='%s'", thread3["id"], thread3["state"], thread3["summary"])
    assert thread3["id"] == thread1["id"], "Expected requirement 3 to join the same thread!"
    assert thread3["state"] == RequirementState.VALIDATED.value, f"Expected VALIDATED state, got {thread3['state']}"

    # 4. Verify thread database fetching
    all_threads = thread_service.thread_repo.get_threads_by_meeting(meeting_id)
    LOGGER.info("4. Database verification: Found %d thread(s) for meeting.", len(all_threads))
    assert len(all_threads) == 1, "Expected 1 consolidated thread in meeting database"

    LOGGER.info("✅ ALL REQUIREMENT THREAD MANAGER TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_requirement_thread_manager()
