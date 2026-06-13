"use client";

// 만세력 진입 — 로그인: 사주 선택(게이트웨이) → 결과(?subject=). 비로그인: 기기당 1개 사주
// (IndexedDB)로 바로 입력→결과. 무료 서비스라 비로그인도 이용 가능하다.

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
import { BirthForm } from "@/components/manse/BirthForm";
import { SubjectGateway } from "@/components/subject/SubjectGateway";
import { loadProfile, saveProfile } from "@/lib/storage";
import type { Profile } from "@/lib/types";

export default function MansePage() {
  const router = useRouter();
  const { ready, isLoggedIn } = useAuth();
  const [checked, setChecked] = useState(false);

  // 비로그인: 저장된 1회성 프로필이 있으면 바로 결과로.
  useEffect(() => {
    if (!ready || isLoggedIn) {
      setChecked(true);
      return;
    }
    loadProfile()
      .then((p) => {
        if (p) router.replace("/manse/result");
        else setChecked(true);
      })
      .catch(() => setChecked(true));
  }, [ready, isLoggedIn, router]);

  if (!ready || !checked) return <p className="text-sm text-gray-500">불러오는 중…</p>;

  if (isLoggedIn) {
    return (
      <SubjectGateway
        title="만세력 — 사주 선택"
        returnTo="/manse"
        onResolved={(s) => router.push(`/manse/result?subject=${s.subject_id}`)}
      />
    );
  }

  return (
    <BirthForm
      onSubmit={async (profile: Profile) => {
        await saveProfile(profile);
        router.push("/manse/result");
      }}
    />
  );
}
