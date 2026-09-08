const STEPS = [
  { id: "borrower", label: "Select Borrower" },
  { id: "assess", label: "Run Assessment" },
  { id: "decide", label: "Review Decision" },
  { id: "execute", label: "Execute" },
];

interface StepIndicatorProps {
  currentStep: number;
  completedSteps: Set<number>;
}

export function StepIndicator({ currentStep, completedSteps }: StepIndicatorProps) {
  return (
    <div className="steps" role="list" aria-label="Demo progress">
      {STEPS.map((step, index) => {
        const isActive = index === currentStep;
        const isDone = completedSteps.has(index);
        const cls = `step ${isActive ? "active" : ""} ${isDone ? "done" : ""}`;
        return (
          <div key={step.id} className={cls} role="listitem" aria-current={isActive ? "step" : undefined}>
            {isDone && !isActive ? "✓ " : ""}
            {step.label}
            {index < STEPS.length - 1 && <span className="step-arrow">→</span>}
          </div>
        );
      })}
    </div>
  );
}
