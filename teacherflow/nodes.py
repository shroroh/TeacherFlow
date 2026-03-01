import os
import re
import json
import yaml
from pocketflow import Node, BatchNode
from teacherflow.utils.call_llm import call_llm
from teacherflow.db import Database
import markdown
from IPython.display import display, HTML
import html


def _parse_structured_response(response, context_desc="response"):
    """Try to parse a structured payload from LLM `response`.

    Order of attempts:
    1. Fenced ```json ... ``` block
    2. Fenced ```yaml ... ``` block
    3. First JSON object substring found in the text
    4. Parse entire response as JSON
    5. Parse entire response as YAML

    Returns parsed Python object (usually dict/list) or raises ValueError.
    """
    # 1) fenced JSON
    m = re.search(r"```json(.*?)```", response, re.DOTALL)
    if m:
        s = m.group(1).strip()
        try:
            return json.loads(s)
        except Exception as e:
            raise ValueError(f"Failed to parse fenced JSON for {context_desc}: {e}")

    # 2) fenced YAML
    m = re.search(r"```yaml(.*?)```", response, re.DOTALL)
    if m:
        s = m.group(1).strip()
        try:
            return yaml.safe_load(s)
        except Exception as e:
            raise ValueError(f"Failed to parse fenced YAML for {context_desc}: {e}")

    # 3) first JSON object in text
    m = re.search(r"\{[\s\S]*\}", response)
    if m:
        s = m.group(0)
        try:
            return json.loads(s)
        except Exception:
            pass

    # 4) entire response as JSON
    try:
        return json.loads(response)
    except Exception:
        pass

    # 5) entire response as YAML
    try:
        return yaml.safe_load(response)
    except Exception:
        pass

    raise ValueError(f"No structured JSON/YAML found in LLM {context_desc}")


# Node 1 - AppriseStudentGrades - Results of person
# --------------------------------------------------------
class AssessStudentLevel(Node):
    """
    Node: AssessStudentLevel
    Purpose: Evaluate student's knowledge across subjects
    and generate a structured profile.
    """

    def prep(self, shared):
        student_data = shared["student_data"]  # dict from Database['data']
        use_cache = shared.get("use_cache", True)
        max_subjects = shared.get("max_subjects", 10)
        return student_data, use_cache, max_subjects

    def exec(self, prep_res):
        student_data, use_cache, max_subjects = prep_res
        print(f"Assessing knowledge level for {student_data.get('Full Name', 'Unknown')}...")

        prompt = f"""
You are an experienced school teacher AI. The data you received 
 contains school grades for subjects (highest score is 5), class number,
 and student biography.

Student Data:
{student_data}

For EACH subject (up to {max_subjects}):
1. Assign a knowledge level: Very Low, Average, Above Average, High.
2. Provide reasoning in 1-3 sentences.
3. Identify main strengths and gaps.

Output STRICTLY in JSON format, wrapped inside a fenced code block for easy parsing:

```json
{{
  "student_profile": {{
    "subjects": [
      {{
        "name": "",
        "level": "",
        "reasoning": "",
        "strengths": [""],
        "gaps": [""]
      }}
    ]
  }}
}}
```"""

        response = call_llm(prompt, use_cache=(use_cache and self.cur_retry == 0))

        # --- Extract JSON safely ---
        profile = _parse_structured_response(response, context_desc="student profile")
        if "student_profile" not in profile:
            raise ValueError("Missing 'student_profile' key in LLM output.")
        return profile

    def post(self, shared, prep_res, exec_res):
        shared["student_profile"] = exec_res
        print("Student profile stored in shared['student_profile'].")


