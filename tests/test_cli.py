import sys
import pytest

from teacherflow import _cli


def test_cli_accepts_course_and_major(monkeypatch, capsys):
    """CLI should put course and major into shared student_data."""
    # stub Database.get
    class DummyDB:
        def get(self, student_id):
            return {"Full Name": "Test Student"}
    monkeypatch.setattr(_cli, "Database", lambda: DummyDB())

    # stub flow to capture shared data
    captured = {}
    class DummyFlow:
        def run(self, shared):
            # mimic a flow by capturing and providing conclusion
            captured.update(shared)
            shared["teacher_conclusion"] = "Dummy conclusion"
    import teacherflow.flow as flow_mod
    # patch both the flow module and the CLI's imported reference
    monkeypatch.setattr(flow_mod, "create_teacher_flow", lambda: DummyFlow())
    monkeypatch.setattr(_cli, "create_teacher_flow", lambda: DummyFlow())

    # also stub out LLM calls so flow.run doesn't hit network
    # return minimal valid profile/other keys for each call
    # stub returns minimal JSON including both profile and priority
    def stub(prompt, use_cache=True):
        # return minimal valid structure depending on node type
        if "learning_priority" in prompt:
            return "```json\n{\"learning_priority\": []}\n```"
        if "knowledge_to_discover" in prompt:
            return "```json\n{\"knowledge_to_discover\": []}\n```"
        if "oral_assessment" in prompt:
            return "```json\n{\"oral_assessment\": {\"summary\": \"\", \"adjustments\": []}}\n```"
        # default: profile
        return "```json\n{\"student_profile\": {\"subjects\": []}}\n```"
    monkeypatch.setattr("teacherflow.utils.call_llm.call_llm", stub)
    monkeypatch.setattr("teacherflow.nodes.call_llm", stub)

    monkeypatch.setattr(sys, "argv", ["prog", "--student-id", "foo", "--course", "3", "--major", "Physics"])
    _cli.main()

    assert captured["student_data"]["Course"] == "3"
    assert captured["student_data"]["Major"] == "Physics"
    # ensure no errors printed
    captured_out = capsys.readouterr().out
    assert "Generating teacher feedback" in captured_out
