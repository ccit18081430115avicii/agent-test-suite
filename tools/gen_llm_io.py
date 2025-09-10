
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全自动②B：LLM 同时生成“输入 + 期望”，再用独立 oracle 校验过滤，防止幻觉。
需要环境变量：OPENAI_API_KEY 或 OPENAI_BASE_URL/AGENT_MODEL。
"""
import os, json
from openai import OpenAI

def oracle_eval(inp: str) -> str:
    parts = inp.strip().split()
    if len(parts) >= 2 and all(p.lstrip("-").isdigit() for p in parts[:2]):
        return f"{int(parts[0]) + int(parts[1])}\n"
    return "ERR\n"

SYS = "Return strict JSON: {'cases':[{'input':'...','expected':'...'}]}"
USR = """
请为“读取一行包含两个整数并输出其和”的程序，生成 40 条测试用例，既包含输入 input，也包含期望输出 expected。
覆盖：正常、边界、格式扰动与异常。
严格 JSON，禁止多余文本（不要换行注释/解释）。
"""

def main():
    client = OpenAI(base_url=os.getenv("OPENAI_BASE_URL"),
                    api_key=os.getenv("OPENAI_API_KEY"))
    resp = client.chat.completions.create(
        model=os.getenv("AGENT_MODEL","gpt-4o-mini"),
        messages=[{"role":"system","content":SYS},
                  {"role":"user","content":USR}],
        temperature=0.0,
    )
    data = json.loads(resp.choices[0].message.content)
    cleaned=[]
    for i, c in enumerate(data["cases"], 1):
        inp = c["input"] if c["input"].endswith("\n") else c["input"]+"\n"
        exp_llm = c["expected"] if c["expected"].endswith("\n") else c["expected"]+"\n"
        exp_true = oracle_eval(inp)
        if exp_true == exp_llm:
            cleaned.append({
                "name": f"llm-io-{i}",
                "input": inp,
                "expected": exp_true,
                "timeout": 2,
                "normalize": {"strip": True, "collapse_ws": True}
            })
    with open("tests_llm_clean.json", "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    print(f"LLM产出 {len(data['cases'])} 条，用独立校验后保留 {len(cleaned)} 条 → tests_llm_clean.json")

if __name__ == "__main__":
    main()
