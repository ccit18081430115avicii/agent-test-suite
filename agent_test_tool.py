#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent_test_tool.py — 带 LLM 分析的智能测试小工具

功能概览：
1) 读取测试用例（JSON/YAML），对子进程（你的程序/脚本/可执行文件）进行批量测试。
2) 失败时调用 LLM 进行错误分析与修复建议（可选）。
3) 生成控制台报告与机器可读的 JUnit XML（可选）。
4) 支持输入/输出规范化（去空格、忽略行序、正则提取等）。
5) 一键初始化样例用例文件与配置。

依赖：
  pip install pyyaml openai junit-xml

环境变量（可选）：
  OPENAI_API_KEY         —— OpenAI API 密钥
  OPENAI_BASE_URL        —— OpenAI 兼容 API 的 Base URL（便于接入本地/私有化大模型）
  AGENT_MODEL            —— 模型名（默认 gpt-4o-mini）
  AGENT_SYS_PROMPT       —— 系统提示词覆盖

用法：
  # 初始化样例
  python agent_test_tool.py --init

  # 运行：指定被测命令和测试文件
  python agent_test_tool.py --cmd "python your_code.py" --tests tests.json
  python agent_test_tool.py --cmd "./your_binary" --tests tests.yaml

  # 生成 JUnit 报告
  python agent_test_tool.py --cmd "python your_code.py" --tests tests.json --junit report.xml

  # 禁用 LLM 分析
  python agent_test_tool.py --cmd "python your_code.py" --tests tests.json --no-llm

测试文件 schema（JSON/YAML 等价）：
[
  {
    "name": "add small",
    "input": "2 3\n",
    "expected": "5\n",
    "timeout": 2,
    "normalize": {
      "strip": true,               # 去除首尾空白
      "collapse_ws": true,         # 折叠多空白为一个空格
      "lower": false,              # 转小写
      "sort_lines": false,         # 按行排序（忽略顺序差异）
      "regex_extract": null        # 使用正则提取(第1个捕获组)
    }
  }
]
"""

from __future__ import annotations
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

try:
    from junit_xml import TestSuite, TestCase  # type: ignore
except Exception:
    TestSuite = None
    TestCase = None

# ============== 工具函数 ==============

def debug(msg: str):
    print(f"[agent] {msg}")


def load_tests(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = f.read()
    # 判定格式
    if path.lower().endswith(('.yaml', '.yml')):
        if yaml is None:
            raise RuntimeError("需要 pyyaml: pip install pyyaml")
        tests = yaml.safe_load(data)
    else:
        tests = json.loads(data)
    if not isinstance(tests, list):
        raise ValueError("测试文件应为数组(List)")
    return tests


def normalize_text(s: str, rules: Dict[str, Any]) -> str:
    if s is None:
        return ""
    out = s
    if rules.get("regex_extract"):
        pattern = rules["regex_extract"]
        m = re.search(pattern, out, re.S)
        out = m.group(1) if m else out
    if rules.get("strip", True):
        out = out.strip()
    if rules.get("collapse_ws", False):
        out = re.sub(r"\s+", " ", out)
    if rules.get("lower", False):
        out = out.lower()
    if rules.get("sort_lines", False):
        lines = [ln.rstrip() for ln in out.splitlines()]
        out = "\n".join(sorted(lines))
    return out


@dataclass
class CaseResult:
    name: str
    passed: bool
    expected: str
    actual: str
    input_data: str
    stderr: str
    exit_code: int
    duration: float
    analysis: Optional[str] = None


# ============== 子进程执行 ==============

def run_one(cmd: str, input_data: str, timeout: Optional[float]) -> Tuple[str, str, int, float]:
    import time
    start = time.time()
    try:
        proc = subprocess.run(
            shlex.split(cmd),
            input=input_data.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        duration = time.time() - start
        return (
            proc.stdout.decode("utf-8", errors="replace"),
            proc.stderr.decode("utf-8", errors="replace"),
            proc.returncode,
            duration,
        )
    except subprocess.TimeoutExpired as e:
        duration = time.time() - start
        return (e.output.decode("utf-8", errors="replace") if e.output else "",
                e.stderr.decode("utf-8", errors="replace") if e.stderr else "<timeout>",
                124,
                duration)


# ============== LLM 分析 ==============

def llm_analyze(input_data: str, expected: str, actual: str, stderr: str, cmd: str) -> str:
    """调用 OpenAI 兼容接口对失败原因进行分析。支持自定义 BASE_URL 与模型名。"""
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return "未安装 openai 包，无法进行 LLM 分析。请 pip install openai"

    base_url = os.getenv("OPENAI_BASE_URL")
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("AGENT_MODEL", "gpt-4o-mini")
    sys_prompt = os.getenv("AGENT_SYS_PROMPT", (
        "You are a senior software testing assistant. Given a failing test, "
        "explain the root cause, minimal reproduction, and concrete fix steps. "
        "If output mismatch is only formatting, propose normalization rules."
    ))

    if not api_key and not base_url:
        # 允许用户只配置本地私有化网关无需 key 的情况，但如果两者都空，提醒
        debug("未检测到 OPENAI_API_KEY（或私有化 OPENAI_BASE_URL），尝试无鉴权调用……")

    client = OpenAI(base_url=base_url, api_key=api_key)

    user_prompt = f"""
被测命令:
{cmd}

输入(标准输入):
{input_data}

期望输出:
{expected}

实际输出:
{actual}

标准错误(stderr):
{stderr}

