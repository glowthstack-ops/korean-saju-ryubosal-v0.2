"use client";

// 전역 클라이언트 프로바이더 묶음 — 서버 컴포넌트인 layout에서 children을 감싼다.

import { AuthProvider } from "./AuthProvider";
import { GnbProvider } from "./GnbProvider";
import { ReportNotificationsProvider } from "./ReportNotificationsProvider";
import { SelectedSubjectProvider } from "./SelectedSubjectProvider";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <SelectedSubjectProvider>
        <ReportNotificationsProvider>
          <GnbProvider>{children}</GnbProvider>
        </ReportNotificationsProvider>
      </SelectedSubjectProvider>
    </AuthProvider>
  );
}
