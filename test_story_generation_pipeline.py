"""Unit tests for meeting-scoped user story generation & evidence validation."""

from unittest.mock import MagicMock
from src.models.user_story import GeneratedStory, StoryBatch, ValidationResult
from src.services.generation.user_story_service import UserStoryService
from src.repositories.transcript_repository import TranscriptRepository
from src.repositories.requirement_repository import RequirementRepository


def test_user_story_service_meeting_scoped_generation():
    # 1. Setup mocks
    meeting_id = "meet-12345"
    active_reqs = [
        {"id": "req-1", "meeting_id": meeting_id, "requirement_text": "Patients must be able to book appointments online.", "status": "active"},
        {"id": "req-2", "meeting_id": meeting_id, "requirement_text": "System sends SMS reminders 2 hours before appointment.", "status": "active"}
    ]

    req_repo = MagicMock(spec=RequirementRepository)
    req_repo.get_all_for_conflict_check.return_value = active_reqs

    req_extractor = MagicMock()
    req_extractor.get_embedding.return_value = [0.01] * 3072

    transcript_repo = MagicMock(spec=TranscriptRepository)
    # Simulate 0 vector results initially -> triggers DB fallback
    transcript_repo.find_relevant_utterances.return_value = []
    transcript_repo.get_requirement_utterances_by_meeting.return_value = [
        {
            "id": "utt-1",
            "transcript_id": "tr-100",
            "utterance_text": "We definitely need an online booking portal for our patients.",
            "speaker_name": "Dr. Smith",
            "start_time": 10.0,
            "end_time": 15.0,
            "utterance_type": "requirement"
        }
    ]

    pipeline = MagicMock()
    pipeline.transcript_repo = transcript_repo
    pipeline.settings.retrieval_top_k = 8
    
    mock_batch = StoryBatch(stories=[
        GeneratedStory(
            story_id="US-001",
            title="Online Patient Appointment Booking",
            story="As a patient, I want to book appointments online, so that I don't have to call the clinic.",
            acceptance_criteria=["Given a patient is logged in When selecting an open slot Then appointment is booked."],
            priority="Must",
            confidence=0.95,
            status="ready",
            evidence_refs=["req-1"]
        )
    ])
    pipeline.story_generator.generate_from_requirements.return_value = mock_batch
    
    mock_val_result = ValidationResult(
        story_id="US-001",
        rule_score=100.0,
        evidence_score=90.0,
        semantic_similarity=0.90,
        invest_score=4.5,
        hallucination_score=0.0,
        overall_quality_score=92.5,
        status="Approved",
        recommendation="Story is ready for backlog."
    )
    pipeline.validation_engine.validate_batch.return_value = [mock_val_result]
    pipeline.story_repo = MagicMock()
    pipeline.validation_repo = MagicMock()

    service = UserStoryService()

    # 2. Execute generate_from_requirements
    response = service.generate_from_requirements(
        meeting_id=meeting_id,
        pipeline=pipeline,
        req_extractor=req_extractor,
        req_repo=req_repo
    )

    # 3. Assertions
    assert response["status"] == "success"
    assert response["meeting_id"] == meeting_id
    assert len(response["stories"]) == 1
    # story_id is validated into a UUID4 string by field validator
    import uuid as uuid_mod
    assert uuid_mod.UUID(response["stories"][0]["story_id"])
    assert response["validation_results"][0]["status"] == "Approved"

    # Verify meeting-scoped requirement fetching
    req_repo.get_all_for_conflict_check.assert_called_once_with(meeting_id)

    # Verify fallback utterance retrieval was triggered when vector search returned 0 items
    transcript_repo.find_relevant_utterances.assert_called_once()
    transcript_repo.get_requirement_utterances_by_meeting.assert_called_once_with(meeting_id)

    # Verify mapping persistence
    pipeline.story_repo.save.assert_called_once()
    assert pipeline.story_repo.save_requirement_mappings.called
    saved_mappings = pipeline.story_repo.save_requirement_mappings.call_args[0][0]
    assert len(saved_mappings) == 1
    assert saved_mappings[0]["requirement_id"] == "req-1"
    pipeline.validation_repo.save.assert_called_once()

    print("✅ Meeting-scoped user story generation test passed successfully!")



if __name__ == "__main__":
    test_user_story_service_meeting_scoped_generation()
