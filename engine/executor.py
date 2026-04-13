"""
B 层执行器（升级版）
实现 LLM + 工具调用循环（ReAct 模式）

流程：
  A层发出任务
    → B层把任务 + 工具列表发给 LLM
    → LLM 决定调用哪个工具
    → Python 真正执行工具
    → 结果返回给 LLM
    → LLM 继续推理或返回最终答案
    → 循环直到完成或超过最大步数
"""

import json
import re
from typing import List, Dict, Any, Optional, Callable
from engine.tools import execute_tool, get_all_schemas, get_tool_risk, TOOL_REGISTRY


# ── 风险确认回调类型 ─────────────────────────────────────
# 签名：(tool_name, params) -> bool
# 返回 True 表示允许执行，False 表示拒绝
ConfirmCallback = Callable[[str, dict], bool]


def default_confirm(tool_name: str, params: dict) -> bool:
    """默认：命令行询问用户"""
    print(f"\n⚠️  [高风险操作] 工具：{tool_name}")
    print(f"   参数：{json.dumps(params, ensure_ascii=False)[:200]}")
    ans = input("   是否允许执行？(y/N) ").strip().lower()
    return ans == "y"


class BLayerExecutor:
    """
    B 层执行器
    支持：纯文本生成 + 工具调用循环
    """

    def __init__(
        self,
        llm_client,
        confirm_callback: ConfirmCallback = None,
        max_tool_steps: int = 8,
        allowed_tools: List[str] = None,   # None = 允许所有工具
        verbose: bool = True
    ):
        self.llm = llm_client
        self.confirm = confirm_callback or default_confirm
        self.max_steps = max_tool_steps
        self.allowed_tools = allowed_tools
        self.verbose = verbose

        # 执行历史（本次任务内）
        self.execution_log: List[Dict] = []

        # ── 动态工具表（LLM自己写代码注册的工具）────────
        # { tool_name: {"fn": callable, "description": str, "code": str} }
        self._dynamic_tools: Dict[str, Dict] = {}

        # 是否已经尝试过run_python兜底（每个任务重置）
        self._python_fallback_attempted: bool = False

    def _log(self, tag: str, msg: str):
        if self.verbose:
            print(f"  [B·{tag}] {msg}")

    def generate(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        system: str = None,
        messages: List[Dict] = None
    ) -> str:
        """纯文本生成（不带工具）"""
        return self.llm.generate(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=messages
        )

    def execute_task(
        self,
        task: str,
        context: str = "",
        use_tools: bool = True,
        max_tokens: int = 4000
    ) -> Dict[str, Any]:
        """
        执行一个需要工具的任务
        返回：{
          "result": 最终答案,
          "steps": 执行步骤列表,
          "tools_used": 用了哪些工具,
          "success": bool
        }
        """
        self.execution_log = []
        steps = []
        tools_used = []
        self._python_fallback_attempted = False

        if not use_tools:
            result = self.generate(task, max_tokens=max_tokens)
            return {"result": result, "steps": [], "tools_used": [], "success": True}

        # 获取可用工具 schema
        schemas = self._get_available_schemas()

        # 构建系统提示
        system_prompt = self._build_system_prompt(context)

        # 消息历史
        messages = [{"role": "user", "content": task}]

        self._log("任务", task[:80])

        # ── 工具结果最大长度（防止上下文溢出） ──────────
        TOOL_RESULT_MAX_CHARS = 3000

        # ── 失败重试计数 ────────────────────────────
        MAX_TOOL_RETRIES = 2
        consecutive_failures = 0
        consecutive_successes = 0
        last_text_output = ""  # 记录最后一步LLM的文本输出（超限兜底用）

        for step in range(self.max_steps):
            # 调用 LLM（带工具定义）
            response = self._call_llm_with_tools(
                messages=messages,
                system=system_prompt,
                tools=schemas,
                max_tokens=max_tokens
            )

            # 解析响应
            text_parts = []
            tool_calls = []

            for block in response:
                if block.get("type") == "text":
                    text_parts.append(block["text"])
                elif block.get("type") == "tool_use":
                    tool_calls.append(block)

            text_content = "\n".join(text_parts).strip()
            if text_content:
                last_text_output = text_content

            # 如果没有工具调用，这就是最终答案
            if not tool_calls:
                self._log("完成", f"步骤 {step+1}，无更多工具调用")
                return {
                    "result": text_content,
                    "steps": steps,
                    "tools_used": list(set(tools_used)),
                    "success": True
                }

            # 执行工具调用
            tool_results = []
            step_has_failure = False
            for tc in tool_calls:
                tool_name = tc.get("name", "")
                tool_params = tc.get("input", {})
                tool_id = tc.get("id", f"call_{step}")

                self._log("工具", f"调用 {tool_name}({json.dumps(tool_params, ensure_ascii=False)[:100]})")

                # 动态工具：每次调用都需用户确认
                if tool_name in self._dynamic_tools:
                    dyn_info = self._dynamic_tools[tool_name]
                    self._log("自学习", f"检测到自学习工具：{tool_name}")
                    allowed = self.confirm(
                        tool_name,
                        {"说明": f"执行之前自动学习的代码：{dyn_info['description'][:80]}"}
                    )
                    if not allowed:
                        result_content = {"ok": False, "error": "用户拒绝执行此自学习工具"}
                        self._log("拒绝", f"{tool_name} 被用户拒绝")
                    else:
                        result_content = self._execute_dynamic_tool(tool_name)
                # 静态工具：按原有风险等级检查
                elif get_tool_risk(tool_name) == "high":
                    allowed = self.confirm(tool_name, tool_params)
                    if not allowed:
                        result_content = {"ok": False, "error": "用户拒绝执行此高风险操作"}
                        self._log("拒绝", f"{tool_name} 被用户拒绝")
                    else:
                        result_content = execute_tool(tool_name, tool_params)
                else:
                    result_content = execute_tool(tool_name, tool_params)

                self._log(
                    "结果",
                    f"{tool_name} → {'✅' if result_content.get('ok') else '❌'} "
                    f"{str(result_content)[:120]}"
                )

                # ── 大文本自动摘要（read_file / read_office 超长内容） ──
                if result_content.get("ok") and tool_name in ("read_file", "read_office"):
                    result_content = self._process_large_tool_result(
                        result_content, tool_name
                    )

                # ── 工具失败重试提示（区分错误类型） ──────
                if not result_content.get("ok"):
                    step_has_failure = True
                    error_msg = result_content.get("error", "未知错误")
                    if consecutive_failures < MAX_TOOL_RETRIES:
                        retry_hint = self._classify_retry_hint(
                            tool_name, error_msg, consecutive_failures, MAX_TOOL_RETRIES
                        )
                        result_content["_retry_hint"] = retry_hint
                        self._log("重试", f"工具失败，提示 LLM 修正（第 {consecutive_failures + 1}/{MAX_TOOL_RETRIES} 次）")

                tools_used.append(tool_name)
                steps.append({
                    "step": step + 1,
                    "tool": tool_name,
                    "params": tool_params,
                    "result": result_content
                })

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": self._truncate_tool_result(result_content)
                })

            # 更新连续失败/成功计数
            if step_has_failure:
                consecutive_failures += 1
                consecutive_successes = 0
            else:
                consecutive_failures = 0
                consecutive_successes += 1

            # 连续失败超过阈值，先尝试run_python兜底，再终止
            if consecutive_failures > MAX_TOOL_RETRIES:
                if not self._python_fallback_attempted:
                    fallback_result = self._try_python_fallback(
                        task, steps, messages, system_prompt, max_tokens
                    )
                    if fallback_result is not None:
                        # 兜底成功，把结果注册为动态工具并返回
                        return {
                            "result": fallback_result["result"],
                            "steps": steps + fallback_result.get("steps", []),
                            "tools_used": list(set(tools_used + ["run_python(fallback)"])),
                            "success": True
                        }
                self._log("终止", f"连续 {consecutive_failures} 次工具失败，终止执行")
                summary = self._summarize_steps(steps, tools_used)
                return {
                    "result": f"连续 {MAX_TOOL_RETRIES} 次工具执行失败，已终止。\n\n{summary}",
                    "steps": steps,
                    "tools_used": list(set(tools_used)),
                    "success": False
                }

            # 把工具结果放回消息历史，继续推理
            # assistant 消息（包含工具调用）
            messages.append({
                "role": "assistant",
                "content": (
                    [{"type": "text", "text": text_content}] if text_content else []
                ) + [
                    {"type": "tool_use", "id": tc.get("id", f"call_{i}"),
                     "name": tc["name"], "input": tc.get("input", {})}
                    for i, tc in enumerate(tool_calls)
                ]
            })
            # 工具结果消息
            messages.append({
                "role": "user",
                "content": tool_results
            })

        # 超过最大步数 — 返回部分结果汇总
        summary = self._summarize_steps(steps, tools_used)
        self._log("超限", f"超过 {self.max_steps} 步，返回已完成结果汇总")
        # 如果最后一步LLM有文本输出（可能是未完成的分析），一并返回
        result_text = f"任务执行达到最大步数（{self.max_steps}步），部分结果如下：\n\n{summary}"
        if last_text_output:
            result_text += f"\n\n【最后阶段的分析】\n{last_text_output[:3000]}"
        return {
            "result": result_text,
            "steps": steps,
            "tools_used": list(set(tools_used)),
            "success": False
        }

    def _call_llm_with_tools(
        self,
        messages: List[Dict],
        system: str,
        tools: List[Dict],
        max_tokens: int
    ) -> List[Dict]:
        """
        调用支持工具的 LLM
        返回 content block 列表
        """
        from engine.llm_client import (
            OllamaClient, DeepSeekClient, OpenAIClient, GroqClient,
            ClaudeClient, GeminiClient,
            QwenClient, ZhipuClient, DoubaoClient, KimiClient,
            BaiduClient, SparkClient,
        )
        # OpenAI 兼容格式（DeepSeek / OpenAI / Groq / 国产大模型）
        _openai_compat = (
            DeepSeekClient, OpenAIClient, GroqClient,
            QwenClient, ZhipuClient, DoubaoClient, KimiClient,
            BaiduClient, SparkClient,
        )
        if isinstance(self.llm, _openai_compat):
            return self._call_openai_tools(messages, system, tools, max_tokens)
        if isinstance(self.llm, OllamaClient):
            return self._call_ollama_tools(messages, system, tools, max_tokens)
        # Claude / Gemini：使用 ReAct prompt 方式（tool 描述内嵌到 prompt）
        if isinstance(self.llm, (ClaudeClient, GeminiClient)):
            return self._call_react_tools(messages, system, tools, max_tokens)
        # Mock 模式
        return self._call_mock_tools(messages, tools)

    def _call_openai_tools(
        self, messages, system, tools, max_tokens
    ) -> List[Dict]:
        """调用 OpenAI 兼容 API（DeepSeek / OpenAI / Groq 统一处理）"""
        import urllib.request, urllib.error

        # ── 工具 schema 转 OpenAI 格式 ──────────────
        oai_tools = []
        for t in tools:
            schema = t.get("input_schema", {})
            # 清理 properties 里的 required/description 嵌套（DeepSeek 严格校验）
            clean_props = {}
            for k, v in schema.get("properties", {}).items():
                prop = {}
                if "type" in v:
                    prop["type"] = v["type"]
                if "description" in v:
                    prop["description"] = v["description"]
                # enum 等其他合法字段保留
                for extra in ("enum", "default", "minimum", "maximum"):
                    if extra in v:
                        prop[extra] = v[extra]
                clean_props[k] = prop

            params: Dict = {"type": "object", "properties": clean_props}
            required = schema.get("required", [])
            if required:
                params["required"] = required

            oai_tools.append({
                "type": "function",
                "function": {
                    "name":        t["name"],
                    "description": t["description"][:256],   # 截断过长描述
                    "parameters":  params
                }
            })

        # ── 消息历史转 OpenAI 格式 ──────────────────
        # 原始 messages 里可能混有 Anthropic 格式的 tool_use/tool_result
        # 必须转换成 OpenAI 的 assistant+tool 格式
        # 先压缩消息防止上下文溢出
        messages = self._compact_messages(messages)
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})

        for m in messages:
            role    = m.get("role", "user")
            content = m.get("content", "")

            # 纯文本消息：直接加
            if isinstance(content, str):
                msgs.append({"role": role, "content": content})
                continue

            # content 是列表（Anthropic 多块格式）
            if isinstance(content, list):
                text_parts   = []
                tool_calls   = []
                tool_results = []

                for block in content:
                    btype = block.get("type", "")
                    if btype == "text":
                        text_parts.append(block.get("text", ""))
                    elif btype == "tool_use":
                        # Anthropic tool_use → OpenAI tool_calls
                        tool_calls.append({
                            "id":   block.get("id", ""),
                            "type": "function",
                            "function": {
                                "name":      block.get("name", ""),
                                "arguments": json.dumps(
                                    block.get("input", {}),
                                    ensure_ascii=False
                                )
                            }
                        })
                    elif btype == "tool_result":
                        tool_results.append(block)

                # assistant 消息（带 tool_calls）
                if tool_calls:
                    msg_obj: Dict = {"role": "assistant"}
                    if text_parts:
                        msg_obj["content"] = "\n".join(text_parts)
                    msg_obj["tool_calls"] = tool_calls
                    msgs.append(msg_obj)
                elif text_parts:
                    msgs.append({
                        "role": role,
                        "content": "\n".join(text_parts)
                    })

                # tool 结果消息（每个结果单独一条）
                for tr in tool_results:
                    msgs.append({
                        "role":         "tool",
                        "tool_call_id": tr.get("tool_use_id", ""),
                        "content":      tr.get("content", "")
                    })

        # ── 发起请求 ────────────────────────────────
        body = {
            "model":      getattr(self.llm, 'model', 'deepseek-chat'),
            "messages":   msgs,
            "max_tokens": max_tokens,
        }
        # 只在有工具时加 tools 字段（空列表会导致 400）
        if oai_tools:
            body["tools"]       = oai_tools
            body["tool_choice"] = "auto"

        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")

        if self.verbose:
            # 调试：打印发出的消息条数和工具数
            self._log("API请求",
                f"消息 {len(msgs)} 条, 工具 {len(oai_tools)} 个, "
                f"max_tokens={max_tokens}"
            )

        api_url = f"{self.llm.base_url}/chat/completions"
        req = urllib.request.Request(
            api_url,
            data=payload,
            headers={
                "Content-Type":  "application/json; charset=utf-8",
                "Authorization": f"Bearer {self.llm.api_key}"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            msg    = data["choices"][0]["message"]
            blocks = []

            if msg.get("content"):
                blocks.append({"type": "text", "text": msg["content"]})

            for tc in msg.get("tool_calls", []):
                try:
                    args = json.loads(tc["function"]["arguments"])
                except Exception:
                    args = {}
                blocks.append({
                    "type":  "tool_use",
                    "id":    tc["id"],
                    "name":  tc["function"]["name"],
                    "input": args
                })

            return blocks if blocks else [{"type": "text", "text": "任务完成"}]

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            # Auto-retry on context length exceeded: compact and retry once
            if e.code == 400 and "context length" in err_body.lower():
                self._log("API错误", "上下文超限，正在压缩消息重试...")
                compacted = self._compact_messages(messages, max_chars=40000)
                if len(compacted) < len(messages):
                    body["messages"] = msgs[:1] + []  # rebuild with compacted
                    # Re-convert compacted messages to OpenAI format
                    new_msgs = []
                    if system:
                        new_msgs.append({"role": "system", "content": system})
                    for m in compacted:
                        role = m.get("role", "user")
                        content = m.get("content", "")
                        if isinstance(content, str):
                            new_msgs.append({"role": role, "content": content})
                        elif isinstance(content, list):
                            # tool_result blocks
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "tool_result":
                                    new_msgs.append({
                                        "role": "tool",
                                        "tool_call_id": block.get("tool_use_id", ""),
                                        "content": block.get("content", "")[:1000]
                                    })
                    body["messages"] = new_msgs
                    try:
                        payload2 = json.dumps(body, ensure_ascii=False).encode("utf-8")
                        req2 = urllib.request.Request(
                            api_url,
                            data=payload2,
                            headers={
                                "Content-Type": "application/json; charset=utf-8",
                                "Authorization": f"Bearer {self.llm.api_key}"
                            }
                        )
                        with urllib.request.urlopen(req2, timeout=60) as resp2:
                            data = json.loads(resp2.read().decode("utf-8"))
                        msg = data["choices"][0]["message"]
                        blks = []
                        if msg.get("content"):
                            blks.append({"type": "text", "text": msg["content"]})
                        for tc in msg.get("tool_calls", []):
                            try:
                                args = json.loads(tc["function"]["arguments"])
                            except Exception:
                                args = {}
                            blks.append({"type": "tool_use", "id": tc["id"],
                                         "name": tc["function"]["name"], "input": args})
                        return blks if blks else [{"type": "text", "text": "任务完成"}]
                    except Exception:
                        pass
            self._log("API错误", f"HTTP {e.code}: {err_body[:600]}")
            return [{"type": "text",
                     "text": f"API调用失败 HTTP {e.code}: {err_body[:300]}"}]
        except Exception as e:
            return [{"type": "text", "text": f"API调用失败: {e}"}]

    def _call_ollama_tools(
        self, messages, system, tools, max_tokens
    ) -> List[Dict]:
        """
        Ollama 工具调用（手动 ReAct 格式）
        Ollama 不原生支持 function calling，改为 prompt 内嵌工具描述
        让模型用 JSON 格式输出工具调用意图，再由 Python 解析执行
        """
        import json, re

        # 构建工具描述 prompt
        tool_desc_lines = []
        for t in tools:
            fn = t.get("function", t)
            name = fn.get("name", "")
            desc = fn.get("description", "")
            params = fn.get("parameters", {}).get("properties", {})
            param_str = ", ".join(
                f"{k}: {v.get('type','any')} ({v.get('description','')})"
                for k, v in params.items()
            )
            tool_desc_lines.append(f"  - {name}({param_str}): {desc}")

        tools_prompt = "\n".join(tool_desc_lines)

        # 组装系统提示（含工具说明）
        full_system = (
            (system or "") + "\n\n"
            "【可用工具】\n" + tools_prompt + "\n\n"
            "【调用规则】\n"
            "如需调用工具，必须且只能输出以下格式的 JSON（不加 markdown 代码块）：\n"
            '{"tool_call": {"name": "工具名", "arguments": {参数}}}\n'
            "如果不需要工具，直接输出文字回答。\n"
            "工具执行结果会以 [TOOL_RESULT: ...] 形式追加到消息中，你再基于结果继续回答。"
        )

        # 构建消息列表（转换 tool_result 块为文本）
        ollama_messages = []
        if full_system:
            ollama_messages.append({"role": "system", "content": full_system})

        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if isinstance(content, list):
                # 把 tool_result 块拼成文本
                parts = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "tool_result":
                            parts.append(f"[TOOL_RESULT: {item.get('content', '')}]")
                        elif item.get("type") == "text":
                            parts.append(item.get("text", ""))
                content = "\n".join(parts)
            ollama_messages.append({"role": role, "content": content})

        # 调用 Ollama
        raw = self.llm.generate(
            prompt="",
            messages=ollama_messages,
            max_tokens=max_tokens,
            temperature=0.3
        )

        # 尝试解析工具调用 JSON
        try:
            m = re.search(r'\{[\s\S]*"tool_call"[\s\S]*\}', raw)
            if m:
                data = json.loads(m.group())
                tc = data.get("tool_call", {})
                tool_name = tc.get("name", "")
                tool_args = tc.get("arguments", {})
                if tool_name:
                    return [{
                        "type": "tool_use",
                        "id": f"ollama_{id(raw) % 9999:04d}",
                        "name": tool_name,
                        "input": tool_args
                    }]
        except (json.JSONDecodeError, AttributeError):
            pass

        # 纯文本回答
        return [{"type": "text", "text": raw}]

    def _call_react_tools(
        self, messages, system, tools, max_tokens
    ) -> List[Dict]:
        """
        ReAct prompt 方式（Claude / Gemini 通用）
        工具描述内嵌到 system prompt，LLM 输出 JSON 格式的工具调用，
        由 Python 解析执行。支持 function calling 的 Claude/Gemini 可
        升级为原生格式以获得更好效果。
        """
        import json as _json, re as _re

        # 构建工具描述 prompt
        tool_desc_lines = []
        for t in tools:
            fn = t.get("function", t)
            name = fn.get("name", "")
            desc = fn.get("description", "")
            params = fn.get("parameters", {}).get("properties", {})
            param_str = ", ".join(
                f"{k}: {v.get('type','any')} ({v.get('description','')})"
                for k, v in params.items()
            )
            tool_desc_lines.append(f"  - {name}({param_str}): {desc}")

        tools_prompt = "\n".join(tool_desc_lines)

        # 组装系统提示（含工具说明）
        full_system = (
            (system or "") + "\n\n"
            "【可用工具】\n" + tools_prompt + "\n\n"
            "【调用规则】\n"
            "如需调用工具，必须且只能输出以下格式的 JSON（不加 markdown 代码块）：\n"
            '{"tool_call": {"name": "工具名", "arguments": {参数}}}\n'
            "如果不需要工具，直接输出文字回答。\n"
            "工具执行结果会以 [TOOL_RESULT: ...] 形式追加到消息中，你再基于结果继续回答。"
        )

        # 构建消息列表（转换 tool_result 块为文本）
        react_messages = []
        if full_system:
            react_messages.append({"role": "system", "content": full_system})

        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "tool_result":
                            parts.append(f"[TOOL_RESULT: {item.get('content', '')}]")
                        elif item.get("type") == "text":
                            parts.append(item.get("text", ""))
                content = "\n".join(parts)
            react_messages.append({"role": role, "content": content})

        # 调用 LLM
        raw = self.llm.generate(
            prompt="",
            messages=react_messages,
            max_tokens=max_tokens,
            temperature=0.3
        )

        # 尝试解析工具调用 JSON
        try:
            m = _re.search(r'\{[\s\S]*"tool_call"[\s\S]*\}', raw)
            if m:
                data = _json.loads(m.group())
                tc = data.get("tool_call", {})
                tool_name = tc.get("name", "")
                tool_args = tc.get("arguments", {})
                if tool_name:
                    return [{
                        "type": "tool_use",
                        "id": f"react_{id(raw) % 9999:04d}",
                        "name": tool_name,
                        "input": tool_args
                    }]
        except (_json.JSONDecodeError, AttributeError):
            pass

        # 纯文本回答
        return [{"type": "text", "text": raw}]

    def _call_mock_tools(self, messages, tools) -> List[Dict]:
        """Mock 模式：模拟工具调用用于测试"""
        last_msg = messages[-1] if messages else {}
        content = ""
        if isinstance(last_msg.get("content"), str):
            content = last_msg["content"]
        elif isinstance(last_msg.get("content"), list):
            for item in last_msg["content"]:
                if isinstance(item, dict) and item.get("type") == "tool_result":
                    return [{"type": "text",
                             "text": f"工具执行完成。结果：{item.get('content', '')[:200]}"}]

        # 根据关键词决定调用哪个工具
        if "列出" in content or "list" in content.lower() or "目录" in content:
            return [{"type": "tool_use", "id": "mock_1",
                     "name": "list_directory", "input": {"path": "."}}]
        elif "搜索" in content or "查找" in content:
            return [{"type": "tool_use", "id": "mock_2",
                     "name": "web_search", "input": {"query": content[:50]}}]
        elif "运行" in content or "执行" in content:
            return [{"type": "tool_use", "id": "mock_3",
                     "name": "run_command", "input": {"command": "echo 'Mock执行'"}}]
        else:
            return [{"type": "text",
                     "text": "（Mock模式）我明白了你的需求，请配置真实 API Key 获得完整工具执行能力。"}]

    def _get_available_schemas(self) -> List[Dict]:
        schemas = get_all_schemas()
        if self.allowed_tools is not None:
            schemas = [
                s for s in schemas
                if s["name"] in self.allowed_tools
            ]
        # 追加动态工具（LLM之前学会的技能）
        for name, info in self._dynamic_tools.items():
            if self.allowed_tools is not None and name not in self.allowed_tools:
                continue
            schemas.append({
                "name": name,
                "description": f"[自学习工具] {info['description']}",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "task_description": {
                            "type": "string",
                            "description": "任务描述（此工具为自动生成的代码，参数将被忽略，直接执行已注册的代码）"
                        }
                    }
                }
            })
        return schemas

    def _build_system_prompt(self, context: str) -> str:
        tools_list = ", ".join(
            name for name in (self.allowed_tools or list(TOOL_REGISTRY.keys()))
        )
        base = f"""你是一个强大的 AI 执行助手，必须通过调用工具完成任务，不能只用文字回答。

可用工具：{tools_list}

核心规则（必须严格遵守）：
1. 收到任务后，立即决定调用哪个工具，直接发出工具调用请求
2. 生成文档/文件类任务：必须调用对应的文件工具（create_pdf 调 create_pdf，Word 调 create_docx，其他调 write_file），把内容写入文件
3. 搜索类任务：必须调用 web_search 工具
4. 执行命令类任务：必须调用 run_command 工具
5. 搜索到足够信息后，必须立即执行最终操作（写文件/生成文档等），不要只做搜索不做事
6. 工具执行完成后，用一句话总结结果
7. 高风险操作前简要说明意图
8. 如果前一步工具已返回所需数据，直接基于该数据生成最终答案，不要再调用不必要的工具
9. 回答必须基于工具返回的真实数据，直接引用原始内容，禁止用"通常""可能""应该"等推测性语言编造内容"""

        if context:
            base += f"\n\n任务背景：\n{context}"

        return base

    def _summarize_large_content(self, content: str, file_path: str = "") -> str:
        """
        对大文本进行分段摘要（Map-Reduce）。
        分段大小 40000 字符，每段摘要不超过 2000 字，最后合并。
        """
        CHUNK_SIZE = 40000
        SUMMARY_MAX = 2000

        if len(content) <= 8000:
            return content  # 短文本不需要摘要

        chunks = []
        for i in range(0, len(content), CHUNK_SIZE):
            chunks.append(content[i:i + CHUNK_SIZE])

        self._log("长文本", f"文件 {len(content)} 字符，分为 {len(chunks)} 段进行摘要")

        chunk_summaries = []
        for idx, chunk in enumerate(chunks):
            prompt = (
                f"请对以下文本的第 {idx + 1}/{len(chunks)} 段进行详细摘要。\n"
                f"要求：\n"
                f"1. 【必须保留】所有人物名字、角色名（包括昵称）、地名、组织名\n"
                f"2. 【必须保留】所有关键事件、情节转折、重要对话的核心内容\n"
                f"3. 【必须保留】所有数据、数字、时间、金额等具体信息\n"
                f"4. 保留原文的结构层次（章节/段落）\n"
                f"5. 用不超过 {SUMMARY_MAX} 字概括\n"
                f"6. 直接输出摘要内容，不要加\"摘要：\"等前缀\n\n"
                f"---文本开始---\n{chunk}\n---文本结束---"
            )
            try:
                summary = self.llm.generate(
                    prompt=prompt,
                    max_tokens=SUMMARY_MAX * 2,
                    temperature=0.3
                )
                chunk_summaries.append(summary.strip())
            except Exception as e:
                self._log("长文本", f"第 {idx + 1} 段摘要失败: {e}，使用截断代替")
                chunk_summaries.append(chunk[:SUMMARY_MAX] + f"\n...[本段截断，共{len(chunk)}字]")

        combined = "\n\n".join(
            f"【第 {i + 1}/{len(chunk_summaries)} 部分】\n{s}"
            for i, s in enumerate(chunk_summaries)
        )

        header = ""
        if file_path:
            header = f"[文件: {file_path}，共 {len(content)} 字符，已分段摘要为 {len(combined)} 字符]\n\n"

        # 如果合并后仍然太长，再做一轮最终压缩
        if len(combined) > 6000:
            try:
                final_prompt = (
                    f"以下是一份长文件的分段摘要（共 {len(chunk_summaries)} 段），"
                    f"请合并为一份不超过 4000 字的完整摘要。\n"
                    f"【必须保留】所有人名、角色名、地名、组织名、关键事件、数据。\n"
                    f"保持结构层次。直接输出摘要，不加前缀。\n\n{combined}"
                )
                combined = self.llm.generate(
                    prompt=final_prompt,
                    max_tokens=8000,
                    temperature=0.3
                ).strip()
                header = header.replace("已分段摘要", "已分段摘要并压缩")
            except Exception:
                pass

        return header + combined

    def _process_large_tool_result(self, result: dict, tool_name: str) -> dict:
        """
        检测工具返回的大文本内容，自动分段摘要。
        目前处理：read_file、read_office 返回的大文本。
        """
        # 只对有 content 字段的文件读取工具做摘要
        _summary_tools = {"read_file", "read_office"}
        if tool_name not in _summary_tools:
            return result

        content = result.get("content", "")
        if not content or len(content) <= 8000:
            return result

        file_path = result.get("path", "")
        summarized = self._summarize_large_content(content, file_path)
        result["content"] = summarized
        result["_summarized"] = True
        result["_original_chars"] = len(content)
        self._log("长文本", f"{tool_name} 内容已摘要：{len(content)} → {len(summarized)} 字符")
        return result

    @staticmethod
    def _truncate_tool_result(result: dict, max_chars: int = 3000) -> str:
        """Truncate tool result to prevent context overflow"""
        raw = json.dumps(result, ensure_ascii=False)
        if len(raw) <= max_chars:
            return raw
        # Keep summary/error info, truncate bulky content
        truncated = {k: v for k, v in result.items()
                     if k in ("ok", "error", "type", "path", "summary", "tip",
                              "_summarized", "_original_chars")}
        if "ok" in result:
            truncated["_truncated"] = True
            truncated["_original_chars"] = len(raw)
        return json.dumps(truncated, ensure_ascii=False)

    def _compact_messages(self, messages: list, max_chars: int = 80000) -> list:
        """
        Compact message history to fit within context budget.
        Keeps the first (task) and last (recent) messages, summarizes the middle.
        """
        total = sum(len(json.dumps(m, ensure_ascii=False)) for m in messages)
        if total <= max_chars:
            return messages

        # Keep first message (task) and last 4 messages
        if len(messages) <= 6:
            return messages

        kept = messages[:1] + messages[-4:]
        # Summarize the middle part
        middle_count = len(messages) - 5
        summary_msg = {
            "role": "user",
            "content": f"[中间 {middle_count} 条消息已压缩以节省上下文空间]"
        }
        return messages[:1] + [summary_msg] + messages[-4:]

    @staticmethod
    def _classify_retry_hint(tool_name: str, error_msg: str,
                             fail_count: int, max_retries: int) -> str:
        """根据错误类型生成不同的重试提示"""
        err_lower = error_msg.lower()
        remaining = max_retries - fail_count

        # 网络限流 / 超时
        if any(kw in err_lower for kw in
               ["rate limit", "too many requests", "429", "timeout", "timed out"]):
            return (
                f"[工具失败] {tool_name} 执行失败：{error_msg}\n"
                f"这是网络限流或超时，不是参数错误。"
                f"请稍后再试同一个工具，或换用其他工具获取同类信息（还可重试 {remaining} 次）。"
            )

        # SSL / 证书错误 → 能力缺口，建议用run_python绕过
        if any(kw in err_lower for kw in
               ["ssl", "certificate", "cert_verify", "certificate_verify_failed"]):
            return (
                f"[工具失败·能力缺口] {tool_name} 遇到SSL证书问题：{error_msg}\n"
                f"这是工具本身的能力限制。如果多次失败，系统会自动尝试用run_python编写代码绕过此限制。"
            )

        # 依赖缺失 → 能力缺口
        if "no module named" in err_lower or "module not found" in err_lower:
            return (
                f"[工具失败·能力缺口] {tool_name} 缺少依赖：{error_msg}\n"
                f"此工具当前不可用，请换用其他工具完成此任务。"
            )

        # 文件不存在 / 路径错误
        if any(kw in err_lower for kw in ["no such file", "not found", "does not exist"]):
            return (
                f"[工具失败] {tool_name} 执行失败：{error_msg}\n"
                f"文件或路径不存在，请检查路径是否正确，或换用其他工具。"
            )

        # 权限不足
        if any(kw in err_lower for kw in ["permission", "access denied", "forbidden", "403"]):
            return (
                f"[工具失败] {tool_name} 执行失败：{error_msg}\n"
                f"权限不足或被拒绝访问，请换用其他方式或工具。"
            )

        # 默认：参数错误
        return (
            f"[工具失败] {tool_name} 执行失败：{error_msg}\n"
            f"请检查参数是否正确，或换用其他工具重试（还可重试 {remaining} 次）。"
        )

    def _try_python_fallback(
        self,
        original_task: str,
        failed_steps: List[Dict],
        messages: List[Dict],
        system_prompt: str,
        max_tokens: int
    ) -> Optional[Dict]:
        """
        工具连续失败后的run_python兜底。
        让LLM自己写代码解决问题，成功则注册为动态工具。
        返回 {"result": str, "steps": list} 或 None（兜底失败）
        """
        self._python_fallback_attempted = True
        self._log("兜底", "现有工具无法完成，尝试用 run_python 自写代码解决")

        # 整理失败历史，让LLM理解哪里卡住了
        failure_summary = "\n".join([
            f"- {s['tool']}：{s['result'].get('error', '失败')}"
            for s in failed_steps if not s['result'].get('ok')
        ])

        fallback_prompt = (
            f"你在执行任务时，以下工具调用均失败了：\n{failure_summary}\n\n"
            f"原始任务：{original_task}\n\n"
            f"请用 run_python 工具，直接编写Python代码来完成这个任务。\n"
            f"要求：\n"
            f"1. 代码必须完整可执行，包含所有必要的import\n"
            f"2. 把最终结果用 print() 输出\n"
            f"3. 如果是网络请求，用requests库并设置verify=False和timeout=10\n"
            f"4. 代码里加上简短注释说明做了什么\n"
            f"现在直接调用 run_python 工具。"
        )

        # 确认是否允许执行（高风险）
        allowed = self.confirm("run_python(自动生成代码)", {"task": original_task[:100]})
        if not allowed:
            self._log("兜底", "用户拒绝执行自动生成代码")
            return None

        try:
            schemas = self._get_available_schemas()
            fb_messages = [{"role": "user", "content": fallback_prompt}]
            response = self._call_llm_with_tools(
                messages=fb_messages,
                system=system_prompt,
                tools=schemas,
                max_tokens=max_tokens
            )

            for block in response:
                if block.get("type") == "tool_use" and block.get("name") == "run_python":
                    code = block.get("input", {}).get("code", "")
                    if not code:
                        continue

                    self._log("兜底·代码", f"执行自动生成代码（{len(code)}字符）")
                    result_content = execute_tool("run_python", {"code": code})

                    if result_content.get("ok"):
                        output = result_content.get("output", "")
                        self._log("兜底·成功", f"代码执行成功：{output[:100]}")

                        # 尝试把这段代码注册为动态工具，方便下次复用
                        tool_name = self._auto_name_dynamic_tool(original_task)
                        self._register_dynamic_tool(
                            name=tool_name,
                            code=code,
                            description=f"自动生成：{original_task[:80]}"
                        )

                        return {
                            "result": output or "代码执行完成",
                            "steps": [{"step": "fallback", "tool": "run_python",
                                       "params": {"code": code[:200]},
                                       "result": result_content}]
                        }
                    else:
                        self._log("兜底·失败", f"自动代码执行失败：{result_content.get('error','')}")
                        return None

        except Exception as e:
            self._log("兜底·异常", str(e))
            return None

        return None

    def _register_dynamic_tool(self, name: str, code: str, description: str):
        """
        把LLM写的Python代码注册为可复用的动态工具。
        注册后会出现在工具列表里，B层下次遇到类似问题可以直接调用。
        """
        try:
            ns: Dict = {}
            exec(code, ns)
            # 找到code里定义的第一个函数作为工具入口
            fn = next((v for v in ns.values() if callable(v)), None)

            self._dynamic_tools[name] = {
                "fn": fn,
                "code": code,
                "description": description
            }
            self._log("注册", f"动态工具已注册：{name}（{description[:50]}）")
        except Exception as e:
            # 注册失败不影响主流程，代码已经执行过了
            self._log("注册·跳过", f"{name} 注册失败（代码无法作为函数调用）：{e}")

    def _execute_dynamic_tool(self, name: str) -> Dict:
        """执行已注册的动态工具，返回结果"""
        info = self._dynamic_tools.get(name)
        if not info or not info.get("fn"):
            return {"ok": False, "error": f"动态工具 '{name}' 不可用"}
        try:
            import io, sys
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            result = info["fn"]()
            output = sys.stdout.getvalue()
            sys.stdout = old_stdout
            return {"ok": True, "output": output or str(result or "")}
        except Exception as e:
            return {"ok": False, "error": f"动态工具执行出错: {e}"}

    def get_dynamic_tools_summary(self) -> str:
        """返回已注册动态工具的摘要，供A层感知"""
        if not self._dynamic_tools:
            return ""
        lines = [f"已学会 {len(self._dynamic_tools)} 个新技能："]
        for name, info in self._dynamic_tools.items():
            lines.append(f"  · {name}：{info['description'][:60]}")
        return "\n".join(lines)

    @staticmethod
    def _auto_name_dynamic_tool(task: str) -> str:
        """根据任务描述自动生成工具名"""
        import re
        # 取前20个中文或英文字符，转成snake_case
        clean = re.sub(r'[^\w\u4e00-\u9fff]', '_', task[:20]).strip('_')
        return f"dynamic_{clean}" if clean else "dynamic_tool"

    def _summarize_steps(self, steps: list, tools_used: list) -> str:
        """汇总已完成的步骤，用于超限/失败时的部分结果返回"""
        if not steps:
            return "没有执行任何步骤。"

        lines = [f"已完成 {len(steps)} 个步骤：\n"]

        for s in steps:
            tool = s.get("tool", "?")
            result = s.get("result", {})
            ok = "✅" if result.get("ok") else "❌"
            error = result.get("error", "")
            summary = result.get("summary", "") or result.get("path", "")

            detail = f"{ok} **{tool}**"
            if summary:
                detail += f" → {str(summary)[:100]}"
            elif error:
                detail += f" → 失败: {str(error)[:80]}"
            lines.append(f"  步骤 {s.get('step', '?')}: {detail}")

        return "\n".join(lines)
