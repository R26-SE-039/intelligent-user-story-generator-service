import logging
from atlassian import Jira

LOGGER = logging.getLogger(__name__)

class JiraService:
    def __init__(self, jira_url: str, jira_email: str, jira_api_token: str):
        self.jira_url = jira_url.rstrip("/")
        # Initialize the Atlassian Jira Client
        self.jira = Jira(
            url=self.jira_url,
            username=jira_email,
            password=jira_api_token,
            cloud=True
        )

    def test_connection(self) -> bool:
        """
        Test if Jira connection works by making a simple request to get user info.
        """
        try:
            # myself() returns information about the currently logged-in user
            self.jira.myself()
            return True
        except Exception as e:
            LOGGER.error(f"[JiraService] Connection test failed: {e}")
            raise ValueError(f"Jira connection failed: {str(e)}")

    def get_or_create_epic(self, project_key: str, epic_name: str) -> str:
        """
        Find an existing Epic with the iteration name as summary, or create a new Epic.
        """
        try:
            # Query for existing Epic
            jql = f"project = '{project_key}' AND issuetype = 'Epic' AND summary ~ '\"{epic_name}\"'"
            results = self.jira.jql(jql)
            issues = results.get("issues", [])
            if issues:
                LOGGER.info(f"[JiraService] Found existing Epic {issues[0]['key']} for Iteration {epic_name}")
                return issues[0]["key"]

            # Create Epic if not found
            epic_fields = {
                "project": {"key": project_key},
                "summary": epic_name,
                "description": f"Epic generated from NextGenQA iteration/meeting backlog: {epic_name}",
                "issuetype": {"name": "Epic"}
            }
            LOGGER.info(f"[JiraService] Creating new Epic for Iteration {epic_name}")
            new_epic = self.jira.create_issue(fields=epic_fields)
            return new_epic["key"]
        except Exception as e:
            LOGGER.error(f"[JiraService] Failed to get or create Epic: {e}")
            raise ValueError(f"Failed to resolve Jira Epic: {str(e)}")

    def export_user_stories(
        self, 
        project_key: str, 
        stories: list[dict], 
        epic_key: str | None = None
    ) -> list[dict]:
        """
        Create Jira Stories and link them to the target Epic.
        Each story should contain Acceptance Criteria and metadata labels.
        """
        created_stories = []
        for s in stories:
            title = s.get("title", "Untitled Story")
            story_id = s.get("story_id", "")
            try:
                story_text = s.get("story", "")
                acs = s.get("acceptance_criteria", [])
                score = s.get("quality_score", 100)
                status = s.get("status", "ready")

                # Format Acceptance Criteria list
                ac_list = "\n".join([f"* {ac}" for ac in acs]) if acs else "None"

                # Description in Jira Cloud format (text/wiki markup)
                description = (
                    f"h3. User Story Statement\n"
                    f"{story_text}\n\n"
                    f"h3. Acceptance Criteria (BDD)\n"
                    f"{ac_list}\n\n"
                    f"h4. Quality Assessment (NGQA)\n"
                    f"* *Quality Score:* {score}/100\n"
                    f"* *Validation Status:* {status}\n"
                    f"* *NGQA Story ID:* {story_id}"
                )

                issue_fields = {
                    "project": {"key": project_key},
                    "summary": title,
                    "description": description,
                    "issuetype": {"name": "Story"},
                    "labels": ["NextGenQA", "AI-Generated"]
                }

                if epic_key:
                    # Link to Epic using modern parent field
                    issue_fields["parent"] = {"key": epic_key}

                LOGGER.info(f"[JiraService] Creating Jira Story: {title}")
                new_story = self.jira.create_issue(fields=issue_fields)
                key = new_story["key"]
                browse_url = f"{self.jira_url}/browse/{key}"

                created_stories.append({
                    "story_id": story_id,
                    "jira_key": key,
                    "jira_url": browse_url,
                    "title": title
                })
            except Exception as e:
                LOGGER.error(f"[JiraService] Failed to create story '{title}': {e}")
                # Try creating without epic link if parent mapping failed
                if epic_key and "parent" in issue_fields:
                    try:
                        LOGGER.info(f"[JiraService] Retrying story creation without Epic link: {title}")
                        del issue_fields["parent"]
                        new_story = self.jira.create_issue(fields=issue_fields)
                        key = new_story["key"]
                        browse_url = f"{self.jira_url}/browse/{key}"
                        created_stories.append({
                            "story_id": story_id,
                            "jira_key": key,
                            "jira_url": browse_url,
                            "title": title,
                            "warning": f"Story created, but could not link to Epic: {e}"
                        })
                        continue
                    except Exception as retry_err:
                        LOGGER.error(f"[JiraService] Retry failed for story '{title}': {retry_err}")
                
                created_stories.append({
                    "story_id": story_id,
                    "error": str(e),
                    "title": title
                })
        return created_stories
