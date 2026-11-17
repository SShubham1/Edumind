import { useEffect, useMemo, useState, type FormEvent } from "react";
import { api } from "../api";
import { formatDate } from "../format";
import type { Flashcard, Topic } from "../types";

const SOURCE_LABELS: Record<string, string> = {
  llm: "AI generated",
  fallback: "Offline fallback",
  manual: "Manual",
  seed: "Sample",
};

interface FlashcardsProps {
  studentId: number;
  topics: Topic[];
}

export function Flashcards({ studentId, topics }: FlashcardsProps) {
  const [cards, setCards] = useState<Flashcard[]>([]);
  const [topicId, setTopicId] = useState("");
  const [count, setCount] = useState(5);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [revealed, setRevealed] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const topicNames = useMemo(
    () => new Map(topics.map((topic) => [topic.id, topic.name])),
    [topics],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setNotice(null);
    setRevealed(new Set());

    api
      .listFlashcards(studentId)
      .then((list) => {
        if (!cancelled) setCards(list);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load flashcards.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [studentId]);

  async function handleGenerate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    if (!topicId) {
      setError("Choose a topic before generating cards.");
      return;
    }

    setGenerating(true);
    try {
      const batch = await api.generateFlashcards(studentId, Number(topicId), count);
      setCards((previous) => [...batch.flashcards, ...previous]);
      setNotice(
        `${batch.flashcards.length} cards added from ${
          batch.source === "llm" ? "the language model" : "the offline fallback"
        }.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate flashcards.");
    } finally {
      setGenerating(false);
    }
  }

  async function handleDelete(cardId: number) {
    setError(null);
    setNotice(null);
    setDeletingId(cardId);
    try {
      await api.deleteFlashcard(cardId);
      setCards((previous) => previous.filter((card) => card.id !== cardId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete the flashcard.");
    } finally {
      setDeletingId(null);
    }
  }

  function toggleAnswer(cardId: number) {
    setRevealed((previous) => {
      const next = new Set(previous);
      if (next.has(cardId)) {
        next.delete(cardId);
      } else {
        next.add(cardId);
      }
      return next;
    });
  }

  return (
    <div className="flashcards">
      <form className="flashcard-controls" onSubmit={handleGenerate}>
        <div>
          <label htmlFor="flashcard-topic">Topic</label>
          <select
            id="flashcard-topic"
            value={topicId}
            onChange={(event) => setTopicId(event.target.value)}
            disabled={topics.length === 0}
          >
            <option value="">Select a topic…</option>
            {topics.map((topic) => (
              <option key={topic.id} value={topic.id}>
                {topic.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="flashcard-count">How many</label>
          <select
            id="flashcard-count"
            value={count}
            onChange={(event) => setCount(Number(event.target.value))}
          >
            <option value={3}>3 cards</option>
            <option value={5}>5 cards</option>
            <option value={8}>8 cards</option>
          </select>
        </div>
        <button
          type="submit"
          className="button primary"
          disabled={generating || topics.length === 0}
        >
          {generating ? "Generating…" : "Generate cards"}
        </button>
      </form>

      <div aria-live="polite">
        {notice && <p className="alert success" role="status">{notice}</p>}
        {error && <p className="alert error" role="alert">{error}</p>}
      </div>

      {loading ? (
        <p className="empty-state">Loading flashcards…</p>
      ) : cards.length === 0 ? (
        <p className="empty-state">
          No flashcards yet. Pick a topic and generate a set, or create cards through the API.
        </p>
      ) : (
        <ul className="flashcard-grid">
          {cards.map((card) => {
            const isRevealed = revealed.has(card.id);
            const answerId = `flashcard-answer-${card.id}`;
            return (
              <li key={card.id} className="flashcard">
                <div className="flashcard-top">
                  <span className="topic-chip">
                    {topicNames.get(card.topic_id) ?? `Topic ${card.topic_id}`}
                  </span>
                  <span className="source-chip">{SOURCE_LABELS[card.source] ?? card.source}</span>
                </div>
                <p className="flashcard-question">{card.question}</p>
                <p className="flashcard-answer" id={answerId} hidden={!isRevealed}>
                  {card.answer}
                </p>
                <div className="flashcard-actions">
                  <button
                    type="button"
                    className="button small"
                    aria-expanded={isRevealed}
                    aria-controls={answerId}
                    onClick={() => toggleAnswer(card.id)}
                  >
                    {isRevealed ? "Hide answer" : "Show answer"}
                  </button>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={`Delete flashcard: ${card.question}`}
                    onClick={() => void handleDelete(card.id)}
                    disabled={deletingId === card.id}
                  >
                    {deletingId === card.id ? "…" : "Delete"}
                  </button>
                </div>
                <p className="flashcard-date">Added {formatDate(card.created_at)}</p>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