请用要点形式回答：
1) 问题定位（可能根因）
2) 证据与对比（引用具体片段）
3) 修复建议（最小改动）
4) 如为格式问题，建议可加入的 normalize 规则
5) （可选）补充一个新的边界测试用例
"""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content or "(LLM 返回为空)"
    except Exception as e:
        return f"调用 LLM 失败：{e}"


# ============== 主流程 ==============

def run_suite(cmd: str, tests: List[Dict[str, Any]], use_llm: bool = True) -> List[CaseResult]:
    results: List[CaseResult] = []
    for i, t in enumerate(tests, 1):
        name = t.get("name", f"case_{i}")
        input_data = t.get("input", "")
        expected = t.get("expected", "")
        timeout = t.get("timeout", None)
        rules = t.get("normalize", {}) or {}

        stdout, stderr, code, dur = run_one(cmd, input_data, timeout)
        norm_expected = normalize_text(expected, rules)
        norm_actual = normalize_text(stdout, rules)
        passed = (norm_expected == norm_actual) and (code == 0)

        analysis = None
        if (not passed) and use_llm:
            analysis = llm_analyze(input_data, norm_expected, norm_actual, stderr, cmd)

        results.append(CaseResult(
            name=name,
            passed=passed,
            expected=norm_expected,
            actual=norm_actual,
            input_data=input_data,
            stderr=stderr,
            exit_code=code,
            duration=dur,
            analysis=analysis,
        ))

        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"[{status}] {name} ({dur:.3f}s, code={code})")
        if not passed:
            print("— diff (expected vs actual) —")
            print("EXPECTED:\n" + norm_expected)
            print("ACTUAL:\n" + norm_actual)
            if analysis:
                print("— LLM analysis —\n" + analysis)
            else:
                print("(LLM 分析已关闭或失败)")
        print()

    return results


def write_junit(results: List[CaseResult], path: str, suite_name: str = "agent-tests"):
    if TestSuite is None or TestCase is None:
        raise RuntimeError("需要 junit-xml: pip install junit-xml")
    cases = []
    for r in results:
        tc = TestCase(r.name, classname=suite_name, elapsed_sec=r.duration)
        if not r.passed:
            msg = "输出不匹配或退出码非0"
            detail = textwrap.dedent(f"""
            INPUT:\n{r.input_data}\n\nEXPECTED:\n{r.expected}\n\nACTUAL:\n{r.actual}\n\nEXIT_CODE: {r.exit_code}\nSTDERR:\n{r.stderr}\n\nLLM ANALYSIS:\n{r.analysis or '(none)'}
            """)
            tc.add_failure_info(message=msg, output=detail)
        cases.append(tc)
    ts = TestSuite(suite_name, test_cases=cases)
    with open(path, 'w', encoding='utf-8') as f:
        TestSuite.to_file(f, [ts])
    debug(f"JUnit report written: {path}")


# ============== 初始化样例 ==============
SAMPLE_JSON = [
    {
        "name": "add small",
        "input": "2 3\n",
        "expected": "5\n",
        "timeout": 2,
        "normalize": {"strip": True, "collapse_ws": True}
    },
    {
        "name": "add big",
        "input": "10 20\n",
        "expected": "30\n",
        "timeout": 2,
        "normalize": {"strip": True}
    },
    {
        "name": "format tolerance",
        "input": "001  2\n",
        "expected": "3",
        "timeout": 2,
        "normalize": {"strip": True, "collapse_ws": True}
    }
]

SAMPLE_PROGRAM = """#!/usr/bin/env python3\nimport sys\n# 一个有意带小问题的程序：未折叠多空格、未处理前导零\n# 运行方式: python sample_prog.py < input.txt\n\nline = sys.stdin.read().strip()\nif not line:\n    print(0)\n    sys.exit(0)\n# 简单相加：期望输入是"a b"\nparts = line.split(' ')  # 多空格会产生空字段\nparts = [p for p in parts if p]  # 粗暴去空元素\ntry:\n    a, b = map(int, parts[:2])\n    print(a + b)\nexcept Exception as e:\n    print(f"ERR: {e}", file=sys.stderr)\n    sys.exit(1)\n"""


def init_scaffold():
    with open("tests.json", "w", encoding="utf-8") as f:
        json.dump(SAMPLE_JSON, f, ensure_ascii=False, indent=2)
    with open("sample_prog.py", "w", encoding="utf-8") as f:
        f.write(SAMPLE_PROGRAM)
    os.chmod("sample_prog.py", 0o755)
    print("已生成 tests.json 与 sample_prog.py。\n运行示例：\n  python agent_test_tool.py --cmd \"python sample_prog.py\" --tests tests.json\n")


# ============== CLI ==============

def main():
    p = argparse.ArgumentParser(description="带 LLM 分析的智能测试小工具")
    p.add_argument("--cmd", type=str, help="被测命令，例如: 'python your_code.py' 或 './bin'", default=None)
    p.add_argument("--tests", type=str, help="测试文件(.json/.yaml)")
    p.add_argument("--no-llm", action="store_true", help="禁用 LLM 分析")
    p.add_argument("--junit", type=str, default=None, help="输出 JUnit XML 报告到该路径")
    p.add_argument("--init", action="store_true", help="生成样例 tests.json 与 sample_prog.py")
    args = p.parse_args()

    if args.init:
        init_scaffold()
        return 0

    if not args.cmd:
        print("错误：请通过 --cmd 指定被测命令。示例: --cmd 'python your_code.py'", file=sys.stderr)
        return 2
    if not args.tests:
        print("错误：请通过 --tests 指定测试文件路径", file=sys.stderr)
        return 2

    tests = load_tests(args.tests)
    results = run_suite(args.cmd, tests, use_llm=(not args.no_llm))

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    print("=" * 60)
    print(f"Total: {total}  Passed: {passed}  Failed: {failed}")

    if args.junit:
        try:
            write_junit(results, args.junit)
        except Exception as e:
            print(f"写入 JUnit 报告失败: {e}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