# Node 2 - PrioritizeSubjects - Generate learning priority list(of subjects)
# --------------------------------------------------------
class PrioritizeSubjects(Node):
    """
    Node: PrioritizeSubjects
    Purpose: Create a ranked list of subjects for a student
    based on their knowledge level and gaps.
    """

    def prep(self, shared):
        student_profile = shared.get("student_profile")
        if not student_profile:
            raise ValueError("Missing 'student_profile' in shared data")
        use_cache = shared.get("use_cache", True)
        return student_profile, use_cache

    def exec(self, prep_res):
        student_profile, use_cache = prep_res
        print("Prioritizing subjects based on student profile...")

        prompt = f"""
You are an AI educational planner. You received a student's profile
with subjects, knowledge levels, strengths, and gaps:

{student_profile}

Task:
1. Rank the subjects from highest priority (needs most attention) to lowest.
2. Take into account:
   - Knowledge levels: Very Low → High (Very Low = highest priority)
   - Gaps: More gaps = higher priority
   - Strengths: Should not reduce priority if gaps exist
3. Provide reasoning for the order in 1-3 sentences.

Output STRICTLY in JSON format:

```json
{{
  "learning_priority": [
    {{
      "subject": "",
      "priority": 1,
      "reasoning": ""
    }}
  ]
}}
```"""

        response = call_llm(prompt, use_cache=(use_cache and self.cur_retry == 0))

        # --- Extract JSON safely ---
        priority_list = _parse_structured_response(response, context_desc="learning priority")

        if "learning_priority" not in priority_list or not isinstance(priority_list["learning_priority"], list):
            raise ValueError("Missing or invalid 'learning_priority' in LLM output.")

        return priority_list

    def post(self, shared, prep_res, exec_res):
        shared["learning_priority"] = exec_res
        print("Learning priority stored in shared['learning_priority'].")


# Node 3 - KnowledgeToDiscover - Lists a theme and topic to learn
# --------------------------------------------------------
class KnowledgeToDiscover(BatchNode):
    """Generate study topics for prioritized subjects using a batch strategy.

    Each subject listed in learning_priority is handled in its own batch
    iteration. Only subjects with `Average`/`Above Average` levels that also
    have gaps produce recommendations. The aggregated results are trimmed to
    ``max_topics`` (stored temporarily in shared state).
    """

    def prep(self, shared):
        student_profile = shared.get("student_profile")
        learning_priority = shared.get("learning_priority", {}).get("learning_priority", [])
        if not student_profile or not learning_priority:
            raise ValueError("Missing 'student_profile' or 'learning_priority' in shared data")
        use_cache = shared.get("use_cache", True)
        max_topics = shared.get("max_topics", 10)
        # Save on instance for use in exec()
        self._student_profile = student_profile
        self._use_cache = use_cache
        self._max_topics = max_topics
        # Return the iterable (list of subjects)
        return learning_priority

    def exec(self, subject_entry):
        # subject_entry is one item from the learning_priority list
        subj = subject_entry if isinstance(subject_entry, str) else subject_entry.get("subject")
        print(f"Generating knowledge suggestions for '{subj}'...")

        prompt = f"""
You are an AI tutor. The student's profile is shown below:
{self._student_profile}

Subject: {subj}

Task:
- If the student's level for this subject is Average or Above Average and
  gaps are present, suggest a main topic to study along with:
    * a reason/source (`based_from`)
    * 2–3 practical examples
    * 2–5 subtopics with their own reason/source

Return a JSON block in markdown fences similar to:
```json
{{
  "knowledge_to_discover": [
    {{
      "topic": "...",
      "based_from": "...",
      "examples": ["..."],
      "subtopics": [
        {{"name": "...", "based_from": "..."}}
      ]
    }}
  ]
}}
```"""

        response = call_llm(prompt, use_cache=(self._use_cache and self.cur_retry == 0))
        result = _parse_structured_response(response, context_desc=f"knowledge_to_discover for subject {subj}")
        # Sometimes the LLM returns a bare boolean (e.g. `false`) or an unexpected
        # type; that causes batch handling to blow up later with a TypeError.
        # We'll treat non-dict results as "no data" so they get skipped.
        if isinstance(result, bool):
            # log a warning so it's easier to debug later
            print(f"Warning: LLM returned a boolean for subject '{subj}', skipping.")
            return None
        if not result or not isinstance(result, dict):
            # Defensive in case YAML was empty or a list, string, etc.
            print(f"Warning: unexpected LLM output for subject '{subj}': {result!r}, skipping.")
            return None
        # Return the valid dictionary result
        return result

    def post(self, shared, prep_res, exec_res_list):
        # exec_res_list is supposed to be a list of results from each exec() call.
        # Add defensive checks in case something went wrong and we got a bool
        # or other non-iterable through from the batch runner.
        if not isinstance(exec_res_list, list):
            raise TypeError(
                f"BatchNode.post expected a list of results but got {type(exec_res_list)}: {exec_res_list!r}"
            )

        topics = []
        for item in exec_res_list:
            if not item:
                continue
            if isinstance(item, dict) and "knowledge_to_discover" in item:
                topics.extend(item["knowledge_to_discover"])
            elif isinstance(item, dict):
                topics.append(item)
        if self._max_topics is not None:
            topics = topics[:self._max_topics]
        shared["knowledge_to_discover"] = {"knowledge_to_discover": topics}
        print("Knowledge topics and subtopics stored in shared['knowledge_to_discover']." )


