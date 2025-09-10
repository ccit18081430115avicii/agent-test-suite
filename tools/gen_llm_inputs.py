
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全自动②A：大模型只生成“输入”，期望值由参考实现/规约计算（最稳妥）。
需要环境变量：OPENAI_API_KEY 或 OPENAI_BASE_URL（私有化网关）/AGENT_MODEL。
"""
import os, json
from openai import OpenAI

# 参考实现/规约 —— 请替换为你的业务逻辑
def oracle_eval(s: str) -> str:
    parts = s.strip().split()
    if len(parts) >= 2 and all(p.lstrip("-").isdigit() for p in parts[:2]):
        return f"{int(parts[0]) + int(parts[1])}\n"
    return "ERR\n"

SYS = "You are a careful test generator. Always return strict JSON with field 'inputs' as a list of strings."
USR = """
目标程序：读取一行，包含两个整数，相加后输出结果并换行。
请生成 30 个“多样化且贴近真实”的输入行，覆盖以下类型：
- 正常样例、边界值（0、极大/极小、负数）
- 格式扰动（多空白、前后空格、tab、前导零）
- 异常样例（非数字、分隔符错误、缺失参数、空输入）
输出格式（严格）：{"inputs": ["...","...", ...]}
"""

def main():
    client = OpenAI(base_url=os.getenv("OPENAI_BASE_URL"),
                    api_key=os.getenv("OPENAI_API_KEY"))
    resp = client.chat.completions.create(
        model=os.getenv("AGENT_MODEL", "gpt-4o-mini"),
        messages=[{"role": "system", "content": SYS},
                  {"role": "user", "content": USR}],
        temperature=0.0,
    )
    content = resp.choices[0].message.content
    data = json.loads(content)  # 严格JSON
    tests=[]
    for i, inp in enumerate(data["inputs"], 1):
        if not inp.endswith("\n"):
            inp += "\n"
        exp = oracle_eval(inp)
        tests.append({
            "name": f"llm-auto-{i}",
            "input": inp,
            "expected": exp,
            "timeout": 2,
            "normalize": {"strip": True, "collapse_ws": True}
        })
    with open("tests_llm.json", "w", encoding="utf-8") as f:
        json.dump(tests, f, ensure_ascii=False, indent=2)
    print(f"已生成 {len(tests)} 条 LLM 输入用例到 tests_llm.json")

if __name__ == "__main__":
    main()
