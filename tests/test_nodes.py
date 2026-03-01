import pytest

from teacherflow.nodes import KnowledgeToDiscover


def test_knowledge_to_discover_skips_boolean(monkeypatch):
    """If the LLM returns a bare boolean in a fenced JSON block, exec() should return None.

    The old implementation would return False, causing the batch runner to
    treat the result list as containing a bool which later crashed during
    iteration. This test ensures the new defensive logic discards booleans.
    """
    node = KnowledgeToDiscover()
    # set attributes used by exec()
    node._student_profile = {"Full Name": "Test"}
    node._use_cache = False
    node.cur_retry = 0

    # monkeypatch the call_llm helper to simulate a boolean JSON response
    def fake_call_llm(prompt, use_cache=True):
        return "```json\nfalse\n```"

    monkeypatch.setattr("teacherflow.nodes.call_llm", fake_call_llm)

    result = node.exec("Math")
    assert result is None, "Expected exec() to return None when LLM output is boolean"


def test_post_raises_on_non_list():
    """post() should explicitly reject a non-list exec_res_list."""
    node = KnowledgeToDiscover()
    with pytest.raises(TypeError):
        node.post({}, None, True)  # pass a bool instead of a list


def test_assess_includes_course_and_major(monkeypatch):
    """AssessStudentLevel should include course/major from student_data in prompt."""
    from teacherflow.nodes import AssessStudentLevel

    node = AssessStudentLevel()
    node.cur_retry = 0

    def fake_call_llm(prompt, use_cache=True):
        assert "Course" in prompt or "course" in prompt.lower()
        assert "Major" in prompt or "major" in prompt.lower()
        return "```json\n{\"student_profile\": {\"subjects\": []}}\n```"

    # patch both the imported name in nodes and the original in utils
    monkeypatch.setattr("teacherflow.nodes.call_llm", fake_call_llm)
    monkeypatch.setattr("teacherflow.utils.call_llm.call_llm", fake_call_llm)

    # call exec with prep_res tuple
    student_data = {"Full Name": "Test", "Course": "3", "Major": "Physics"}
    node.exec((student_data, False, 1))
