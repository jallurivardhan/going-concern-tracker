"""Tier-2 LLM classification layer.

Reads each AuditorReport from the database, sends it to Claude via Instructor,
receives a validated Pydantic response, and writes a GoingConcernFlag row.

Public surface:
    classify_auditor_report()  — classify one report (async)
    ClaudeClassifier           — reusable Claude + Instructor + Langfuse client
"""
