"""Context Builder for utterance classification.

Builds the contextual input string matching the format used during ModernBERT training:
    "Previous: {prev} | Utterance: {current} | Next: {next}"
"""

from __future__ import annotations


class ContextBuilder:
    """Builds context-aware input strings for utterance classification."""

    def build(
        self,
        utterances: list[str],
        index: int,
    ) -> str:
        """Build a contextual string for the utterance at the given index.

        Args:
            utterances: Ordered list of utterance strings from the meeting.
            index: Index of the utterance to classify.

        Returns:
            Formatted string: "Previous: X | Utterance: Y | Next: Z"
        """
        previous = utterances[index - 1].strip() if index > 0 else ""
        current = utterances[index].strip()
        next_utt = utterances[index + 1].strip() if index < len(utterances) - 1 else ""

        return f"Previous: {previous} | Utterance: {current} | Next: {next_utt}"

    def build_single(
        self,
        current: str,
        previous: str = "",
        next_utterance: str = "",
    ) -> str:
        """Build a contextual string from individual utterance strings.

        Useful when you don't have a full list, e.g. for real-time streaming.

        Args:
            current: The utterance to classify.
            previous: The utterance before it (can be empty).
            next_utterance: The utterance after it (can be empty).

        Returns:
            Formatted string: "Previous: X | Utterance: Y | Next: Z"
        """
        return (
            f"Previous: {previous.strip()} | "
            f"Utterance: {current.strip()} | "
            f"Next: {next_utterance.strip()}"
        )

    def build_all(self, utterances: list[str]) -> list[str]:
        """Build context strings for all utterances in a list.

        Args:
            utterances: Full list of utterance strings from a meeting.

        Returns:
            List of formatted context strings, one per utterance.
        """
        return [self.build(utterances, i) for i in range(len(utterances))]
