// 항목별 설명 툴팁(접근성: details/summary 기반, 클릭 토글).
export function InfoTooltip({ text }: { text: string }) {
  return (
    <details className="ml-1 inline-block align-middle">
      <summary className="inline-flex h-4 w-4 cursor-pointer list-none items-center justify-center rounded-full bg-gray-300 text-[10px] text-gray-700">
        ?
      </summary>
      <span className="mt-1 block rounded bg-gray-800 p-2 text-xs font-normal text-white">
        {text}
      </span>
    </details>
  );
}
