import os
import re
import yaml
from pocketflow import Node, BatchNode
from teacherflow.utils.call_llm import call_llm
from teacherflow.db import Database
import markdown
from IPython.display import display, HTML


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

Output STRICTLY in YAML format:

```yaml
student_profile:
  subjects:
    - name: ""
      level: ""
      reasoning: |
        ...
      strengths:
        - ""
      gaps:
        - ""
```"""

        response = call_llm(prompt, use_cache=(use_cache and self.cur_retry == 0))

        # --- Extract YAML safely ---
        match = re.search(r"```yaml(.*?)```", response, re.DOTALL)
        if not match:
            raise ValueError("No YAML block found in LLM output")
        yaml_str = match.group(1).strip()

        profile = yaml.safe_load(yaml_str)
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

Output STRICTLY in YAML format:

```yaml
learning_priority:
  - subject: ""
    priority: 1
    reasoning: |
      ...
```"""

        response = call_llm(prompt, use_cache=(use_cache and self.cur_retry == 0))

        # --- Extract YAML safely ---
        match = re.search(r"```yaml(.*?)```", response, re.DOTALL)
        if not match:
            raise ValueError("No YAML block found in LLM output")
        yaml_str = match.group(1).strip()

        priority_list = yaml.safe_load(yaml_str)

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

Return a YAML block in markdown fences similar to:
```yaml
knowledge_to_discover:
  - topic: "..."
    based_from: "..."
    examples:
      - "..."
    subtopics:
      - name: "..."
        based_from: "..."
```"""

        response = call_llm(prompt, use_cache=(self._use_cache and self.cur_retry == 0))
        match = re.search(r"```yaml(.*?)```", response, re.DOTALL)
        if not match:
            raise ValueError(f"No YAML block found in LLM output for subject {subj}")
        yaml_str = match.group(1).strip()
        result = yaml.safe_load(yaml_str)
        # Return None if no valid result, so we can skip it in post()
        return result if result else None

    def post(self, shared, prep_res, exec_res_list):
        # exec_res_list is the list of results from each exec() call
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


class FinalTeacherConclusion(Node):
    """
    Generates a complete teacher conclusion and saves as HTML using Markdown rendering.
    """

    def prep(self, shared):
        return (
            shared["student_data"],
            shared["student_profile"],
            shared["learning_priority"],
            shared["knowledge_to_discover"],
            shared.get("output_dir", "output"),
            shared.get("use_cache", True),
        )

    def exec(self, prep_res):
        student_data, profile, priority, plan, output_dir, use_cache = prep_res

        name = student_data.get("Full Name", "ученик")
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

Составьте итоговое заключение на русском языке в Markdown,
с заголовками, списками, таблицами и отступами.
"""

        # ---- Вызов LLM ----
        text = call_llm(prompt, use_cache=(use_cache and getattr(self, "cur_retry", 0) == 0))

        os.makedirs(output_dir, exist_ok=True)
        safe_name = re.sub(r"[^\w]+", "_", name.lower())
        html_file = os.path.join(output_dir, f"{safe_name}_teacher_conclusion.html")

        # ---- Markdown -> HTML ----
        html_body = markdown.markdown(text, extensions=['tables', 'fenced_code'])
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
pre {{ background-color: #f9f9f9; padding: 10px; border-radius: 4px; overflow-x: auto; }}
ul, ol {{ padding-left: 20px; }}
</style>
</head>
<body>
<h1>Итоговое заключение учителя для {name}</h1>
<h2>Класс: {grade}</h2>
{html_body}
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
