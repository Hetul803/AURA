import { useState } from 'react';
import { panicStop, sendCommand, subscribeRun } from './state/api';
import ActionPanel from './ui/ActionPanel';
import { pushEvent, store } from './state/store';

export default function App() {
  const [input, setInput] = useState('');
  const [out, setOut] = useState('');
  const [runId, setRunId] = useState('');
  const [clarifications, setClarifications] = useState<any[]>([]);
  const [events, setEvents] = useState<any[]>([]);

  async function run(choices: Record<string, string> = {}, useMacro = false) {
    const res = await sendCommand(input, choices, useMacro);
    setOut(JSON.stringify(res, null, 2));
    if (res.run_id) {
      setRunId(res.run_id);
      subscribeRun(res.run_id, (evt) => {
        pushEvent(evt);
        setEvents([...(store.eventsByRun[res.run_id] || [])]);
      });
    }
    setClarifications(res.clarifications || []);
  }

  const autoChoices = Object.fromEntries(clarifications.map((c: any) => [c.key, c.options[0]]));

  return <div>
    <h1>AURA Overlay</h1>
    <button aria-label='mic'>🎤</button>
    <p>Transcription stub active.</p>
    <input value={input} onChange={e => setInput(e.target.value)} placeholder='Type command' />
    <button onClick={() => run()}>Run</button>
    <button onClick={() => panicStop(runId)} disabled={!runId}>Panic Stop</button>
    {!!clarifications.length && <button onClick={() => run(autoChoices)}>Answer Clarifications</button>}
    <ActionPanel events={events} />
    <pre>{out}</pre>
  </div>;
}
