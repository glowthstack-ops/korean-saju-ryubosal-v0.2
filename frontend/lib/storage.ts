// 사용자 프로필을 IndexedDB에 암호화 저장한다.
// 키는 AES-GCM 256 비트 non-extractable CryptoKey로, IndexedDB에 저장되지만 추출 불가능하다.

import type { CalibrationResult, Profile } from "./types";

const DB_NAME = "ryubosal";
const DB_VERSION = 1;
const KEY_STORE = "keys";
const DATA_STORE = "profile";
const KEY_ID = "aes-key";
const DATA_ID = "current";

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(KEY_STORE)) db.createObjectStore(KEY_STORE);
      if (!db.objectStoreNames.contains(DATA_STORE)) db.createObjectStore(DATA_STORE);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function tx<T>(
  db: IDBDatabase,
  store: string,
  mode: IDBTransactionMode,
  op: (s: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const request = op(db.transaction(store, mode).objectStore(store));
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function getKey(): Promise<CryptoKey> {
  const db = await openDB();
  const existing = (await tx<CryptoKey | undefined>(
    db,
    KEY_STORE,
    "readonly",
    (s) => s.get(KEY_ID) as IDBRequest<CryptoKey | undefined>,
  )) as CryptoKey | undefined;
  if (existing) return existing;

  const key = await crypto.subtle.generateKey(
    { name: "AES-GCM", length: 256 },
    false, // non-extractable: 키 자체를 읽어낼 수 없음
    ["encrypt", "decrypt"],
  );
  await tx(db, KEY_STORE, "readwrite", (s) => s.put(key, KEY_ID));
  return key;
}

const enc = new TextEncoder();
const dec = new TextDecoder();

export async function saveProfile(profile: Profile): Promise<void> {
  const key = await getKey();
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    key,
    enc.encode(JSON.stringify(profile)),
  );
  const db = await openDB();
  await tx(db, DATA_STORE, "readwrite", (s) =>
    s.put({ iv, ciphertext }, DATA_ID),
  );
}

export async function loadProfile(): Promise<Profile | null> {
  const db = await openDB();
  const rec = (await tx<{ iv: Uint8Array; ciphertext: ArrayBuffer } | undefined>(
    db,
    DATA_STORE,
    "readonly",
    (s) => s.get(DATA_ID) as IDBRequest<{ iv: Uint8Array; ciphertext: ArrayBuffer } | undefined>,
  )) as { iv: Uint8Array; ciphertext: ArrayBuffer } | undefined;
  if (!rec) return null;
  const key = await getKey();
  const plain = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: rec.iv },
    key,
    rec.ciphertext,
  );
  return JSON.parse(dec.decode(plain)) as Profile;
}

export async function clearProfile(): Promise<void> {
  const db = await openDB();
  await tx(db, DATA_STORE, "readwrite", (s) => s.delete(DATA_ID));
  await tx(db, DATA_STORE, "readwrite", (s) => s.delete(CALIB_ID));
  await tx(db, KEY_STORE, "readwrite", (s) => s.delete(KEY_ID));
}

// ── 용신 검증 상태 저장 ──────────────────────────────────────────
// 답변/결과를 같은 키(AES-GCM)로 암호화해 IndexedDB에 보존한다.
// sig(출생 시그니처)로 동일 명식 여부를, chartId(기준일 포함)로 동일 질문셋 여부를 판별한다.
const CALIB_ID = "calibration";

export type SavedCalibration = {
  sig: string;
  chartId: string;
  answers: Record<string, { rating: string; events: string[] }>;
  result: CalibrationResult | null;
};

// 출생 기반 안정 시그니처(기준일 제외) — 명식이 같으면 확정 결과를 유지.
export function profileSig(p: Profile): string {
  return JSON.stringify([
    p.calendarType, p.isLeapMonth, p.birthDate, p.birthTime, p.timeUnknown,
    p.place?.name, p.gender,
  ]);
}

export async function saveCalibration(data: SavedCalibration): Promise<void> {
  const key = await getKey();
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    key,
    enc.encode(JSON.stringify(data)),
  );
  const db = await openDB();
  await tx(db, DATA_STORE, "readwrite", (s) => s.put({ iv, ciphertext }, CALIB_ID));
}

export async function loadCalibration(): Promise<SavedCalibration | null> {
  const db = await openDB();
  const rec = (await tx<{ iv: Uint8Array; ciphertext: ArrayBuffer } | undefined>(
    db,
    DATA_STORE,
    "readonly",
    (s) => s.get(CALIB_ID) as IDBRequest<{ iv: Uint8Array; ciphertext: ArrayBuffer } | undefined>,
  )) as { iv: Uint8Array; ciphertext: ArrayBuffer } | undefined;
  if (!rec) return null;
  const key = await getKey();
  const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: rec.iv }, key, rec.ciphertext);
  return JSON.parse(dec.decode(plain)) as SavedCalibration;
}

export async function clearCalibration(): Promise<void> {
  const db = await openDB();
  await tx(db, DATA_STORE, "readwrite", (s) => s.delete(CALIB_ID));
}

// ── 균시차(Equation of Time) 사용 토글 저장 ─────────────────────
// 민감정보가 아닌 표시 옵션 boolean이라 암호화 없이 localStorage에 보존한다.
// 만세력 결과 페이지의 토글 상태를 간지달력(일운) 등 다른 라우트와 공유하는 용도.
const EOT_KEY = "ryubosal:applyEquationOfTime";

/** 균시차 사용 여부를 저장한다(기본값 true와 무관하게 명시 저장). */
export function saveEotPreference(value: boolean): void {
  try {
    localStorage.setItem(EOT_KEY, value ? "1" : "0");
  } catch {
    /* SSR/프라이빗 모드 등 접근 불가 시 무시 */
  }
}

/** 저장된 균시차 사용 여부를 읽는다. 미저장/접근 불가 시 기본값 true. */
export function loadEotPreference(): boolean {
  try {
    return localStorage.getItem(EOT_KEY) !== "0";
  } catch {
    return true;
  }
}

// ── AI 채팅 상담 폰트 크기 ───────────────────────────────────────
// 표시 옵션이라 암호화 없이 localStorage에 보존(기기별 가독성 설정).
// "base"=현재 기본 크기, "large"=한 단계 키운 크기. 설정 변경 시 같은 탭의
// 채팅 화면이 즉시 반영하도록 커스텀 이벤트를 발행한다.
const CHAT_FONT_KEY = "ryubosal:chatFontSize";
export const CHAT_FONT_CHANGE_EVENT = "ryubosal:chatFontChange";
export type ChatFontSize = "base" | "large";

/** 채팅 폰트 크기를 저장하고 변경 이벤트를 발행한다. */
export function saveChatFontSize(value: ChatFontSize): void {
  try {
    localStorage.setItem(CHAT_FONT_KEY, value);
    window.dispatchEvent(new Event(CHAT_FONT_CHANGE_EVENT));
  } catch {
    /* SSR/프라이빗 모드 등 접근 불가 시 무시 */
  }
}

/** 저장된 채팅 폰트 크기를 읽는다. 미저장/접근 불가 시 기본값 "base". */
export function loadChatFontSize(): ChatFontSize {
  try {
    return localStorage.getItem(CHAT_FONT_KEY) === "large" ? "large" : "base";
  } catch {
    return "base";
  }
}
