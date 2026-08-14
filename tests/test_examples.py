import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AutomationExampleTests(unittest.TestCase):
    def test_n8n_workflow_is_importable_bounded_and_credential_free(self):
        workflow_path = ROOT / "examples" / "n8n-grants-gov-monitor.json"
        workflow = json.loads(workflow_path.read_text())
        nodes = {node["name"]: node for node in workflow["nodes"]}
        request = nodes["Run Grants.gov Monitor"]["parameters"]
        body = json.loads(request["jsonBody"])

        self.assertEqual(request["authentication"], "genericCredentialType")
        self.assertEqual(request["genericAuthType"], "httpHeaderAuth")
        self.assertEqual(
            request["url"],
            "https://api.apify.com/v2/actors/ai-coding-radar~grants-gov-opportunity-monitor/"
            "run-sync-get-dataset-items?clean=1",
        )
        self.assertEqual(body["keyword"], "artificial intelligence")
        self.assertEqual(body["statuses"], ["posted", "forecasted"])
        self.assertEqual(body["limit"], 10)
        self.assertRegex(body["monitorId"], r"^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$")
        self.assertEqual(body["monitorId"], "n8n-ai-grants")
        self.assertIn("changeType === 'new'", nodes["Format grant alerts"]["parameters"]["jsCode"])
        self.assertIn("sourceUrl", nodes["Format grant alerts"]["parameters"]["jsCode"])

        public_export = workflow_path.read_text().lower()
        self.assertNotIn("bearer apify_api_", public_export)
        self.assertNotIn("?token=", public_export)
        self.assertNotIn('"credentials"', public_export)

    def test_readmes_document_both_no_code_recipes_and_the_cost_bound(self):
        readme = (ROOT / "README.md").read_text()
        examples = (ROOT / "examples" / "README.md").read_text()
        self.assertIn("examples/n8n-grants-gov-monitor.json", readme)
        self.assertIn("examples/README.md", readme)
        self.assertIn("daily-small-business-federal-grant-alerts", readme)
        self.assertIn("daily-nonprofit-federal-grant-alerts", readme)
        self.assertIn("n8n-grants-gov-monitor.json", examples)
        self.assertIn("ai-coding-radar~grants-gov-opportunity-monitor", examples)
        self.assertIn("monitorId", examples)
        self.assertIn("limit", examples)
        self.assertIn("0.15005", examples)
        self.assertRegex(examples, re.compile(r"Make", re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