# New Node: OralQuestionGenerator - generate a short list of oral questions
# --------------------------------------------------------
class OralQuestionGenerator(Node):
    """Generate a list of short, oral-style questions for the student.

    The number of questions can be provided via `shared['oral_num_questions']`.
    Results are stored in `shared['oral_questions']` as a simple dict:
      {"oral_questions": ["q1", "q2", ...]}
    """

    def prep(self, shared):
        self._no_oral = shared.get("no_oral", False)
        if self._no_oral:
            return None, None, None
        self.student_profile = shared.get("student_profile")
        self.learning_priority = shared.get("learning_priority", {}).get("learning_priority", [])
        self.num_questions = int(shared.get("oral_num_questions", 5))
        self.use_cache = shared.get("use_cache", True)
        if not self.student_profile:
            raise ValueError("Missing 'student_profile' in shared data for OralQuestionGenerator")
        return self.student_profile, self.learning_priority, self.num_questions

    def exec(self, prep_res):
        if self._no_oral:
            return {"oral_questions": []}
        student_profile, learning_priority, num_questions = prep_res
        print(f"Generating {num_questions} oral-style questions based on student's profile...")

        prompt = f"""
You are an educational assistant. Given the student's profile and prioritized subjects, create {num_questions} short oral questions in Russian that a teacher might ask a student standing in front of them.

Student profile:
{student_profile}

Learning priority:
{learning_priority}

Requirements:
- Produce exactly {num_questions} distinct, concise questions (one sentence each).
- Questions should be varied: recall, explanation, short problem, opinion/reflection.
- Output STRICTLY in JSON fenced block as:
```json
{{
  "oral_questions": [
    "...",
    "..."
  ]
}}
```
"""

        response = call_llm(prompt, use_cache=(self.use_cache and getattr(self, "cur_retry", 0) == 0))
        result = _parse_structured_response(response, context_desc="oral questions")
        if not result or "oral_questions" not in result:
            raise ValueError("LLM did not return 'oral_questions' list")
        return result

    def post(self, shared, prep_res, exec_res):
        shared["oral_questions"] = exec_res
        print("Oral questions stored in shared['oral_questions'].")


