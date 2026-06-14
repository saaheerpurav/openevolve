"""
Claude / Codex / OpenAI mutators for TDES repair experiments.

Priority order for the ClaudeMutator factory:
  1. CodexMutator — OpenAI API key from ~/.codex/auth.json (codex CLI session)
  2. ClaudeAPIMutator — Anthropic SDK if ANTHROPIC_API_KEY is set
  3. ClaudeCLIMutator — claude CLI session auth (no key needed)

Uses the locally installed Claude Code CLI (`claude -p`) so no ANTHROPIC_API_KEY
is required — the existing Claude Code session auth is reused automatically.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional

from openevolve.tdes import prompts
from openevolve.tdes.mutation import MutationProposal
from openevolve.tdes.types import Candidate, FeedbackTuple
from openevolve.utils.code_utils import apply_diff, extract_diffs, parse_full_rewrite

logger = logging.getLogger(__name__)

_SUMMARY_RE = re.compile(r"SUMMARY:\s*(.+)", re.IGNORECASE)

DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_CODEX_MODEL = "gpt-5.5"


def _extract_summary(response: str, default: str) -> str:
    m = _SUMMARY_RE.search(response)
    return m.group(1).strip() if m else default


def _parse_response(source: str, text: str, diff_based: bool) -> Optional[str]:
    """Extract new module source from LLM response text.

    Only accepts structured output (SEARCH/REPLACE blocks or fenced code blocks).
    Never falls back to raw text — prose responses that lack code markers are
    rejected so they don't get written to disk as syntactically broken Python.
    """
    if diff_based:
        diffs = extract_diffs(text)
        if diffs:
            new_source = apply_diff(source, text)
            if new_source != source:
                return new_source

    # Only accept explicitly fenced code blocks, not raw text.
    import re
    matches = re.findall(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
    if matches:
        rewritten = matches[0].strip()
        if rewritten and rewritten != source:
            return rewritten
    return None


# ── CLI-backed mutator (uses existing Claude Code session) ──────────────────

async def _call_claude_cli(
    prompt: str,
    system: str,
    model: str,
    timeout: int = 300,
) -> Optional[str]:
    """Call `claude -p /dev/stdin` as a subprocess, piping the prompt via stdin.

    Using stdin avoids Windows 32 KB command-line argument limits, which would
    silently truncate large prompts (e.g. 500+ line source files).
    """
    full_prompt = f"<system>\n{system}\n</system>\n\n{prompt}"
    cmd = [
        "claude",
        "--model", model,
        "-p", "/dev/stdin",
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=full_prompt.encode("utf-8")),
            timeout=timeout,
        )
        text = stdout.decode("utf-8", errors="replace").strip()
        if proc.returncode != 0 or not text:
            err = stderr.decode("utf-8", errors="replace")[:300]
            logger.warning("claude CLI returned rc=%d: %s", proc.returncode, err)
            return None
        return text
    except asyncio.TimeoutError:
        logger.warning("claude CLI timed out after %ds", timeout)
        try:
            proc.kill()
        except Exception:
            pass
        return None
    except Exception as e:
        logger.error("claude CLI call failed: %s", e)
        return None


class ClaudeCLIMutator:
    """
    Mutator backed by the locally installed Claude Code CLI.
    No API key required — uses existing Claude Code session auth.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        diff_based: bool = True,
        timeout: int = 300,
    ):
        self.model = model
        self.diff_based = diff_based
        self.timeout = timeout

    async def propose(
        self,
        *,
        candidate: Candidate,
        module: str,
        feedback: List[FeedbackTuple],
        memory_text: str,
        generation: int,
    ) -> Optional[MutationProposal]:
        source = candidate.modules[module]
        user_prompt = prompts.build_user_prompt(
            module_name=module,
            module_source=source,
            feedback=feedback,
            memory_text=memory_text,
            diff_based=self.diff_based,
            generation=generation,
        )
        text = await _call_claude_cli(
            prompt=user_prompt,
            system=prompts.SYSTEM_MESSAGE,
            model=self.model,
            timeout=self.timeout,
        )
        if not text:
            return None

        approach = _extract_summary(text, default=f"Claude edit to {module}")
        new_source = _parse_response(source, text, self.diff_based)
        if new_source is None:
            logger.warning("ClaudeCLIMutator: no usable output for module %s", module)
            return None
        return MutationProposal(module, new_source, approach)


# ── SDK-backed mutator (fallback when ANTHROPIC_API_KEY is set) ─────────────

