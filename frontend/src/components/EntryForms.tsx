import { useState, type FormEvent } from "react";
import { api } from "../api";
import { percent } from "../format";
import type { Topic } from "../types";

interface EntryFormsProps {
  studentId: number;
  topics: Topic[];
  onSaved: () => void | Promise<void>;
}

export function EntryForms({ studentId, topics, onSaved }: EntryFormsProps) {
  return (
    <div className="forms-grid">
      <StudyForm studentId={studentId} topics={topics} onSaved={onSaved} />
      <QuizForm studentId={studentId} topics={topics} onSaved={onSaved} />
    </div>
  );
}

interface FormProps {
  studentId: number;
  topics: Topic[];
  onSaved: () => void | Promise<void>;
}

function StudyForm({ studentId, topics, onSaved }: FormProps) {
  const [topicId, setTopicId] = useState("");
  const [duration, setDuration] = useState("25");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setError(null);

    const minutes = Number(duration);
    if (!topicId) {
      setError("Choose a topic.");
      return;
    }
    if (!Number.isFinite(minutes) || minutes < 1 || minutes > 1440) {
      setError("Duration must be between 1 and 1440 minutes.");
      return;
    }

    setSaving(true);
    try {
      const topicName = topics.find((topic) => topic.id === Number(topicId))?.name ?? "topic";
      await api.addStudyRecord({
        student_id: studentId,
        topic_id: Number(topicId),
        duration_minutes: Math.round(minutes),
        notes: notes.trim() ? notes.trim() : undefined,
      });
      setNotes("");
      setDuration("25");
      setMessage(`Logged ${Math.round(minutes)} minutes on ${topicName}.`);
      await onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the study session.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="card form-card" onSubmit={handleSubmit} aria-labelledby="study-form-title">
      <h3 id="study-form-title">Log a study session</h3>
      <p className="hint">Record revision time to inform revision urgency.</p>

      <label htmlFor="study-topic">Topic</label>
      <select
        id="study-topic"
        value={topicId}
        onChange={(event) => setTopicId(event.target.value)}
        required
        disabled={topics.length === 0}
      >
        <option value="">Select a topic…</option>
        {topics.map((topic) => (
          <option key={topic.id} value={topic.id}>
            {topic.name}
          </option>
        ))}
      </select>

      <label htmlFor="study-duration">Duration (minutes)</label>
      <input
        id="study-duration"
        type="number"
        min={1}
        max={1440}
        value={duration}
        onChange={(event) => setDuration(event.target.value)}
        required
      />

      <label htmlFor="study-notes">Notes (optional)</label>
      <textarea
        id="study-notes"
        rows={2}
        maxLength={1000}
        value={notes}
        onChange={(event) => setNotes(event.target.value)}
        placeholder="What did you revise?"
      />

      <button type="submit" className="button" disabled={saving || topics.length === 0}>
        {saving ? "Saving…" : "Save session"}
      </button>

      <div aria-live="polite">
        {message && <p className="alert success" role="status">{message}</p>}
        {error && <p className="alert error" role="alert">{error}</p>}
      </div>
    </form>
  );
}

function QuizForm({ studentId, topics, onSaved }: FormProps) {
  const [topicId, setTopicId] = useState("");
  const [correct, setCorrect] = useState("");
  const [total, setTotal] = useState("10");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const correctNumber = Number(correct);
  const totalNumber = Number(total);
  const preview =
    correct !== "" && Number.isFinite(correctNumber) && totalNumber > 0 && correctNumber <= totalNumber
      ? correctNumber / totalNumber
      : null;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setError(null);

    if (!topicId) {
      setError("Choose a topic.");
      return;
    }
    if (!Number.isInteger(correctNumber) || correctNumber < 0) {
      setError("Correct answers must be a whole number of 0 or more.");
      return;
    }
    if (!Number.isInteger(totalNumber) || totalNumber < 1 || totalNumber > 200) {
      setError("Total questions must be a whole number between 1 and 200.");
      return;
    }
    if (correctNumber > totalNumber) {
      setError("Correct answers cannot exceed total questions.");
      return;
    }

    setSaving(true);
    try {
      const topicName = topics.find((topic) => topic.id === Number(topicId))?.name ?? "topic";
      const result = await api.submitQuizResult({
        student_id: studentId,
        topic_id: Number(topicId),
        correct_answers: correctNumber,
        total_questions: totalNumber,
      });
      setCorrect("");
      setTotal("10");
      setMessage(`Quiz saved. ${topicName} mastery is now ${percent(result.mastery, 1)}.`);
      await onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the quiz result.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="card form-card" onSubmit={handleSubmit} aria-labelledby="quiz-form-title">
      <h3 id="quiz-form-title">Log a quiz taken elsewhere</h3>
      <p className="hint">
        For a paper test or an external quiz. AI practice quizzes record their own
        results automatically when graded.
      </p>

      <label htmlFor="quiz-topic">Topic</label>
      <select
        id="quiz-topic"
        value={topicId}
        onChange={(event) => setTopicId(event.target.value)}
        required
        disabled={topics.length === 0}
      >
        <option value="">Select a topic…</option>
        {topics.map((topic) => (
          <option key={topic.id} value={topic.id}>
            {topic.name}
          </option>
        ))}
      </select>

      <div className="field-row">
        <div>
          <label htmlFor="quiz-correct">Correct answers</label>
          <input
            id="quiz-correct"
            type="number"
            min={0}
            max={200}
            value={correct}
            onChange={(event) => setCorrect(event.target.value)}
            required
          />
        </div>
        <div>
          <label htmlFor="quiz-total">Total questions</label>
          <input
            id="quiz-total"
            type="number"
            min={1}
            max={200}
            value={total}
            onChange={(event) => setTotal(event.target.value)}
            required
          />
        </div>
      </div>

      <p className="score-preview">
        Score preview: <strong>{preview === null ? "—" : percent(preview, 0)}</strong>
      </p>

      <button type="submit" className="button" disabled={saving || topics.length === 0}>
        {saving ? "Saving…" : "Save external quiz"}
      </button>

      <div aria-live="polite">
        {message && <p className="alert success" role="status">{message}</p>}
        {error && <p className="alert error" role="alert">{error}</p>}
      </div>
    </form>
  );
}
