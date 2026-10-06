import { Component, type ReactNode } from "react";

/** Last resort: an error the page did not handle is shown, in French, instead of a blank
 *  screen (P8). Nothing is lost: corrections are saved by the service as they are made. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error === null) return this.props.children;
    return (
      <div className="cl-crash" role="alert">
        <h1>Cette page a rencontré une erreur</h1>
        <p>
          Vos corrections déjà enregistrées ne sont pas perdues. Rechargez la page pour reprendre.
        </p>
        <pre>{this.state.error.message}</pre>
        <button type="button" onClick={() => window.location.reload()}>
          Recharger la page
        </button>
      </div>
    );
  }
}
