import { useEffect, useState } from "react";
import { api } from "../../api/client";

type Props = {
  battle: any;
  sessionId: string;
  onRematch: () => void;
  onReview: () => void;
};

export function DebriefScreen({ battle, sessionId, onRematch, onReview }: Props) {
  const [debrief, setDebrief] = useState<any>(null);
  const [feedback, setFeedback] = useState("");
  const [feedbackStatus, setFeedbackStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [feedbackError, setFeedbackError] = useState<string | null>(null);

  useEffect(() => {
    api.debrief(battle.battle_id).then(setDebrief).catch(() => setDebrief(null));
  }, [battle.battle_id]);

  const status = debrief?.status || battle.status;
  const title =
    status === "VICTORY" ? "Victory" : status === "DEFEAT" ? "Defeat" : status === "DRAW" ? "Draw" : status;

  async function onSubmitFeedback() {
    const message = feedback.trim();
    if (!message || feedbackStatus === "sending" || feedbackStatus === "sent") return;
    setFeedbackStatus("sending");
    setFeedbackError(null);
    try {
      await api.submitFeedback(sessionId, message, {
        battle_id: battle.battle_id,
        status: battle.status,
        result: battle.result,
        round: battle.round,
        seed: battle.seed,
        map_id: battle.map?.map_id || battle.map_id,
      });
      setFeedbackStatus("sent");
    } catch (e: any) {
      setFeedbackStatus("error");
      setFeedbackError(e?.message || "Could not send feedback");
    }
  }

  return (
    <div className="debrief panel stack">
      <h1>{title}</h1>
      <p className="muted">
        Objective: {battle.objective?.label || "Freestyle"} (first to{" "}
        {debrief?.vp_to_win ?? battle.objective?.vp_to_win ?? 5} VP)
      </p>
      <div>
        Score: Blue {debrief?.friendly_vp ?? battle.objective?.friendly_vp ?? 0} – Red{" "}
        {debrief?.opposition_vp ?? battle.objective?.opposition_vp ?? 0} / {debrief?.vp_to_win ?? 5}
      </div>
      <div>Rounds: {debrief?.round ?? battle.round}</div>
      <div>Seed: {debrief?.seed ?? battle.seed}</div>
      <div>Friendly remaining: {debrief?.friendly_remaining ?? "—"}</div>
      <div>Opposition remaining: {debrief?.opposition_remaining ?? "—"}</div>
      <div>Events: {debrief?.event_count ?? battle.last_event_sequence}</div>

      <div className="feedback-block stack">
        <label className="feedback-label" htmlFor="playtest-feedback">
          Playtest feedback
        </label>
        <p className="muted feedback-hint">
          What felt good, broken, confusing, or unfair? This is saved with this session so we can match it to the battle
          logs.
        </p>
        <textarea
          id="playtest-feedback"
          className="feedback-input"
          rows={5}
          maxLength={4000}
          value={feedback}
          disabled={feedbackStatus === "sent" || feedbackStatus === "sending"}
          placeholder="e.g. Red Commander walked too far forward… tanks ignored RAM… Paint Target was unclear…"
          onChange={(e) => setFeedback(e.target.value)}
        />
        <div className="row feedback-actions">
          <button
            className="primary"
            type="button"
            disabled={!feedback.trim() || feedbackStatus === "sending" || feedbackStatus === "sent"}
            onClick={onSubmitFeedback}
          >
            {feedbackStatus === "sending"
              ? "Sending…"
              : feedbackStatus === "sent"
                ? "Feedback sent"
                : "Send feedback"}
          </button>
          {feedbackStatus === "sent" && <span className="muted">Thanks — linked to session {sessionId.slice(0, 8)}</span>}
          {feedbackStatus === "error" && <span className="err">{feedbackError}</span>}
        </div>
      </div>

      <div className="row">
        <button className="primary" onClick={onRematch}>
          Rematch / New Prep
        </button>
        <button onClick={onReview}>Review Battlefield</button>
      </div>
    </div>
  );
}
