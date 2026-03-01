import pytest

from teacherflow.nodes import KnowledgeToDiscover


def test_knowledge_to_discover_skips_boolean(monkeypatch):
    """If the LLM returns a bare boolean in YAML, exec() should return None.

    The old implementation would return False, leading the batch runner to
    treat the result list as containing a bool which later crashed during
    iteration. This test ensures the new defensive logic discards booleans.
    """
    node = KnowledgeToDiscover()
    # set attributes used by exec()
    node._student_profile = {"Full Name": "Test"}
    node._use_cache = False
    node.cur_retry = 0

    # monkeypatch the call_llm helper to simulate a boolean YAML response
    def fake_call_llm(prompt, use_cache=True):
        return "```yaml\nfalse\n```"

    monkeypatch.setattr("teacherflow.nodes.call_llm", fake_call_llm)

    result = node.exec("Math")
    assert result is None, "Expected exec() to return None when LLM output is boolean"


def test_post_raises_on_non_list():
    """post() should explicitly reject a non-list exec_res_list."""
    node = KnowledgeToDiscover()
    with pytest.raises(TypeError):
        node.post({}, None, True)  # pass a bool instead of a list