# New Node: SimulateOralAnswers - batch-simulate student's answers
# --------------------------------------------------------
class SimulateOralAnswers(BatchNode):
    """For each question, generate a short student-style answer using profile/context.

    Stores results in `shared['oral_qa']` as:
      {"oral_qa": [{"question": q, "answer": a, "notes": ...}, ...]}
    """

    def prep(self, shared):
        self._no_oral = shared.get("no_oral", False)
        if self._no_oral:
            return []
        oral_questions = shared.get("oral_questions", {}).get("oral_questions")
        if not oral_questions:
            oral_questions = shared.get("oral_questions")
        if not oral_questions:
            raise ValueError("Missing 'oral_questions' in shared data for SimulateOralAnswers")
        self.student_data = shared.get("student_data")
        self.student_profile = shared.get("student_profile")
        self._use_cache = shared.get("use_cache", True)
        return oral_questions

    def exec(self, question):
        if self._no_oral:
            return None
        print(f"Generating student answer for question: {question}")
        prompt = f"""
You are simulating how the student would answer a short oral question in front of a teacher.

Student data:
{self.student_data}

Student profile:
{self.student_profile}

Question: {question}

Requirements:
- Answer in 1-3 short sentences, natural spoken style in Russian.
- Be concise and honest about potential gaps (if the student likely doesn't know, provide a short attempted answer and a short note).
- Output STRICTLY in JSON fenced block:
```json
{{
  "qa": {{
    "question": "...",
    "answer": "...",
    "note": "optional short note"
  }}
}}
```"""

        response = call_llm(prompt, use_cache=(self._use_cache and getattr(self, "cur_retry", 0) == 0))
        try:
            result = _parse_structured_response(response, context_desc=f"qa for question {question}")
        except ValueError:
            # Fallback: return the raw answer text as a simple dict
            return {"qa": {"question": question, "answer": response.strip()}}
        # Normalize to expected structure
        if isinstance(result, dict) and "qa" in result:
            qa = result["qa"]
            # Ensure question field present
            if "question" not in qa:
                qa["question"] = question
            return {"qa": qa}
        # Otherwise, return fallback
        return {"qa": {"question": question, "answer": str(result)}}

    def post(self, shared, prep_res, exec_res_list):
        if not isinstance(exec_res_list, list):
            raise TypeError("Expected list of results from batch execution for SimulateOralAnswers")
        qa_list = []
        for item in exec_res_list:
            if not item:
                continue
            if isinstance(item, dict) and "qa" in item:
                qa_list.append(item["qa"])
            elif isinstance(item, dict):
                qa_list.append(item)
            else:
                qa_list.append({"question": None, "answer": str(item)})
        shared["oral_qa"] = {"oral_qa": qa_list}
        print("Oral Q&A stored in shared['oral_qa'].")