class ClaudeAPIMutator:
    """
    Mutator backed by the Anthropic Python SDK.
    Requires ANTHROPIC_API_KEY in the environment.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 4096,
        temperature: float = 0.8,
        diff_based: bool = True,
    ):
        import anthropic
        self.client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.diff_based = diff_based

    async def propose(
        self,
        *,
        candidate: Candidate,
        module: str,
        feedback: List[FeedbackTuple],
        memory_text: str,
        generation: int,
    ) -> Optional[MutationProposal]:
        source = candidate.modules[module]
        user_prompt = prompts.build_user_prompt(
            module_name=module,
            module_source=source,
            feedback=feedback,
            memory_text=memory_text,
            diff_based=self.diff_based,
            generation=generation,
        )
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=prompts.SYSTEM_MESSAGE,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except Exception as e:
            logger.error("Anthropic API call failed for module %s: %s", module, e)
            return None

        text = response.content[0].text if response.content else ""
        if not text:
            return None

        approach = _extract_summary(text, default=f"Claude edit to {module}")
        new_source = _parse_response(source, text, self.diff_based)
        if new_source is None:
            logger.warning("ClaudeAPIMutator: no usable output for module %s", module)
            return None
        return MutationProposal(module, new_source, approach)


# ── Codex CLI mutator (uses `codex exec` with ChatGPT session auth) ──────────

def _codex_executable() -> Optional[str]:
    """Return the full path to the codex CLI, or None if not found.

    On Windows, npm installs codex as codex.CMD which shutil.which finds
    but bare 'codex' in subprocess.run does not (no PATHEXT resolution).
    """
    import shutil
    return shutil.which("codex")


def _codex_on_path() -> bool:
    return _codex_executable() is not None


async def _call_codex_cli(
    prompt: str,
    system: str,
    reasoning_effort: str = "low",
    timeout: int = 300,
) -> Optional[str]:
    """Call `codex exec --ephemeral` via stdin, capture last message via temp file.

    Uses the codex CLI's ChatGPT session auth — no API key required.
    The full prompt (system + user) is written to a temp file and piped
    via stdin to avoid Windows arg-length limits.
    """
    import tempfile
    full_prompt = f"INSTRUCTIONS:\n{system}\n\n---\n\n{prompt}"

    response_fd, response_path = tempfile.mkstemp(suffix=".txt")
    os.close(response_fd)
    try:
        codex_bin = _codex_executable() or "codex"
        cmd = [
            codex_bin, "exec",
            "--ephemeral",
            "--ignore-rules",
            "-c", f"model_reasoning_effort={reasoning_effort}",
            "-o", response_path,
            "-",
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(
            proc.communicate(input=full_prompt.encode("utf-8")),
            timeout=timeout,
        )
        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace")[:300]
            logger.warning("codex exec returned rc=%d: %s", proc.returncode, err)
            return None
        with open(response_path, encoding="utf-8") as f:
            text = f.read().strip()
        if not text:
            logger.warning("codex exec returned empty response")
            return None
        return text
    except asyncio.TimeoutError:
        logger.warning("codex exec timed out after %ds", timeout)
        try:
            proc.kill()
        except Exception:
            pass
        return None
    except Exception as e:
        logger.error("codex exec call failed: %s", e)
        return None
    finally:
        try:
            os.unlink(response_path)
        except Exception:
            pass


class CodexMutator:
    """
    Mutator backed by the `codex exec` CLI (ChatGPT session auth, no API key).

    Uses gpt-5.5 with low reasoning effort by default — fast enough for TDES
    generation budgets while still producing high-quality code fixes.
    The response is captured via --output-last-message so stdout noise is ignored.
    """

    def __init__(
        self,
        diff_based: bool = False,
        reasoning_effort: str = "low",
        timeout: int = 300,
    ):
        self.diff_based = diff_based
        self.reasoning_effort = reasoning_effort
        self.timeout = timeout

    async def propose(
        self,
        *,
        candidate: Candidate,
        module: str,
        feedback: List[FeedbackTuple],
        memory_text: str,
        generation: int,
    ) -> Optional[MutationProposal]:
        source = candidate.modules[module]
        user_prompt = prompts.build_user_prompt(
            module_name=module,
            module_source=source,
            feedback=feedback,
            memory_text=memory_text,
            diff_based=self.diff_based,
            generation=generation,
        )
        text = await _call_codex_cli(
            prompt=user_prompt,
            system=prompts.SYSTEM_MESSAGE,
            reasoning_effort=self.reasoning_effort,
            timeout=self.timeout,
        )
        if not text:
            return None

        approach = _extract_summary(text, default=f"Codex edit to {module}")
        new_source = _parse_response(source, text, self.diff_based)
        if new_source is None:
            logger.warning(
                "CodexMutator: no usable output for module %s\nResponse preview: %.400s",
                module, text,
            )
            return None
        return MutationProposal(module, new_source, approach)


# ── Factory: pick the right mutator automatically ───────────────────────────

def ClaudeMutator(model: str = None, **kwargs):
    """
    Return the best available LLM mutator, in priority order:
      1. CodexMutator    — if `codex` CLI is on PATH (ChatGPT session auth)
      2. ClaudeAPIMutator — if ANTHROPIC_API_KEY is set
      3. ClaudeCLIMutator — if `claude` CLI is on PATH
    """
    if _codex_on_path():
        logger.info("Using CodexMutator (codex CLI, gpt-5.5, reasoning_effort=low)")
        codex_kwargs = {k: v for k, v in kwargs.items() if k in ("diff_based", "reasoning_effort", "timeout")}
        codex_kwargs.setdefault("reasoning_effort", "low")
        return CodexMutator(**codex_kwargs)

    if os.environ.get("ANTHROPIC_API_KEY"):
        claude_model = model or DEFAULT_MODEL
        logger.info("Using ClaudeAPIMutator (ANTHROPIC_API_KEY, model=%s)", claude_model)
        return ClaudeAPIMutator(model=claude_model, **{k: v for k, v in kwargs.items() if k in ("diff_based", "max_tokens", "temperature")})

    if _cli_on_path():
        claude_model = model or DEFAULT_MODEL
        logger.info("Using ClaudeCLIMutator (claude CLI session auth, model=%s)", claude_model)
        return ClaudeCLIMutator(model=claude_model, **{k: v for k, v in kwargs.items() if k in ("diff_based", "timeout")})

    raise RuntimeError(
        "No LLM backend available. Install codex CLI (`npm i -g @openai/codex`), "
        "set ANTHROPIC_API_KEY, or install Claude Code CLI."
    )


def _cli_on_path() -> bool:
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False
