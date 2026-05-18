from __future__ import annotations

import json
import os

from src.screening.config import load_local_env
from src.screening.gpt_extractor import GPTFieldExtractor


def main() -> None:
    load_local_env()
    os.environ.setdefault("SCREENING_EXTRACTION_PROVIDER", "kimi_cli")
    os.environ.setdefault("SCREENING_ENABLE_MODEL_EXTRACTION", "true")
    os.environ.setdefault("SCREENING_EXTRACTION_MODEL", "kimi-for-coding")
    os.environ.setdefault("SCREENING_KIMI_CLI_COMMAND", "kimi")

    sample_resume_text = """
候选人：王某某，29岁，本科，计算机科学与技术。
5年测试经验，负责Web与接口自动化测试。
熟悉Linux、MySQL、Postman、JMeter、Charles、Python+pytest。
期望职位：测试工程师，期望薪资15-20K。
"""

    extractor = GPTFieldExtractor()
    result = {
        "enabled": extractor.enabled,
        "provider": extractor.provider,
        "model": extractor.model,
        "cli_command": extractor.kimi_cli_command,
    }
    if not extractor.enabled:
        result["ok"] = False
        result["error"] = "Kimi CLI bridge is not enabled. Check SCREENING_KIMI_CLI_COMMAND and CLI installation."
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    try:
        payload = extractor.extract_candidate("qa_test_engineer_v1", sample_resume_text)
        result["ok"] = True
        result["usage"] = extractor.last_usage
        result["parsed_fields"] = {
            "name": payload.get("name"),
            "age": payload.get("age"),
            "education_level": payload.get("education_level"),
            "years_experience": payload.get("years_experience"),
            "skills_count": len(payload.get("skills", []) if isinstance(payload.get("skills"), list) else []),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        result["ok"] = False
        result["error"] = str(exc)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
