const stages = [
  { name: "SENSE", detail: "Review maritime awareness and source context." },
  { name: "SURVIVE", detail: "Discuss constrained-communications operating modes." },
  { name: "RESPOND", detail: "Run a civilian logistics scenario for human review." },
];

export function DemoNarrative() {
  return (
    <aside className="demo-narrative" aria-label="Illustrative workflow / 演示流程">
      <div className="demo-narrative-heading">
        <strong>Illustrative workflow / 演示流程</strong>
        <span>
          This guided sequence is not an actual network failure, not an automatic
          failover, and not a real-time transition.
        </span>
      </div>
      <ol>
        {stages.map((stage, index) => (
          <li key={stage.name}>
            <span className="demo-stage-number">0{index + 1}</span>
            <div><strong>{stage.name}</strong><span>{stage.detail}</span></div>
          </li>
        ))}
      </ol>
    </aside>
  );
}
