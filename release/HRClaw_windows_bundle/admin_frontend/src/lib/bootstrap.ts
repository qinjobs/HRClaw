export interface BootstrapPayload {
  currentPath: string;
  pageKey: string;
  pageTitle: string;
  username?: string;
  userRole?: string;
  nextPath?: string;
}

declare global {
  interface Window {
    __SCREENING_BOOTSTRAP__?: BootstrapPayload;
  }
}

export function getBootstrap(): BootstrapPayload {
  return (
    window.__SCREENING_BOOTSTRAP__ ?? {
      currentPath: window.location.pathname,
      pageKey: "tasks",
      pageTitle: "HRClaw",
    }
  );
}
