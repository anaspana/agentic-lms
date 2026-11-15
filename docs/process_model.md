# Process model: a student's lifecycle in a course

The process is a state machine over (a) the course state and (b) the student's action history (event log).
A student does not move through a linear flow but through an **event loop**: the teacher publishes,
the student reacts. For that reason "where the student is" is not stored as a single variable;
it is **derived** from the event log plus the current state of the course.

## Where the model lives

The authoritative model is [`backend/process/course_lifecycle.yaml`](../backend/process/course_lifecycle.yaml).
The tables below are a readable summary of it. If they ever disagree, the YAML file wins.

The model is split into two layers:

- **The YAML file** says *what* the process is: activities, who performs them, whether they change state,
  which conditions must hold and in what order, and the priority of recommendations.
- **The condition library** (`CONDITIONS` in `backend/app/process_model.py`) says *how* each condition is
  checked against the database. Each condition is a single yes/no question, such as "is the student enrolled".

A new activity that reuses existing conditions only needs a YAML entry and a form. A completely new kind of
check needs one new function in the library. The backend validates the model at startup and refuses to run
if it refers to a condition, object or state that does not exist.

The model is also served as JSON at `GET /api/process`, so the agent can read the same description the
backend enforces.

## Activities (actions)

| Activity             | Actor   | Changes state | Preconditions (in order)                                         |
|----------------------|---------|---------------|------------------------------------------------------------------|
| `enroll_course`      | student | yes           | course_exists, not_enrolled                                      |
| `read_announcement`  | student | no            | object_exists, enrolled                                          |
| `download_material`  | student | no            | object_exists, enrolled                                          |
| `submit_assignment`  | student | yes           | object_exists, enrolled, deadline_open, not_submitted            |
| `view_grade`         | student | no            | object_exists, enrolled, grade_exists                            |
| `post_announcement`  | teacher | yes           | course_exists, is_course_teacher                                 |
| `post_material`      | teacher | yes           | course_exists, is_course_teacher                                 |
| `post_grade`         | teacher | yes           | course_exists, is_course_teacher, assignment_in_course, student_submitted |

"Changes state = yes" means the agent asks for the user's confirmation before executing.
Read-only actions (navigation, reading, downloading) are executed by the agent without confirmation, but visibly.

## Student state in a course (derived)

- `enrolled`: the student has enrolled in the course
- `unread_announcements`: announcements that are posted but have no `read_announcement` event
- `pending_materials`: published materials with no `download_material` event (ordered by lesson number)
- `open_assignments`: assignments with a future deadline and no submission
- `unviewed_grades`: grades that are posted but have no `view_grade` event

## Recommendation rule (reference / "baseline" implementation)

Priority order from the `recommendation` section of the model, the first rule that applies wins:

1. not enrolled → `enroll_course`
2. unread announcement → `read_announcement` (oldest first)
3. material not downloaded → `download_material` (lowest lesson number)
4. open assignment → `submit_assignment` (nearest deadline)
5. unviewed grade → `view_grade`
6. nothing to do → no recommendation (`idle`)

Changing the order in the YAML file changes the recommendation without touching the code.

This rule is the **reference for testing and for variant 0** in the evaluation. The labels in the synthetic
dataset are not derived from it alone (for example, an announcement that asks students to download a
corrected lesson again, or a deadline that was moved), so that the evaluation does not simply measure a
copy of the rule.

## Example from the professor's feedback

The student has downloaded the material for lesson 3, then the teacher publishes lesson 4 → state:
`pending_materials = [lesson 4]` → recommendation `download_material(lesson 4)`; the front end opens
the page of material 4 and automatically starts the download.
