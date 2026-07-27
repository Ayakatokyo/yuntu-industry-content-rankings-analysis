import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = ROOT / "SKILL.md"
OPENAI_YAML_PATH = ROOT / "agents" / "openai.yaml"
CONNECTOR_PATH = ROOT / "scripts" / "rpa_connector.py"


class AnalysisSkillContractTests(unittest.TestCase):
    def read_skill(self):
        return SKILL_PATH.read_text(encoding="utf-8")

    def test_frontmatter_identifies_a_standalone_analysis_skill(self):
        skill = self.read_skill()
        frontmatter = re.match(r"\A---\n(.*?)\n---", skill, re.DOTALL)

        self.assertIsNotNone(frontmatter)
        self.assertIn(
            "name: 云图行业内容榜单分析", frontmatter.group(1)
        )
        description = re.search(r"^description: (.+)$", frontmatter.group(1), re.MULTILINE)
        self.assertIsNotNone(description)
        self.assertTrue(description.group(1).startswith("适用于"))
        self.assertNotIn("python", description.group(1).lower())

    def test_documents_fixed_connectors_runtime_and_workflow(self):
        skill = self.read_skill()
        for connector in (
            "rpa.conn.juliang.yt.industry.content.rankings.list",
            "rpa.conn.juliang.yt.industry.content.rankings.detail",
        ):
            self.assertIn(connector, skill)
        for environment_variable in (
            "ENV_BACKEND_HOST",
            "YUCE_AUTHORIZATION",
            "YUCE_SESSION_ID",
        ):
            self.assertIn(environment_variable, skill)
        self.assertRegex(skill, r"凭证.{0,100}环境变量")
        self.assertRegex(skill, r"(?s)列表.{0,300}material_id.{0,160}详情")

    def test_documents_all_commands_and_exposes_fetch_options(self):
        skill = self.read_skill()
        command = "python yuntu-industry-content-rankings-analysis/scripts/rpa_connector.py"
        for subcommand in ("list-accounts", "schema", "self-test", "fetch"):
            self.assertIn(f"{command} {subcommand}", skill)

        result = subprocess.run(
            [sys.executable, str(CONNECTOR_PATH), "fetch", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for option in (
            "--shop-id",
            "--top-n",
            "--output-dir",
            "--detail-date-range-type",
            "--detail-custom-start-date",
            "--detail-custom-end-date",
            "--industry",
            "--time-range-type",
            "--ranking-limit-type",
        ):
            self.assertIn(option, result.stdout)
            self.assertIn(option, skill)

    def test_documents_default_output_and_failure_boundaries(self):
        skill = self.read_skill()
        self.assertRegex(skill, r"(?is)top.{0,80}10")
        for output_path in (
            "list-response.json",
            "details/<material_id>.json",
            "manifest.json",
        ):
            self.assertIn(output_path, skill)
        self.assertRegex(skill, r"(?is)list.{0,140}(fail|失败).{0,160}(nonzero|非零)")
        self.assertRegex(skill, r"(?is)detail.{0,160}(continue|继续).{0,160}(nonzero|非零)")
        self.assertRegex(skill, r"(?i)(does not|不).{0,100}(download|下载).{0,80}(video|视频)")
        self.assertRegex(skill, r"(?i)(does not|不).{0,100}(process|处理).{0,80}(files|文件)")
        self.assertRegex(skill, r"(?i)(does not|不).{0,100}(report|报告)")

    def test_openai_metadata_has_required_interface_fields(self):
        metadata = OPENAI_YAML_PATH.read_text(encoding="utf-8")
        self.assertRegex(metadata, r'(?m)^interface:\s*$')
        self.assertRegex(metadata, r'(?m)^  display_name: "[^"\n]+"\s*$')
        self.assertRegex(metadata, r'(?m)^  short_description: "[^"\n]+"\s*$')
        self.assertIn(
            "$云图行业内容榜单分析",
            metadata,
        )


if __name__ == "__main__":
    unittest.main()
