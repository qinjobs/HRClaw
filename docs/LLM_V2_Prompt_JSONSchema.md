# LLM V2 Prompt + JSON Schema（可直接接入）

## 1) System Prompt（建议固定）
```text
Extract only fields supported by visible resume evidence.
Output one pure JSON object (no markdown) that strictly follows CandidateExtractionV2 schema.
If evidence is missing, use null (for scalar) or [] (for list) and explain in evidence_map.
Never infer hidden facts.
```

## 2) User Prompt 模板（直接喂给模型）
```text
你是“简历结构化抽取引擎”，当前岗位 job_id={{job_id}}。
只允许依据可见简历文本，不得臆测，不得补全隐含信息。

请输出一个 JSON 对象（不要 markdown，不要解释文本），必须满足以下规则：
1. 顶层字段必须完整且仅包含这些键：
name, age, education_level, major, years_experience, current_company, current_title,
expected_salary, location, last_active_time, skills, industry_tags, certificates,
project_keywords, resume_summary, evidence_map, normalized_fields
2. 缺失值规则：标量字段用 null；列表字段用 []
3. evidence_map 必须写明关键字段证据，建议用字段名作为 key（例如 years_experience / testing_evidence）
4. normalized_fields 仅输出“有明确证据支撑”的字段
5. 所有 level 类字段范围必须是 [0,1]

岗位特定 normalized_fields 约束：
{{job_contract}}

必须遵循的 JSON Schema：
{{schema_json}}

简历页面文本（截断）：
{{page_text}}
```

## 3) Job Contract（按 job_id 选择其一）

### qa_test_engineer_v1
```text
normalized_fields must include keys below when evidence exists:
- testing_evidence: boolean
- qa_role_history_evidence: boolean
- has_test_engineer_experience: boolean
- has_api_testing_experience: boolean
- has_app_testing_experience: boolean
- has_web_testing_experience: boolean
- core_test_depth_level: number in [0,1]
- tools: string[]
- frontend_backend_test: boolean
- defect_closure_level: number in [0,1]
- industry_tags: string[]
- analysis_logic_level: number in [0,1]
```

### py_dev_engineer_v1
```text
normalized_fields must include keys below when evidence exists:
- linux_experience: boolean
- python_engineering_level: number in [0,1]
- linux_shell_level: number in [0,1]
- java_support_level: number in [0,1]
- middleware: string[]
- security_fit_level: number in [0,1]
- analysis_design_level: number in [0,1]
```

### caption_aesthetic_qc_v1
```text
normalized_fields must include keys below when evidence exists:
- media_caption_evidence: boolean
- writing_sample: boolean
- aesthetic_writing_level: number in [0,1]
- film_art_theory_level: number in [0,1]
- ai_annotation_qc_level: number in [0,1]
- visual_domain_tags: string[]
- watching_volume_level: number in [0,1]
- english_level: number in [0,1]
- portfolio_level: number in [0,1]
- gender: string|null
```

### caption_ai_trainer_zhengzhou_v1
```text
normalized_fields must include keys below when evidence exists:
- zhengzhou_intent: boolean
- full_time_education: boolean
- graduation_year: number|null
- writing_sample: boolean
- rule_execution_evidence: boolean
- writing_naturalness_level: number in [0,1]
- reading_rule_follow_level: number in [0,1]
- visual_analysis_level: number in [0,1]
- film_language_level: number in [0,1]
- output_stability_level: number in [0,1]
- ai_annotation_experience_level: number in [0,1]
- long_term_stability_level: number in [0,1]
```

## 4) CandidateExtractionV2 JSON Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "CandidateExtractionV2",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "name",
    "age",
    "education_level",
    "major",
    "years_experience",
    "current_company",
    "current_title",
    "expected_salary",
    "location",
    "last_active_time",
    "skills",
    "industry_tags",
    "certificates",
    "project_keywords",
    "resume_summary",
    "evidence_map",
    "normalized_fields"
  ],
  "properties": {
    "name": { "type": ["string", "null"] },
    "age": { "type": ["integer", "null"], "minimum": 16, "maximum": 80 },
    "education_level": { "type": ["string", "null"] },
    "major": { "type": ["string", "null"] },
    "years_experience": { "anyOf": [{ "type": "number" }, { "type": "string" }, { "type": "null" }] },
    "current_company": { "type": ["string", "null"] },
    "current_title": { "type": ["string", "null"] },
    "expected_salary": { "type": ["string", "null"] },
    "location": { "type": ["string", "null"] },
    "last_active_time": { "type": ["string", "null"] },
    "skills": { "type": "array", "items": { "type": "string" } },
    "industry_tags": { "type": "array", "items": { "type": "string" } },
    "certificates": { "type": "array", "items": { "type": "string" } },
    "project_keywords": { "type": "array", "items": { "type": "string" } },
    "resume_summary": { "type": ["string", "null"] },
    "evidence_map": {
      "type": "object",
      "additionalProperties": {
        "anyOf": [
          { "type": "string" },
          { "type": "number" },
          { "type": "boolean" },
          { "type": "null" },
          { "type": "array", "items": { "type": "string" } }
        ]
      }
    },
    "normalized_fields": {
      "type": "object",
      "additionalProperties": {
        "anyOf": [
          { "type": "string" },
          { "type": "number" },
          { "type": "boolean" },
          { "type": "null" },
          { "type": "array", "items": { "type": "string" } }
        ]
      }
    }
  }
}
```
