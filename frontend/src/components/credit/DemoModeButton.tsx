interface DemoModeButtonProps {
  onRunDemo: () => void;
  busy?: boolean;
}

export function DemoModeButton({ onRunDemo, busy }: DemoModeButtonProps) {
  return (
    <button
      className="demo-btn"
      onClick={onRunDemo}
      disabled={busy}
      type="button"
      title="Run full demo pipeline with pre-seeded data"
    >
      {busy ? "Running Demo…" : "▶ Run Full Demo Pipeline"}
    </button>
  );
}
