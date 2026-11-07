# Process model: a student's lifecycle in a course

The process is a state machine over (a) the course state and (b) the student's action history (event log).
A student does not move through a linear flow but through an **event loop**: the teacher publishes,
the student reacts. For that reason "where the student is" is not stored as a single variable;
it is **derived** from the event log plus the current state of the course.

## Activities (actions)

| Activity             | Actor   | Changes state | Precondition                                              |
|----------------------|---------|---------------|-----------------------------------------------------------|
| `enroll_course`      | student | yes           | not enrolled in the course                                |
| `read_announcement`  | student | no            | enrolled; announcement exists                             |
| `download_material`  | student | no            | enrolled; material is published                           |
| `submit_assignment`  | student | yes           | enrolled; deadline has not passed; not already submitted  |
| `view_grade`         | student | no            | enrolled; a grade for the assignment exists               |
| `post_announcement`  | teacher | yes           | teacher of the course                                     |
| `post_material`      | teacher | yes           | teacher of the course                                     |
| `post_grade`         | teacher | yes           | teacher of the course; student has submitted the assignment |

"Changes state = yes" means the agent asks for the user's confirmation before executing.
Read-only actions (navigation, reading, downloading) are executed by the agent without confirmation, but visibly.

## Student state in a course (derived)

- `enrolled`: yes/no (`enroll_course` event)
- `unread_announcements`: announcements that are posted but have no `read_announcement` event
- `pending_materials`: published materials with no `download_material` event (ordered by lesson number)
- `open_assignments`: assignments with a future deadline and no submission
- `unviewed_grades`: grades that are posted but have no `view_grade` event

## Recommendation rule (reference / "baseline" implementation)

Priority order, the first rule that applies wins:

1. not enrolled → `enroll_course`
2. unread announcement → `read_announcement` (oldest first)
3. material not downloaded → `download_material` (lowest lesson number)
4. open assignment → `submit_assignment` (nearest deadline)
5. unviewed grade → `view_grade`
6. nothing to do → no recommendation (`idle`)

This rule is the **reference for testing and for variant 2** in the evaluation. The labels in the synthetic
dataset are not derived from it alone (traps: material posted mid-way, student skips a lesson,
deadline passed), so that the evaluation does not simply measure a copy of the rule.

## Example from the professor's feedback

The student has downloaded the material for lesson 3, then the teacher publishes lesson 4 → state:
`pending_materials = [lesson 4]` → recommendation `download_material(lesson 4)`; the front end opens
the page of material 4 and automatically starts the download.
