import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';

declare global {
  interface Window {
    auraDesktop?: {
      reportRendererIssue?: (issue: any) => Promise<any>;
    };
  }
}

function reportRendererIssue(issue: any) {
  window.auraDesktop?.reportRendererIssue?.(issue).catch(() => undefined);
}

function AuraCrashScreen(props: { title: string; detail: string }) {
  return <div className="renderer-crash">
    <section className="renderer-crash-card">
      <div className="crash-orb" />
      <span>Aegisure startup repair</span>
      <h1>{props.title}</h1>
      <p>{props.detail}</p>
      <p>Try reopening Aegisure. If this persists, rebuild from a clean clone with <code>pnpm aura:package</code>, then open Advanced / Diagnostics and logs.</p>
      <button onClick={() => window.location.reload()}>Reload Aegisure</button>
    </section>
  </div>;
}

class ErrorBoundary extends React.Component<React.PropsWithChildren, { error: Error | null }> {
  state = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    reportRendererIssue({ type: 'react_error', message: error.message, stack: error.stack, componentStack: info.componentStack });
  }

  render() {
    if (this.state.error) {
      return <AuraCrashScreen title="Aegisure hit a renderer error." detail={this.state.error.message || 'Unknown renderer error.'} />;
    }
    return this.props.children;
  }
}

window.addEventListener('error', (event) => {
  reportRendererIssue({ type: 'window_error', message: event.message, stack: event.error?.stack, source: event.filename, line: event.lineno, column: event.colno });
});

window.addEventListener('unhandledrejection', (event) => {
  reportRendererIssue({ type: 'unhandled_rejection', reason: String(event.reason), stack: event.reason?.stack });
});

const root = document.getElementById('root');
if (!root) {
  document.body.innerHTML = '<div class="renderer-crash"><section class="renderer-crash-card"><h1>Aegisure could not find its root element.</h1><p>Rebuild the desktop package and reopen the app.</p></section></div>';
} else {
  createRoot(root).render(
    <React.StrictMode>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </React.StrictMode>
  );
}
