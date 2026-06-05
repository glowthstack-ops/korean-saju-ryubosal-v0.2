// 광고 자리 placeholder. 추후 AdSense 등 광고 네트워크를 이 컴포넌트에 연동한다.
export function AdSlot({ label = "광고" }: { label?: string }) {
  return (
    <div className="my-4 flex h-20 items-center justify-center rounded border border-dashed border-gray-300 bg-white text-xs text-gray-400">
      {label} 영역
    </div>
  );
}
