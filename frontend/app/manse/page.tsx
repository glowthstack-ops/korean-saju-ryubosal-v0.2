"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { BirthForm } from "@/components/manse/BirthForm";
import { loadProfile, saveProfile } from "@/lib/storage";
import type { Profile } from "@/lib/types";

export default function MansePage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    loadProfile()
      .then((p) => {
        if (p) router.replace("/manse/result");
        else setReady(true);
      })
      .catch(() => setReady(true));
  }, [router]);

  if (!ready) return <p className="text-sm text-gray-500">불러오는 중…</p>;

  return (
    <BirthForm
      onSubmit={async (profile: Profile) => {
        await saveProfile(profile);
        router.push("/manse/result");
      }}
    />
  );
}
