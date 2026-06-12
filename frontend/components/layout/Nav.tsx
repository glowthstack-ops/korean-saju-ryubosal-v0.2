import Link from "next/link";

export function Nav() {
  return (
    <header className="border-b bg-white">
      <nav className="mx-auto flex max-w-3xl items-center gap-6 px-4 py-3">
        <Link href="/" className="text-lg font-bold">
          류보살 <span className="text-gray-400">v2</span>
        </Link>
        <div className="flex gap-4 text-sm">
          <Link href="/manse" className="hover:underline">만세력</Link>
          <Link href="/calendar" className="hover:underline">간지달력</Link>
          <Link href="/chat" className="hover:underline">채팅사주풀이</Link>
        </div>
      </nav>
    </header>
  );
}
