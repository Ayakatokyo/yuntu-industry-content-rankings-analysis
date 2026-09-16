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

    def test_skill_keeps_the_operating_guide_concise(self):
        self.assertLessEqual(len(self.read_skill().splitlines()), 170)

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

    def test_declares_user_preinput_and_yuntu_time_defaults(self):
        skill = self.read_skill()
        frontmatter = re.match(r"\A---\n(.*?)\n---", skill, re.DOTALL)

        self.assertIsNotNone(frontmatter)
        self.assertRegex(frontmatter.group(1), r"(?m)^argument_hint: .+分析周期")
        self.assertRegex(frontmatter.group(1), r"(?m)^  pre_input: .+分析周期")
        for phrase in (
            "近七天",
            "云图界面",
            "行业",
            "秒级拆解素材数",
            "默认",
            "同一分析周期",
        ):
            self.assertIn(phrase, skill)

    def test_documents_distinct_collection_and_brand_analysis_counts(self):
        skill = self.read_skill()
        frontmatter = re.match(r"\A---\n(.*?)\n---", skill, re.DOTALL)

        self.assertIsNotNone(frontmatter)
        self.assertNotIn("fetch --target-top-n", frontmatter.group(1))
        self.assertNotIn("prepare-analysis --brand-top-n", frontmatter.group(1))
        self.assertIn("秒级拆解素材数默认 10，由批参数 JSON 的 `target_top_n` 控制", skill)
        self.assertIn("第一部分品牌分析直接使用提取到的行业 TOP1000，并在其中按品牌匹配全部素材", skill)
        self.assertNotIn("品牌榜单 Top 素材数默认 30", skill)
        self.assertIn("未完成映射核对时不得启动 RPA 长任务", skill)

    def test_fetch_and_prepare_cli_help_explain_count_ownership(self):
        result = subprocess.run(
            [sys.executable, str(CONNECTOR_PATH), "fetch", "--help"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("target_top_n", result.stdout)
        self.assertIn("candidate_top_n", result.stdout)
        self.assertIn("second-level breakdown", result.stdout)
        self.assertIn("not the brand analysis Top N", result.stdout)

        result = subprocess.run(
            [sys.executable, str(CONNECTOR_PATH), "prepare-analysis", "--help"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertNotIn("brand Top N", result.stdout)
        self.assertNotIn("Analysis-only", result.stdout)

    def test_documents_relative_periods_as_yuntu_enums(self):
        skill = self.read_skill()

        for phrase in (
            "近7天",
            "LAST_7_DAYS",
            "近30天",
            "LAST_30_DAYS",
            "不换算为自定义日期",
        ):
            self.assertIn(phrase, skill)

    def test_documents_optional_filters_and_generic_user_facing_copy(self):
        skill = self.read_skill()
        prompt = (ROOT / "prompts" / "yuntu-analysis-prompt.md").read_text(
            encoding="utf-8"
        )

        for phrase in (
            "指定品牌是 ____（至少3个品牌）",
            "年龄是 ____（可选；不填写则不筛选，即全选）",
            "性别是 ____（可选；不填写则不筛选，即全选）",
            "八大人群是 ____（可选；不填写则不筛选，即全选）",
        ):
            self.assertIn(phrase, skill)
        removed_brand = "\u5c0f\u4ed9\u7096"
        self.assertNotIn(removed_brand, skill)
        self.assertNotIn(removed_brand, prompt)

    def test_requires_the_same_time_range_for_ranking_and_detail(self):
        skill = self.read_skill()

        self.assertIn("榜单和素材详情必须使用同一分析周期", skill)
        self.assertRegex(
            skill,
            r'(?s)"date_type": "LAST_7_DAYS".{0,160}'
            r'"date_type": "LAST_7_DAYS"',
        )

    def test_documents_fixed_connectors_runtime_and_workflow(self):
        skill = self.read_skill()
        for connector in (
            "rpa.conn.juliang.yt.industry.content.rankings.list",
            "rpa.conn.juliang.yt.industry.content.rankings.details",
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
            "schema",
            "self-test",
            "fetch",
            "prepare-analysis",
            "render-report",
            "retry-failed",
            "retry-unresolved",
        ):
            self.assertIn(f"{command} {subcommand}", skill)
        dynamic_command = "python <skill-root>/scripts/rpa_dynamic_client.py"
        for subcommand in ("detail", "list-accounts", "validate"):
            self.assertIn(f"{dynamic_command} {subcommand}", skill)

        result = subprocess.run(
            [sys.executable, str(CONNECTOR_PATH), "fetch", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for option in (
            "--shop-id",
            "--params-json",
            "--params-file",
            "--output-dir",
        ):
            self.assertIn(option, result.stdout)
            self.assertIn(option, skill)
        for removed_option in ("--top-n", "--industry", "--detail-date-range-type"):
            self.assertNotIn(removed_option, result.stdout)
        root_help = subprocess.run(
            [sys.executable, str(CONNECTOR_PATH), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(root_help.returncode, 0, root_help.stderr)
        self.assertIn("retry-failed", root_help.stdout)
        self.assertIn("retry-unresolved", root_help.stdout)

    def test_documents_long_task_recovery_and_explicit_unresolved_retry(self):
        skill = self.read_skill()

        for phrase in (
            "长任务",
            "异步",
            "3600 秒",
            "unresolvedMaterials",
            "retry-unresolved",
            "不重复提交",
        ):
            self.assertIn(phrase, skill)

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
            "references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_details.md",
            skill,
        )

    def test_documents_html_and_zip_final_delivery(self):
        skill = self.read_skill()

        for phrase in (
            "final-report.zip",
            "HTML 报告",
            "final-report/` 目录",
            "同级",
        ):
            self.assertIn(phrase, skill)

    def test_report_acceptance_is_automated_without_browser_visual_check(self):
        skill = self.read_skill()

        self.assertIn("报告验收只执行自动化产物校验", skill)
        self.assertIn("不要启动实际浏览器", skill)
        self.assertIn("不要把桌面端、移动端截图或人工视觉检查列为技能必经步骤", skill)

    def test_keeps_operational_rules_and_defers_schema_details(self):
        skill = self.read_skill()

        for phrase in (
            "run-summary.json",
            "status --output-dir",
            "参数指纹",
            "list_context",
            "unresolvedMaterials",
            "status == success",
            "prepare-analysis",
            "attest-analysis",
            "render-report",
            "程序化兜底",
            "脚本和生成的提示词是 schema 权威",
        ):
            self.assertIn(phrase, skill)
        self.assertIn("python <skill-root>/scripts/rpa_connector.py status", skill)
        self.assertLessEqual(len(skill.splitlines()), 100)
        self.assertNotIn("industryTop1000Facts", skill)
        self.assertNotIn("--highlight-trends", skill)

    def test_documents_slim_analysis_output_and_legacy_json_compatibility(self):
        skill = self.read_skill()

        self.assertIn("只生成当前报告实际展示的分析模块", skill)
        self.assertIn("旧版完整 JSON", skill)
        self.assertIn("额外字段", skill)
        self.assertIn("兼容渲染", skill)
        self.assertIn("新批次不再生成 `yuntu-analysis-data.json`", skill)
        self.assertIn("缺少 `report-data.json`", skill)
        self.assertIn("历史批次", skill)
        self.assertIn(
            "`diagnostic-analysis/yuntu-ai-analysis.schema.json`", skill
        )
        self.assertIn("`diagnostic-analysis/yuntu-analysis-prompt.md`", skill)
        self.assertNotIn(
            "`diagnostic-analysis/yuntu-analysis-data.json`（完整兼容快照）",
            skill,
        )

    def test_requires_current_dialog_model_without_external_model_processes(self):
        skill = self.read_skill()

        self.assertIn("当前对话模型直接完成", skill)
        self.assertIn("实际查看全部可用本地 JPEG", skill)
        for forbidden_route in ("`codex exec`", "子进程", "外部模型服务"):
            self.assertIn(forbidden_route, skill)
        self.assertIn("不得仅凭 `--generator`", skill)

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
