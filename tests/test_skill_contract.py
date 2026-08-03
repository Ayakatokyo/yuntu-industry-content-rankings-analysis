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

    def test_guides_platform_injected_gateway_diagnosis(self):
        skill = self.read_skill()

        self.assertIn("平台运行时注入", skill)
        self.assertRegex(skill, r"(?s)404.{0,160}基路径")
        self.assertRegex(skill, r"(?s)504.{0,160}网关超时")

    def test_documents_all_commands_and_exposes_fetch_options(self):
        skill = self.read_skill()
        command = "python <skill-root>/scripts/rpa_connector.py"
        for subcommand in (
            "list-accounts",
            "schema",
            "self-test",
            "fetch",
            "prepare-analysis",
            "render-report",
            "retry-failed",
        ):
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
        root_help = subprocess.run(
            [sys.executable, str(CONNECTOR_PATH), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(root_help.returncode, 0, root_help.stderr)
        self.assertIn("retry-failed", root_help.stdout)

    def test_documents_default_output_and_failure_boundaries(self):
        skill = self.read_skill()
        self.assertRegex(skill, r"(?is)top.{0,80}10")
        for output_path in (
            "list-response.json",
            "details/<material_id>.json",
            "manifest.json",
        ):
            self.assertIn(output_path, skill)
        self.assertRegex(skill, r"(?s)列表请求失败.{0,160}非零")
        self.assertRegex(skill, r"(?s)详情请求失败.{0,160}继续.{0,160}非零")
        self.assertRegex(skill, r"(?i)(does not|不).{0,100}(download|下载).{0,80}(video|视频)")
        self.assertRegex(skill, r"(?s)files-envelope.{0,200}CSV")
        self.assertRegex(skill, r"(?s)报告.{0,200}render-report")

    def test_documents_csv_first_analysis_workflow(self):
        skill = self.read_skill()
        for phrase in (
            "files-envelope",
            "raw-csv/list.csv",
            "raw-csv/details/<material_id>.csv",
            "normalized/list-records.json",
            "normalized/detail-records/<material_id>.json",
            "batch-manifest.json",
            "prepare-analysis",
            "render-report",
            "yuntu-analysis-data.json",
            "yuntu-ai-analysis.json",
            "final-report.md",
        ):
            self.assertIn(phrase, skill)
        self.assertRegex(skill, r"(?s)CSV.{0,120}主路径")
        self.assertRegex(skill, r"(?s)分析.{0,120}normalized")
        self.assertIn("references/platforms/juliang-yt.md", skill)
        self.assertIn(
            "references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_list.md",
            skill,
        )
        self.assertIn(
            "references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_detail.md",
            skill,
        )

    def test_documents_xiaoxian_dun_closed_loop_report(self):
        skill = self.read_skill()
        for chapter in (
            "榜单机会总览",
            "素材表现对比",
            "单素材秒级诊断",
            "竞品创意模式",
            "小仙炖机会地图",
            "下一轮实验矩阵",
        ):
            self.assertIn(chapter, skill)
        self.assertIn("Python 字面量", skill)
        self.assertIn("数据不足以判断", skill)
        self.assertNotIn("数据范围与可信度", skill)
        self.assertNotIn("风险与待补数据", skill)

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
