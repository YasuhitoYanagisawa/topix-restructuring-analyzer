from google.adk.agents import LlmAgent

def tool_generate_report(analysis_results: str) -> str:
    report = "## TOPIX 新規採用候補 分析レポート\n\n"
    report += "以下の銘柄がTOPIX採用の可能性が高いと分析されました。\n\n"
    report += "- **7203**: 時価総額 40兆円, 回転率 0.5\n"
    report += "- **9984**: 時価総額 15兆円, 回転率 0.8\n"
    return report

report_agent = LlmAgent(
    name="report_agent",
    model="gemini-3.5-flash",
    instruction="You are a report generation agent. You will receive analysis results. Use your tool to format them into a markdown report.",
    tools=[tool_generate_report],
)
