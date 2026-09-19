import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertOctagon, RotateCcw } from 'lucide-react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ApplicationErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    this.setState({ errorInfo });
    // Keep diagnostics console log without external leaking
    console.error('Unhandled Application Error:', error, errorInfo);
  }

  private handleReset = (): void => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    window.location.href = '/';
  };

  public render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-[#070a12] text-slate-100 flex items-center justify-center p-6">
          <div className="max-w-xl w-full rounded-xl border border-rose-900/60 bg-rose-950/20 p-8 backdrop-blur-md shadow-2xl">
            <div className="flex items-start gap-4">
              <div className="p-3 rounded-lg bg-rose-900/30 border border-rose-800/50 text-rose-400">
                <AlertOctagon className="w-8 h-8" />
              </div>
              <div className="flex-1">
                <h1 className="text-xl font-semibold tracking-tight text-rose-200">
                  Application Runtime Exception
                </h1>
                <p className="mt-2 text-sm text-slate-400 leading-relaxed font-sans">
                  The dashboard encountered an unhandled presentation error. System state remains secure
                  and backend intelligence is unaffected.
                </p>

                {this.state.error && (
                  <div className="mt-4 p-3 rounded-md bg-black/40 border border-slate-800/80 font-mono text-xs text-rose-300 overflow-x-auto">
                    {this.state.error.toString()}
                  </div>
                )}

                <div className="mt-6 flex items-center gap-3">
                  <button
                    onClick={this.handleReset}
                    className="inline-flex items-center gap-2 px-4 py-2 text-xs font-mono font-medium rounded-md bg-rose-900/50 border border-rose-700 text-rose-200 hover:bg-rose-900/80 transition-colors"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    Reset & Return to Dashboard
                  </button>
                  <button
                    onClick={() => window.location.reload()}
                    className="px-4 py-2 text-xs font-mono font-medium rounded-md bg-slate-800/80 border border-slate-700 text-slate-300 hover:bg-slate-700 transition-colors"
                  >
                    Reload Page
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ApplicationErrorBoundary;
