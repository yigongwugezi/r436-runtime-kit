# Explainable adaptive revision v1 demo

1. Open an active learning path and complete a task quiz below its passing
   threshold.
2. Return to the path. A pending adjustment card shows the score, threshold,
   weak knowledge point, one added review task, target stage, duration change,
   expected outcome, and risk.
3. Choose **Accept adjustment**. The canonical path gains exactly that review
   task; completed tasks and their progress remain unchanged after refresh.
4. In a fresh path sandbox, choose **Reject adjustment** instead. The path is
   unchanged and no pending card returns after refresh.

The adjustment is deterministic when an LLM is unavailable: it derives a
stable review task ID from learner/session/path/attempt scope and records the
fallback in the revision workflow trace.