class OralAssessment(Node):
    """Analyze the simulated oral answers to produce a short assessment

    Outputs `shared['oral_assessment']` as a dict, e.g.:
      {"oral_assessment": {"summary": "...", "adjustments": [...]}}
    """

    def prep(self, shared):
        self._no_oral = shared.get("no_oral", False)
        if self._no_oral:
            return None, None, None
        self.oral_qa = shared.get("oral_qa")
        self.student_profile = shared.get("student_profile")
        self.student_data = shared.get("student_data")
        self.use_cache = shared.get("use_cache", True)
        if not self.oral_qa:
            raise ValueError("Missing 'oral_qa' in shared data for OralAssessment")
        return self.oral_qa, self.student_profile, self.student_data

    def exec(self, prep_res):
        if self._no_oral:
            return {"oral_assessment": {"summary": "Oral disabled", "adjustments": []}}
        oral_qa, student_profile, student_data = prep_res
        # Build prompt asking LLM to analyze spoken answers and suggest any changes
        prompt = f"""
You are an experienced teacher. You received a set of short oral Q&A exchanges between a teacher and a student, plus the student's profile.

Student data:
{student_data}

Student profile:
{student_profile}

Oral Q&A (list of question/answer pairs):
{oral_qa}

Task:
- Provide a concise summary (2-4 sentences) of the student's oral performance: clarity, correctness, confidence, major misconceptions.
- Suggest up to 3 concrete adjustments to the student's profile/priority that should be made based on the oral answers (format: subject, suggested change, short reason).

Return STRICTLY in a YAML fenced block like:
```yaml
oral_assessment:
  summary: "..."
  adjustments:
    - subject: "..."
      change: "increase|decrease|note"
      reason: "..."
```
"""

        response = call_llm(prompt, use_cache=(self.use_cache and getattr(self, "cur_retry", 0) == 0))
        result = _parse_structured_response(response, context_desc="oral assessment")
        if not result or "oral_assessment" not in result:
            raise ValueError("LLM did not return 'oral_assessment'")
        return result

    def post(self, shared, prep_res, exec_res):
        shared["oral_assessment"] = exec_res
        print("Oral assessment stored in shared['oral_assessment'].")

        # Apply adjustments to student_profile and learning_priority
        try:
            adjustments = exec_res.get("oral_assessment", {}).get("adjustments", [])
            if adjustments:
                # Update student_profile: add oral_adjustments notes per subject
                sp = shared.get("student_profile")
                if sp and isinstance(sp, dict):
                    # student_profile structure expected: {'student_profile': {'subjects': [...]}}
                    subjects = None
                    if "student_profile" in sp and isinstance(sp["student_profile"], dict):
                        subjects = sp["student_profile"].get("subjects")
                    elif isinstance(sp.get("subjects"), list):
                        subjects = sp.get("subjects")

                    if subjects and isinstance(subjects, list):
                        for adj in adjustments:
                            subj = adj.get("subject")
                            change = adj.get("change")
                            reason = adj.get("reason")
                            if not subj:
                                continue
                            for s in subjects:
                                name = s.get("name")
                                if name and name.strip().lower() == subj.strip().lower():
                                    notes = s.setdefault("oral_adjustments", [])
                                    notes.append({"change": change, "reason": reason})

                # Update learning_priority: adjust numeric priorities
                lp = shared.get("learning_priority", {}).get("learning_priority", [])
                if isinstance(lp, list) and lp:
                    # Build lookup
                    subj_map = {entry.get("subject"): entry for entry in lp if isinstance(entry, dict)}
                    # Compute current max priority
                    current_priorities = [int(entry.get("priority", 9999)) for entry in lp if isinstance(entry, dict)]
                    max_priority = max(current_priorities) if current_priorities else len(lp)
                    for adj in adjustments:
                        subj = adj.get("subject")
                        change = (adj.get("change") or "").lower()
                        if not subj:
                            continue
                        # find matching entry (case-insensitive)
                        found = None
                        for entry in lp:
                            if isinstance(entry, dict) and entry.get("subject") and entry.get("subject").strip().lower() == subj.strip().lower():
                                found = entry
                                break
                        if found:
                            try:
                                p = int(found.get("priority", max_priority))
                            except Exception:
                                p = max_priority
                            if change == "increase":
                                p = max(1, p - 1)
                            elif change == "decrease":
                                p = p + 1
                            found["priority"] = p
                        else:
                            # add new entry at lower priority (end)
                            lp.append({"subject": subj, "priority": max_priority + 1, "reasoning": f"Added from oral assessment: {adj.get('reason')}"})
                            max_priority += 1

                    # normalize priorities (1..n) based on current numeric sort
                    lp_sorted = sorted([e for e in lp if isinstance(e, dict)], key=lambda x: int(x.get("priority", 9999)))
                    for idx, entry in enumerate(lp_sorted, start=1):
                        entry["priority"] = idx
                    shared["learning_priority"] = {"learning_priority": lp_sorted}
        except Exception:
            # Do not let adjustment errors break the flow; log simple message
            print("Warning: failed to apply oral_assessment adjustments to shared profile/priorities.")


