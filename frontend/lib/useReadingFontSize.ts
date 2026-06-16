"use client";

// 읽기 글자 크기(설정 localStorage)를 구독하는 공용 훅 — AI 채팅 상담과 테마 사주 뷰어가 공유한다.
// 같은 탭에서의 변경은 커스텀 이벤트로, 다른 탭에서의 변경은 storage 이벤트로 즉시 반영한다.

import { useEffect, useState } from "react";

import {
  READING_FONT_CHANGE_EVENT,
  type ReadingFontSize,
  loadReadingFontSize,
} from "./storage";

/** 현재 읽기 글자 크기를 반환하고, 설정 변경 시 자동으로 갱신한다. */
export function useReadingFontSize(): ReadingFontSize {
  const [size, setSize] = useState<ReadingFontSize>("base");
  useEffect(() => {
    const sync = () => setSize(loadReadingFontSize());
    sync(); // 마운트 시 1회 로드(SSR 기본값 "base" → 클라이언트 값으로 교정)
    window.addEventListener(READING_FONT_CHANGE_EVENT, sync);
    window.addEventListener("storage", sync); // 다른 탭에서 변경 시
    return () => {
      window.removeEventListener(READING_FONT_CHANGE_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  return size;
}
