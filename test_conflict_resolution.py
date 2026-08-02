"""Test script for Conflict Resolution Workflow and Re-Embedding logic."""

import uuid
import logging
from unittest.mock import MagicMock

from src.models.conflict import Conflict
from src.services.requirement.requirement_thread_service import RequirementThreadService
from src.repositories.requirement_repository import RequirementRepository
from src.repositories.conflict_repository import ConflictRepository

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)


def test_conflict_resolution_workflow():
    LOGGER.info("Starting Conflict Resolution Workflow unit test...")

    # Mock gateway & dependencies
    gateway = MagicMock()
    gateway.settings.requirements_table = "requirements"
    gateway.settings.requirement_embeddings_table = "requirement_embeddings"
    gateway.settings.conflicts_table = "conflicts"
    gateway.select.side_effect = lambda table, eq: [
        {"id": eq.get("id"), "requirement_text": "Sample Text A" if eq.get("id") == "req-a" else "Sample Text B"}
    ]

    thread_service = RequirementThreadService(gateway=gateway)
    req_repo = MagicMock(spec=RequirementRepository)
    conflict_repo = MagicMock(spec=ConflictRepository)
    conflict_repo.get_by_id.return_value = {
        "id": "conf-123",
        "requirement_a_id": "req-a",
        "requirement_b_id": "req-b",
        "suggested_resolution": "The system shall allow queue bypass with manager approval.",
    }

    req_extractor = MagicMock()
    req_extractor.get_embedding.return_value = [0.1] * 3072

    # 1. Test apply_suggestion
    res = thread_service.resolve_single_conflict(
        conflict_id="conf-123",
        resolution_type="apply_suggestion",
        req_repo=req_repo,
        conflict_repo=conflict_repo,
        req_extractor=req_extractor,
        user_id="usr-ba-1",
    )

    LOGGER.info("1. apply_suggestion result: %s", res)
    assert res["status"] == "success"
    req_extractor.get_embedding.assert_called_with("The system shall allow queue bypass with manager approval.")
    req_repo.update_text_and_reembed.assert_called_once_with("req-a", "The system shall allow queue bypass with manager approval.", [0.1] * 3072)
    req_repo.update_status.assert_called_with("req-b", "superseded")
    conflict_repo.resolve_conflict.assert_called_once_with(
        conflict_id="conf-123",
        resolved_by="usr-ba-1",
        previous_text_a="Sample Text A",
        previous_text_b="Sample Text B",
    )

    # 2. Test keep_a
    req_repo.reset_mock()
    conflict_repo.reset_mock()
    res2 = thread_service.resolve_single_conflict(
        conflict_id="conf-123",
        resolution_type="keep_a",
        req_repo=req_repo,
        conflict_repo=conflict_repo,
        user_id="usr-ba-1",
    )
    LOGGER.info("2. keep_a result: %s", res2)
    req_repo.update_status.assert_any_call("req-a", "active")
    req_repo.update_status.assert_any_call("req-b", "superseded")

    # 3. Test accept_duplicate
    req_repo.reset_mock()
    conflict_repo.reset_mock()
    res3 = thread_service.resolve_single_conflict(
        conflict_id="conf-123",
        resolution_type="accept_duplicate",
        req_repo=req_repo,
        conflict_repo=conflict_repo,
        user_id="usr-ba-1",
    )
    LOGGER.info("3. accept_duplicate result: %s", res3)
    req_repo.update_status.assert_called_with("req-a", "active")
    req_repo.mark_as_duplicate.assert_called_with("req-b", duplicate_of_id="req-a")

    LOGGER.info("✅ ALL CONFLICT RESOLUTION WORKFLOW TESTS PASSED!")


if __name__ == "__main__":
    test_conflict_resolution_workflow()