class FinalTeacherConclusion(Node):
    """
    Generates a complete teacher conclusion and saves as HTML using Markdown rendering.
    """

    def prep(self, shared):
        return (
            shared["student_data"],
            shared["student_profile"],
            shared["learning_priority"],
            shared.get("knowledge_to_discover"),
            shared.get("oral_qa"),
            shared.get("output_dir", "output"),
            shared.get("use_cache", True),
            shared.get("oral_assessment"),
            shared.get("no_oral", False),
        )

    def exec(self, prep_res):
        student_data, profile, priority, plan, oral_qa, output_dir, use_cache, oral_assessment, no_oral = prep_res

        name = student_data.get("Full Name", "ученик")
        # if course is set, use course/major instead of school class
        if student_data.get("Course"):
            course = student_data.get("Course")
            major = student_data.get("Major")
            grade = f"курс {course}"
            if major:
                grade += f", направление {major}"
        else:
            grade = student_data.get("Class", "N/A")

        # ---- Prompt ----
        prompt = f"""
Вы — заботливый и опытный школьный учитель.

Имя ученика: {name}
Класс: {grade}

Профиль ученика:
{profile}

Приоритеты:
{priority}

Учебный план:
{plan}

Устная сессия (вопросы и ответы):
{oral_qa if oral_qa else 'Нет устной сессии.'}

Составьте итоговое заключение на русском языке в Markdown,
с заголовками, списками, таблицами и отступами.
"""

        # Optionally include oral assessment
        if not no_oral and oral_assessment and isinstance(oral_assessment, dict):
            try:
                oa_summary = oral_assessment.get("oral_assessment", {}).get("summary")
                if oa_summary:
                    prompt += f"\n\nУстная оценка (краткое резюме):\n{oa_summary}\n\nУчтите это при составлении заключения."
            except Exception:
                pass

        # ---- Вызов LLM ----
        text = call_llm(prompt, use_cache=(use_cache and getattr(self, "cur_retry", 0) == 0))

        os.makedirs(output_dir, exist_ok=True)
        safe_name = re.sub(r"[^\w]+", "_", name.lower())
        html_file = os.path.join(output_dir, f"{safe_name}_teacher_conclusion.html")

        # ---- Markdown -> HTML ----
        html_body = markdown.markdown(text, extensions=['tables', 'fenced_code'])
        dialog_html = ""
        try:
            dialog_md = ""
            dialog_text = ""
            if no_oral:
                entries = []
            elif oral_qa and isinstance(oral_qa, dict):
                entries = oral_qa.get("oral_qa", [])
            else:
                entries = []
            for item in entries:
                q = item.get("question") if isinstance(item, dict) else None
                a = item.get("answer") if isinstance(item, dict) else None
                note = item.get("note") if isinstance(item, dict) else None
                if q:
                    dialog_md += f"**Учитель:** {q}\n\n"
                    dialog_text += f"Учитель: {q}\n"
                if a:
                    dialog_md += f"**Ученик:** {a}\n\n"
                    dialog_text += f"Ученик: {a}\n"
                if note:
                    dialog_md += f"_Примечание:_ {note}\n\n"
                    dialog_text += f"Примечание: {note}\n"
                dialog_md += "---\n\n"
                dialog_text += "\n"

            if dialog_md:
                os.makedirs(output_dir, exist_ok=True)
                dialog_txt_file = os.path.join(output_dir, f"{safe_name}_oral_dialog.txt")
                with open(dialog_txt_file, "w", encoding="utf-8") as dtf:
                    dtf.write(dialog_text)
                # also save Markdown source
                dialog_md_file = os.path.join(output_dir, f"{safe_name}_oral_dialog.md")
                with open(dialog_md_file, "w", encoding="utf-8") as dmf:
                    dmf.write(dialog_md)

                # Render Markdown to HTML and include inside collapsible block
                dialog_rendered = markdown.markdown(dialog_md, extensions=['tables', 'fenced_code'])
                dialog_html = f"""
<details>
  <summary>Устная сессия — показать/скрыть</summary>
  <div style="margin:10px 0;padding:10px;background:#f8f8f8;border-radius:6px;">{dialog_rendered}</div>
</details>
"""
        except Exception:
            dialog_html = ""

        full_html = f"""
<html>
<head>
<meta charset="utf-8">
<title>Заключение учителя: {name}</title>
<style>
body {{ font-family: DejaVu Sans, Arial, sans-serif; line-height: 1.5; padding: 20px; }}
h1,h2,h3,h4 {{ margin-top: 20px; }}
table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
table, th, td {{ border: 1px solid #333; padding: 6px; }}
code {{ background-color: #f0f0f0; padding: 2px 4px; border-radius: 4px; }}
        .oral-dialog {{ margin: 16px 0; padding: 12px; background: linear-gradient(180deg,#fff7e6,#fff); border-left:4px solid #ffb84d; border-radius:6px; }}
        .oral-dialog h3 {{ margin-top:0; }}
pre {{ background-color: #f9f9f9; padding: 10px; border-radius: 4px; overflow-x: auto; }}
ul, ol {{ padding-left: 20px; }}
</style>
</head>
<body>
<h1>Итоговое заключение учителя для {name}</h1>
{html_body}
{dialog_html}
</body>
</html>
"""

        with open(html_file, "w", encoding="utf-8") as f:
            f.write(full_html)

        return {"text": text, "html_file": html_file}

    def post(self, shared, prep_res, exec_res):
        shared["teacher_conclusion"] = exec_res["text"]
        shared["teacher_conclusion_html"] = exec_res["html_file"]
        print(f"📄 Teacher conclusion saved as HTML: {exec_res['html_file']}")
