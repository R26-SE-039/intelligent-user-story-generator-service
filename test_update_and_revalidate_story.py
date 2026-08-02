"""Unit tests for User Story Editing & System 5-Layer Re-Validation."""

from unittest.mock import MagicMock
from src.models.user_story import ValidationResult
from src.services.generation.user_story_service import UserStoryService
from src.repositories.transcript_repository import TranscriptRepository


def test_update_and_revalidate_story():
    story_id = "550e8400-e29b-41d4-a716-446655440000"
    meeting_id = "meet-999"

    transcript_repo = MagicMock(spec=TranscriptRepository)
    transcript_repo.find_relevant_utterances.return_value = [
        {
            "id": "utt-1",
            "transcript_id": "tr-1",
            "utterance_text": "We need patients to book appointments online.",
            "speaker_name": "Dr. Alex",
            "start_time": 0.0,
            "end_time": 5.0,
            "utterance_type": "requirement"
        }
    ]

    pipeline = MagicMock()
    pipeline.transcript_repo = transcript_repo
    pipeline.story_repo = MagicMock()
    pipeline.validation_repo = MagicMock()

    mock_val_result = ValidationResult(
        story_id=story_id,
        rule_score=100.0,
        evidence_score=95.0,
        semantic_similarity=0.95,
        invest_score=4.8,
        hallucination_score=0.0,
        overall_quality_score=94.5,
        status="Approved",
        recommendation="Story validated and backlog ready."
    )
    pipeline.validation_engine.validate_batch.return_value = [mock_val_result]

    req_extractor = MagicMock()
    req_extractor.get_embedding.return_value = [0.01] * 3072

    service = UserStoryService()

    # Execute update and re-validation
    response = service.update_and_revalidate_story(
        story_id=story_id,
        meeting_id=meeting_id,
        title="Updated Appointment Booking",
        story="As a patient, I want to book appointments online, so that I can schedule visits 24/7.",
        acceptance_criteria=[
            "Given a patient is logged in When selecting an available slot Then the slot is confirmed.",
            "Given an invalid time slot When selected Then an error message is displayed."
        ],
        priority="Must",
        pipeline=pipeline,
        req_extractor=req_extractor
    )

    # Assertions
    assert response["status"] == "success"
    assert response["meeting_id"] == meeting_id
    assert response["story"]["story_id"] == story_id
    assert response["story"]["title"] == "Updated Appointment Booking"
    assert response["validation_result"]["overall_quality_score"] == 94.5
    assert response["validation_result"]["status"] == "Approved"

    # Verify story repository update was called
    pipeline.story_repo.update_story.assert_called_once_with(
        story_id=story_id,
        title="Updated Appointment Booking",
        story="As a patient, I want to book appointments online, so that I can schedule visits 24/7.",
        acceptance_criteria=[
            "Given a patient is logged in When selecting an available slot Then the slot is confirmed.",
            "Given an invalid time slot When selected Then an error message is displayed."
        ],
        priority="Must"
    )

    # Verify validation engine re-validated against evidence
    pipeline.validation_engine.validate_batch.assert_called_once()
    pipeline.validation_repo.save.assert_called_once()

    print("✅ Story update & system re-validation test passed successfully!")


if __name__ == "__main__":
    test_update_and_revalidate_story()
