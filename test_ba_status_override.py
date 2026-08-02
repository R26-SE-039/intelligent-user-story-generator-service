"""Unit tests for BA Manual Status Override Workflow."""

from unittest.mock import MagicMock
from src.services.generation.user_story_service import UserStoryService


def test_ba_status_override_workflow():
    story_id = "story-777"
    meeting_id = "meet-888"

    pipeline = MagicMock()
    pipeline.validation_repo = MagicMock()

    service = UserStoryService()

    # 1. Test BA Approve override
    res = service.override_story_status(
        story_id=story_id,
        status="Approved",
        meeting_id=meeting_id,
        feedback="BA reviewed and approved for sprint backlog.",
        pipeline=pipeline,
    )

    assert res["status"] == "success"
    assert res["new_status"] == "Approved"
    pipeline.validation_repo.update_status.assert_called_with(
        story_id=story_id,
        status="Approved",
        recommendation="BA reviewed and approved for sprint backlog.",
    )

    # 2. Test BA Reject override
    pipeline.validation_repo.reset_mock()
    res_reject = service.override_story_status(
        story_id=story_id,
        status="Rejected",
        meeting_id=meeting_id,
        feedback="Scope out of bounds for current project phase.",
        pipeline=pipeline,
    )

    assert res_reject["status"] == "success"
    assert res_reject["new_status"] == "Rejected"
    pipeline.validation_repo.update_status.assert_called_with(
        story_id=story_id,
        status="Rejected",
        recommendation="Scope out of bounds for current project phase.",
    )

    print("✅ BA manual status override test passed successfully!")


if __name__ == "__main__":
    test_ba_status_override_workflow()
