// 사용자 프로필을 IndexedDB에 암호화 저장한다.
// 키는 AES-GCM 256 비트 non-extractable CryptoKey로, IndexedDB에 저장되지만 추출 불가능하다.

import type { Profile } from "./types";

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
  await tx(db, KEY_STORE, "readwrite", (s) => s.delete(KEY_ID));
}
