import { useState, type FormEvent } from "react";
import { api } from "../api";
import { percent } from "../format";
import type { GeneratedQuiz } from "../types";

interface QuizGeneratorProps {
  studentId: number;
  subject: string | null;
  onGraded: () => void | Promise<void>;
}

interface GradedSummary {
  correct: number;
  total: number;
  mastery: Record<number, number>;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong.";
}

export function QuizGenerator({ studentId, subject, onGraded }: QuizGeneratorProps) {
  const [quiz, setQuiz] = useState<GeneratedQuiz | null>(null);
  const [count, setCount] = useState(5);
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [summary, setSummary] = useState<GradedSummary | null>(null);
  const [generating, setGenerating] = useState(false);
  const [grading, setGrading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setQuiz(null);
    setAnswers({});
    setSummary(null);
    setGenerating(true);
    try {
      const generated = await api.generateQuiz(studentId, count, subject);
      setQuiz(generated);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setGenerating(false);
    }
  }

  function choose(questionIndex: number, optionIndex: number) {
    setAnswers((previous) => ({ ...previous, [questionIndex]: optionIndex }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!quiz) return;
    if (Object.keys(answers).length < quiz.questions.length) {
      setError("Answer every question before grading.");
      return;
    }

    setError(null);
    setGrading(true);
    try {
      const byTopic = new Map<number, { correct: number; total: number }>();
      let correct = 0;
      quiz.questions.forEach((question, index) => {
        const entry = byTopic.get(question.topic_id) ?? { correct: 0, total: 0 };
        entry.total += 1;
        if (answers[index] === question.correct_index) {
          entry.correct += 1;
          correct += 1;
        }
        byTopic.set(question.topic_id, entry);
      });

      // Graded generated quizzes follow the same path as a manually logged
      // quiz, so mastery and recommendations update from real performance.
      const entries = [...byTopic.entries()];
      const results = await Promise.all(
        entries.map(([topicId, score]) =>
          api.submitQuizResult({
            student_id: studentId,
            topic_id: topicId,
            correct_answers: score.correct,
            total_questions: score.total,
          }),
        ),
      );

      const mastery: Record<number, number> = {};
      entries.forEach(([topicId], index) => {
        mastery[topicId] = results[index].mastery;
      });

      setSummary({ correct, total: quiz.questions.length, mastery });
      await onGraded();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setGrading(false);
    }
  }

  const answered = quiz ? Object.keys(answers).length : 0;

  return (
    <div className="quiz">
      <form className="quiz-controls" onSubmit={handleGenerate}>
        <div>
          <label htmlFor="quiz-count">Questions</label>
          <select
            id="quiz-count"
            value={count}
            onChange={(event) => setCount(Number(event.target.value))}
            disabled={generating}
          >
            <option value={3}>3 questions</option>
            <option value={5}>5 questions</option>
            <option value={8}>8 questions</option>
          </select>
        </div>
        <button type="submit" className="button primary" disabled={generating}>
          {generating ? "Generating…" : quiz ? "Generate another quiz" : "Generate quiz"}
        </button>
      </form>

      <div aria-live="polite">
        {error && (
          <p className="alert error" role="alert">
            {error}
          </p>
        )}
      </div>

      {!quiz && !generating && !error && (
        <p className="empty-state">
          Generate a quiz from your weakest topics, with one question on a relative
          strength. Questions come from the language model; grading updates mastery.
        </p>
      )}

      {quiz && (
        <>
          <ul className="quiz-focus" aria-label="Quiz focus">
            {quiz.focus.map((item) => (
              <li key={item.topic_id} className={`focus-chip ${item.role}`}>
                <span className="focus-role">
                  {item.role === "strength" ? "Strength" : "Weak"}
                </span>
                <span className="focus-name">{item.topic_name}</span>
                <span className="focus-mastery">{percent(item.mastery)}</span>
              </li>
            ))}
          </ul>

          <form onSubmit={handleSubmit}>
            <ol className="quiz-list">
              {quiz.questions.map((question, index) => {
                const selected = answers[index];
                const graded = summary !== null;
                return (
                  <li key={`${question.topic_id}-${index}`} className="quiz-question">
                    <div className="quiz-question-head">
                      <span className="topic-chip">{question.topic_name}</span>
                      <span className="quiz-position">
                        Question {index + 1} of {quiz.questions.length}
                      </span>
                    </div>
                    <p className="quiz-prompt">{question.question}</p>
                    <div
                      className="quiz-options"
                      role="radiogroup"
                      aria-label={`Question ${index + 1}`}
                    >
                      {question.options.map((option, optionIndex) => {
                        const chosen = selected === optionIndex;
                        const isAnswer = question.correct_index === optionIndex;
                        let className = "quiz-option";
                        if (graded && isAnswer) {
                          className += " correct";
                        } else if (graded && chosen) {
                          className += " incorrect";
                        }
                        return (
                          <label key={optionIndex} className={className}>
                            <input
                              type="radio"
                              name={`quiz-question-${index}`}
                              value={optionIndex}
                              checked={chosen}
                              disabled={graded || grading}
                              onChange={() => choose(index, optionIndex)}
                            />
                            <span>{option}</span>
                          </label>
                        );
                      })}
                    </div>
                    {graded && (
                      <p className="quiz-explanation">
                        <strong>
                          {selected === question.correct_index ? "Correct. " : "Not quite. "}
                        </strong>
                        {question.explanation}
                      </p>
                    )}
                  </li>
                );
              })}
            </ol>

            {summary === null ? (
              <button type="submit" className="button primary" disabled={grading}>
                {grading
                  ? "Grading…"
                  : `Grade quiz (${answered}/${quiz.questions.length} answered)`}
              </button>
            ) : (
              <div className="quiz-summary" role="status">
                <p>
                  You scored {summary.correct} of {summary.total}. Mastery updated:
                </p>
                <ul>
                  {Object.entries(summary.mastery).map(([topicId, value]) => {
                    const topic = quiz.focus.find(
                      (item) => item.topic_id === Number(topicId),
                    );
                    return (
                      <li key={topicId}>
                        <span>{topic?.topic_name ?? `Topic ${topicId}`}</span>
                        <strong>{percent(value, 1)}</strong>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
          </form>
        </>
      )}
    </div>
  );
}
